from calendar import monthrange
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.db import get_db
from app.lifecycle import (
    current_market_date,
    effective_lifecycle,
    effective_lifecycle_expression,
)
from app.models import Exchange, ExchangeListing, IngestionRun, Ipo, Lifecycle, Segment
from app.offer_math import build_lot_applications, build_reservation_summary
from app.schemas import (
    CalendarEvent,
    IpoCard,
    IpoDetail,
    IpoPage,
    PageMeta,
    SummaryOut,
)

router = APIRouter(prefix="/api/v1")


def _card(ipo: Ipo, *, today: date | None = None) -> IpoCard:
    return IpoCard(
        id=ipo.id,
        company_name=ipo.company_name,
        slug=ipo.slug,
        lifecycle=effective_lifecycle(ipo, today=today),
        open_date=ipo.open_date,
        close_date=ipo.close_date,
        allotment_date=ipo.allotment_date,
        allotment_date_is_estimated=ipo.allotment_date_is_estimated,
        refund_date=ipo.refund_date,
        refund_date_is_estimated=ipo.refund_date_is_estimated,
        credit_date=ipo.credit_date,
        credit_date_is_estimated=ipo.credit_date_is_estimated,
        expected_listing_date=ipo.expected_listing_date,
        listing_date=ipo.listing_date,
        price_low=ipo.price_low,
        price_high=ipo.price_high,
        lot_size=ipo.lot_size,
        listings=[listing for listing in ipo.listings if not listing.is_stale],
    )


