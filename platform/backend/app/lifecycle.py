from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import case, literal
from sqlalchemy.sql.elements import ColumnElement

from app.models import Ipo, Lifecycle

IST = ZoneInfo("Asia/Kolkata")


def current_market_date() -> date:
    return datetime.now(IST).date()


def effective_lifecycle(ipo: Ipo, *, today: date | None = None) -> Lifecycle:
    """Derive the public lifecycle from dates instead of trusting a stale source status."""
    current = today or current_market_date()
    if ipo.lifecycle in {Lifecycle.WITHDRAWN, Lifecycle.CANCELLED}:
        return ipo.lifecycle
    if ipo.listing_date and ipo.listing_date <= current:
        return Lifecycle.LISTED
    if ipo.open_date and ipo.open_date > current:
        return Lifecycle.UPCOMING
    if (
        ipo.open_date
        and ipo.close_date
        and ipo.open_date <= current <= ipo.close_date
    ):
        return Lifecycle.OPEN
    if ipo.close_date and ipo.close_date < current:
        return Lifecycle.CLOSED
    return ipo.lifecycle


def effective_lifecycle_expression(*, today: date | None = None) -> ColumnElement[Lifecycle]:
    """SQL equivalent of effective_lifecycle for filters and aggregate counts."""
    current = today or current_market_date()
    lifecycle_type = Ipo.lifecycle.type

    def value(lifecycle: Lifecycle):
        return literal(lifecycle, type_=lifecycle_type)

    return case(
        (
            Ipo.lifecycle.in_([Lifecycle.WITHDRAWN, Lifecycle.CANCELLED]),
            Ipo.lifecycle,
        ),
        (
            Ipo.listing_date.is_not(None) & (Ipo.listing_date <= current),
            value(Lifecycle.LISTED),
        ),
        (
            Ipo.open_date.is_not(None) & (Ipo.open_date > current),
            value(Lifecycle.UPCOMING),
        ),
        (
            Ipo.open_date.is_not(None)
            & Ipo.close_date.is_not(None)
            & (Ipo.open_date <= current)
            & (Ipo.close_date >= current),
            value(Lifecycle.OPEN),
        ),
        (
            Ipo.close_date.is_not(None) & (Ipo.close_date < current),
            value(Lifecycle.CLOSED),
        ),
        else_=Ipo.lifecycle,
    )