@router.get("/ipos", response_model=IpoPage)
def list_ipos(
    db: Annotated[Session, Depends(get_db)],
    status: Lifecycle | None = None,
    exchange: Exchange | None = None,
    segment: Segment | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    open_from: date | None = None,
    open_to: date | None = None,
    sort: Literal["open_date", "listing_date", "updated"] = "open_date",
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> IpoPage:
    today = current_market_date()
    lifecycle = effective_lifecycle_expression(today=today)
    statement = select(Ipo).options(selectinload(Ipo.listings))
    filters = [Ipo.listings.any(ExchangeListing.is_stale.is_(False))]
    if status:
        filters.append(lifecycle == status)
    if q:
        filters.append(Ipo.company_name.ilike(f"%{q.strip()}%"))
    if open_from:
        filters.append(Ipo.open_date >= open_from)
    if open_to:
        filters.append(Ipo.open_date <= open_to)
    if cursor:
        filters.append(Ipo.id < cursor)
    if exchange or segment:
        statement = statement.join(ExchangeListing)
        filters.append(ExchangeListing.is_stale.is_(False))
        if exchange:
            filters.append(ExchangeListing.exchange == exchange)
        if segment:
            filters.append(ExchangeListing.segment == segment)
    order_column = {
        "open_date": Ipo.open_date,
        "listing_date": Ipo.listing_date,
        "updated": Ipo.updated_at,
    }[sort]
    rows = (
        db.scalars(
            statement.where(*filters)
            .order_by(order_column.desc().nullslast(), Ipo.id.desc())
            .limit(limit + 1)
        )
        .unique()
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    last_updated = db.scalar(select(func.max(Ipo.updated_at)))
    return IpoPage(
        data=[_card(row, today=today) for row in rows],
        meta=PageMeta(
            next_cursor=rows[-1].id if has_more and rows else None, last_updated_at=last_updated
        ),
    )


@router.get("/ipos/{slug}", response_model=IpoDetail)
def ipo_detail(slug: str, db: Annotated[Session, Depends(get_db)]) -> IpoDetail:
    today = current_market_date()
    ipo = db.scalar(
        select(Ipo)
        .where(Ipo.slug == slug)
        .options(
            selectinload(Ipo.listings),
            selectinload(Ipo.documents),
            selectinload(Ipo.subscriptions),
            selectinload(Ipo.bid_rules),
            selectinload(Ipo.reservations),
        )
    )
    if not ipo:
        raise HTTPException(status_code=404, detail="IPO not found")
    active_listings = [listing for listing in ipo.listings if not listing.is_stale]
    freshest_listing = max(active_listings, key=lambda item: item.last_seen_at, default=None)
    nse_listing = max(
        (listing for listing in active_listings if listing.exchange == Exchange.NSE),
        key=lambda item: item.last_seen_at,
        default=None,
    )
    bse_listing = max(
        (listing for listing in active_listings if listing.exchange == Exchange.BSE),
        key=lambda item: item.last_seen_at,
        default=None,
    )
    exchanges = {listing.exchange for listing in active_listings}
    exchange_platform = (
        "BOTH"
        if exchanges == {Exchange.NSE, Exchange.BSE}
        else next(iter(exchanges)).value
        if exchanges
        else None
    )
    fetched_times = [
        listing.master_data_last_fetched_at
        for listing in active_listings
        if listing.master_data_last_fetched_at is not None
    ]
    return IpoDetail(
        **_card(ipo, today=today).model_dump(),
        isin=ipo.isin,
        issue_type=ipo.issue_type,
        market_type=ipo.market_type,
        platform=freshest_listing.segment if freshest_listing else None,
        exchange_platform=exchange_platform,
        nse_symbol=nse_listing.symbol if nse_listing else None,
        nse_series=nse_listing.series if nse_listing else None,
        bse_symbol=bse_listing.symbol if bse_listing else None,
        bse_scrip_code=bse_listing.scrip_code if bse_listing else None,
        final_issue_price=ipo.final_issue_price,
        face_value=ipo.face_value,
        tick_size=ipo.tick_size,
        minimum_bid_quantity=ipo.minimum_bid_quantity,
        minimum_retail_investment=ipo.minimum_retail_investment,
        issue_size_shares=ipo.issue_size_shares,
        issue_size_crore=ipo.issue_size_crore,
        issue_size_crore_is_estimated=ipo.issue_size_crore_is_estimated,
        registrar=ipo.registrar,
        lead_managers=ipo.lead_managers,
        documents=ipo.documents,
        subscriptions=sorted(
            ipo.subscriptions,
            key=lambda item: (item.captured_at, item.observed_at),
            reverse=True,
        ),
        bid_rules=sorted(ipo.bid_rules, key=lambda item: (item.exchange.value, item.category)),
        reservation_summary=build_reservation_summary(
            ipo, freshest_listing.segment if freshest_listing else None
        ),
        lot_size_applications=build_lot_applications(
            ipo, freshest_listing.segment if freshest_listing else None
        ),
        master_data_last_fetched_at=max(fetched_times, default=None),
        master_data_sources=sorted(
            {
                listing.exchange.value
                for listing in active_listings
                if listing.master_data_last_fetched_at is not None
            }
        ),
        last_updated_at=ipo.updated_at,
        sources=sorted({listing.exchange.value for listing in active_listings}),
    )


@router.get("/calendar", response_model=list[CalendarEvent])
def calendar_events(month: str, db: Annotated[Session, Depends(get_db)]) -> list[CalendarEvent]:
    today = current_market_date()
    try:
        year, month_number = (int(part) for part in month.split("-"))
        start = date(year, month_number, 1)
        end = date(year, month_number, monthrange(year, month_number)[1])
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="month must use YYYY-MM") from None
    rows = db.scalars(
        select(Ipo).where(
            Ipo.listings.any(ExchangeListing.is_stale.is_(False)),
            or_(
                Ipo.open_date.between(start, end),
                Ipo.close_date.between(start, end),
                Ipo.allotment_date.between(start, end),
                Ipo.refund_date.between(start, end),
                Ipo.credit_date.between(start, end),
                Ipo.listing_date.between(start, end),
            )
        )
    ).all()
    events: list[CalendarEvent] = []
    for ipo in rows:
        for event_type, event_date in (
            ("OPENS", ipo.open_date),
            ("CLOSES", ipo.close_date),
            ("ALLOTMENT", ipo.allotment_date),
            ("REFUNDS", ipo.refund_date),
            ("CREDIT", ipo.credit_date),
            ("LISTS", ipo.listing_date),
        ):
            if event_date and start <= event_date <= end:
                events.append(
                    CalendarEvent(
                        ipo_slug=ipo.slug,
                        company_name=ipo.company_name,
                        event_type=event_type,
                        event_date=event_date,
                        lifecycle=effective_lifecycle(ipo, today=today),
                    )
                )
    return sorted(events, key=lambda event: (event.event_date, event.company_name))


@router.get("/meta/summary", response_model=SummaryOut)
def summary(db: Annotated[Session, Depends(get_db)]) -> SummaryOut:
    today = current_market_date()
    lifecycle = effective_lifecycle_expression(today=today)
    def count_where(*conditions: object) -> int:
        return (
            db.scalar(
                select(func.count(func.distinct(Ipo.id))).where(
                    Ipo.listings.any(ExchangeListing.is_stale.is_(False)), *conditions
                )
            )
            or 0
        )

    return SummaryOut(
        open=count_where(lifecycle == Lifecycle.OPEN),
        upcoming=count_where(lifecycle == Lifecycle.UPCOMING),
        listed=count_where(lifecycle == Lifecycle.LISTED),
        mainboard=count_where(
            Ipo.listings.any(
                and_(
                    ExchangeListing.segment == Segment.MAINBOARD,
                    ExchangeListing.is_stale.is_(False),
                )
            )
        ),
        sme=count_where(
            Ipo.listings.any(
                and_(
                    ExchangeListing.segment == Segment.SME,
                    ExchangeListing.is_stale.is_(False),
                )
            )
        ),
        last_updated_at=db.scalar(select(func.max(Ipo.updated_at))),
    )


@router.get("/internal/ingestion-status", include_in_schema=False)
def ingestion_status(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> list[dict[str, object]]:
    if authorization != f"Bearer {settings.internal_api_token}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    rows = db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(20)).all()
    return [
        {
            "id": row.id,
            "exchange": row.exchange,
            "status": row.status,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "fetched_count": row.fetched_count,
            "error": row.error,
        }
        for row in rows
    ]
