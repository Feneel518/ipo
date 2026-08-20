import gzip
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from google.cloud import storage
from slugify import slugify
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.ingestion.bse import BSEAdapter
from app.ingestion.nse import NSEAdapter
from app.ingestion.types import NormalizedIssue, Subscription
from app.models import (
    BidRule,
    Exchange,
    ExchangeListing,
    IngestionRun,
    Ipo,
    IpoDocument,
    Lifecycle,
    MarketType,
    SourceRecord,
    SubscriptionSnapshot,
)

logger = logging.getLogger(__name__)
LOCK_ID = 1_904_2026
IST = ZoneInfo("Asia/Kolkata")


def _set_if_present(target: object, values: dict[str, object]) -> None:
    for key, value in values.items():
        if value is not None:
            setattr(target, key, value)


def _next_refresh(
    lifecycle: Lifecycle, listing_date, now: datetime
) -> tuple[datetime | None, datetime | None]:
    if lifecycle in {Lifecycle.WITHDRAWN, Lifecycle.CANCELLED}:
        return None, now
    if lifecycle == Lifecycle.LISTED and listing_date and (now.date() - listing_date).days >= 7:
        return None, now
    interval = {
        Lifecycle.UPCOMING: timedelta(hours=6),
        Lifecycle.OPEN: timedelta(minutes=5),
        Lifecycle.CLOSED: timedelta(days=1),
        Lifecycle.LISTED: timedelta(days=1),
    }.get(lifecycle, timedelta(days=1))
    return now + interval, None


def _detail_is_due(listing: ExchangeListing | None, now: datetime) -> bool:
    if listing is None or listing.master_data_last_fetched_at is None:
        return True
    if listing.master_data_finalized_at is not None:
        return False
    return listing.next_refresh_at is None or listing.next_refresh_at <= now


def _failure_retry(now: datetime, failure_count: int) -> datetime:
    return now + timedelta(hours=min(2 ** max(failure_count - 1, 0), 24))


def _next_failure_count(current: int | None) -> int:
    """Handle new ORM objects whose database default has not been applied yet."""
    return (current or 0) + 1


def _payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _subscription_content_hash(subscription: Subscription) -> str:
    """Identify a set of reported figures without using poll time or source URL."""
    values = (
        subscription.shares_reserved_for_category,
        subscription.raw_exchange_bid_quantity,
        subscription.applications,
        subscription.calculated_subscription,
        subscription.source_reported_multiple,
    )
    canonical = [format(value.normalize(), "f") if value is not None else None for value in values]
    return hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode()).hexdigest()


def _store_subscription_snapshot(
    db: Session,
    ipo_id: int,
    exchange: Exchange,
    subscription: Subscription,
    observed_at: datetime,
) -> bool:
    """Append a changed observation and leave every previously stored row immutable."""
    captured_at = subscription.captured_at or observed_at
    content_hash = _subscription_content_hash(subscription)
    exists = db.scalar(
        select(SubscriptionSnapshot.id).where(
            SubscriptionSnapshot.ipo_id == ipo_id,
            SubscriptionSnapshot.exchange == exchange,
            SubscriptionSnapshot.captured_at == captured_at,
            SubscriptionSnapshot.category == subscription.category,
            SubscriptionSnapshot.bid_data_scope == subscription.bid_data_scope,
            SubscriptionSnapshot.content_hash == content_hash,
        )
    )
    if exists is not None:
        return False

    db.add(
        SubscriptionSnapshot(
            ipo_id=ipo_id,
            exchange=exchange,
            snapshot_date=captured_at.astimezone(IST).date(),
            captured_at=captured_at,
            observed_at=observed_at,
            category=subscription.category,
            shares_reserved_for_category=subscription.shares_reserved_for_category,
            raw_exchange_bid_quantity=subscription.raw_exchange_bid_quantity,
            applications=subscription.applications,
            calculated_subscription=subscription.calculated_subscription,
            source_reported_multiple=subscription.source_reported_multiple,
            source=subscription.source,
            bid_data_scope=subscription.bid_data_scope,
            content_hash=content_hash,
        )
    )
    return True


def _snapshot(issues: list[NormalizedIssue], exchange: Exchange) -> str | None:
    settings = get_settings()
    if not settings.raw_snapshot_bucket:
        return None
    captured = datetime.now(UTC)
    object_name = f"raw/{exchange.value.lower()}/{captured:%Y/%m/%d/%H%M%S}.json.gz"
    content = json.dumps(
        [
            {
                "discovery": issue.raw,
                "detail": issue.detail_raw,
                "detail_endpoint": issue.detail_endpoint,
                "detail_fetched_at": issue.detail_fetched_at,
                "detail_error": issue.detail_error,
                "subscription": issue.subscription_raw,
                "subscription_endpoint": issue.subscription_endpoint,
            }
            for issue in issues
        ],
        default=str,
    ).encode()
    client = storage.Client()
    blob = client.bucket(settings.raw_snapshot_bucket).blob(object_name)
    blob.upload_from_string(gzip.compress(content), content_type="application/gzip")
    return f"gs://{settings.raw_snapshot_bucket}/{object_name}"


def _find_ipo(db: Session, issue: NormalizedIssue) -> Ipo | None:
    listing = db.scalar(
        select(ExchangeListing).where(
            ExchangeListing.exchange == issue.exchange,
            ExchangeListing.source_id == issue.source_id,
        )
    )
    if issue.isin:
        ipo = db.scalar(select(Ipo).where(Ipo.isin == issue.isin))
        if ipo:
            return ipo
    if listing:
        return db.get(Ipo, listing.ipo_id)
    candidates = db.scalars(
        select(Ipo).where(
            Ipo.normalized_name == issue.normalized_name,
            Ipo.open_date == issue.open_date,
            Ipo.close_date == issue.close_date,
        )
    ).all()
    return candidates[0] if len(candidates) == 1 else None


def _unique_slug(db: Session, issue: NormalizedIssue) -> str:
    base = slugify(issue.company_name) or f"ipo-{issue.source_id}"
    slug = base
    index = 2
    while db.scalar(select(Ipo.id).where(Ipo.slug == slug)):
        slug = f"{base}-{index}"
        index += 1
    return slug


def _upsert_issue(
    db: Session,
    issue: NormalizedIssue,
    snapshot_uri: str | None,
    *,
    detail_attempted: bool = False,
    detail_error: str | None = None,
    warnings: list[str] | None = None,
) -> bool:
    ipo = _find_ipo(db, issue)
    inserted = ipo is None
    if ipo is None:
        ipo = Ipo(
            company_name=issue.company_name,
            normalized_name=issue.normalized_name,
            slug=_unique_slug(db, issue),
            lifecycle=issue.lifecycle,
        )
        db.add(ipo)
        db.flush()
    shared_values = {
        "company_name": issue.company_name,
        "normalized_name": issue.normalized_name,
        "isin": issue.isin,
        "lifecycle": issue.lifecycle,
        "open_date": issue.open_date,
        "close_date": issue.close_date,
        "listing_date": issue.listing_date,
        "price_low": issue.price_low,
        "price_high": issue.price_high,
        "final_issue_price": issue.final_issue_price,
        "face_value": issue.face_value,
        "tick_size": issue.tick_size,
        "lot_size": issue.lot_size,
        "minimum_bid_quantity": issue.minimum_bid_quantity,
        "minimum_retail_investment": issue.minimum_retail_investment,
        "issue_size_shares": issue.issue_size_shares,
        "issue_size_crore": issue.issue_size_crore,
        "registrar": issue.registrar,
        "lead_managers": issue.lead_managers,
    }
    if warnings is not None and not inserted:
        for key, value in shared_values.items():
            old = getattr(ipo, key)
            if value is not None and old is not None and old != value:
                warnings.append(
                    f"{issue.exchange.value}:{issue.source_id} changed {key} from {old} to {value}"
                )
    _set_if_present(
        ipo,
        shared_values,
    )
    ipo.issue_type = "IPO"
    if issue.market_type != MarketType.UNKNOWN:
        ipo.market_type = issue.market_type
    if issue.issue_size_crore is not None:
        ipo.issue_size_crore_is_estimated = issue.issue_size_crore_is_estimated
    listing = db.scalar(
        select(ExchangeListing).where(
            ExchangeListing.exchange == issue.exchange,
            ExchangeListing.source_id == issue.source_id,
        )
    )
    if listing is None:
        listing = ExchangeListing(
            ipo_id=ipo.id,
            exchange=issue.exchange,
            segment=issue.segment,
            source_id=issue.source_id,
            source_url=issue.source_url,
        )
        db.add(listing)
    elif listing.ipo_id != ipo.id:
        # A detail feed can reveal that two discovery records are the same
        # security. ISIN is authoritative, so attach the existing source
        # listing to the canonical IPO instead of attempting a duplicate ISIN.
        listing.ipo_id = ipo.id
    _set_if_present(
        listing,
        {
            "segment": issue.segment,
            "symbol": issue.symbol,
            "series": issue.series,
            "scrip_code": issue.scrip_code,
            "source_status": issue.source_status,
            "source_url": issue.source_url,
            "issue_price": issue.issue_price,
            "listing_price": issue.listing_price,
            "listing_close": issue.listing_close,
        },
    )
    if listing.listing_price and listing.issue_price and listing.issue_price != 0:
        listing.listing_gain_percent = (
            (Decimal(listing.listing_price) - Decimal(listing.issue_price))
            / Decimal(listing.issue_price)
            * Decimal(100)
        )
    listing.last_seen_at = datetime.now(UTC)
    listing.missing_runs = 0
    listing.is_stale = False
    if detail_attempted:
        now = datetime.now(UTC)
        if detail_error:
            listing.detail_last_error = detail_error[:4000]
            if detail_error.startswith("subscription:"):
                # The master-data request succeeded. Keep the live book on its
                # five-minute cadence instead of exponentially backing it off.
                listing.master_data_last_fetched_at = issue.detail_fetched_at or now
                listing.detail_failure_count = 0
                listing.next_refresh_at = now + timedelta(minutes=5)
            else:
                listing.detail_failure_count = _next_failure_count(
                    listing.detail_failure_count
                )
                listing.next_refresh_at = _failure_retry(now, listing.detail_failure_count)
        else:
            listing.master_data_last_fetched_at = issue.detail_fetched_at or now
            listing.detail_failure_count = 0
            listing.detail_last_error = None
            listing.next_refresh_at, listing.master_data_finalized_at = _next_refresh(
                issue.lifecycle, issue.listing_date, now
            )

    for kind, title, url in issue.documents:
        exists = db.scalar(
            select(IpoDocument.id).where(
                IpoDocument.ipo_id == ipo.id,
                IpoDocument.document_type == kind,
                IpoDocument.url == url,
            )
        )
        if not exists:
            db.add(IpoDocument(ipo_id=ipo.id, document_type=kind, title=title, url=url))

    observed = datetime.now(UTC)
    for subscription in issue.subscriptions:
        _store_subscription_snapshot(db, ipo.id, issue.exchange, subscription, observed)

    for bid_rule in issue.bid_rules:
        existing_rule = db.scalar(
            select(BidRule).where(
                BidRule.ipo_id == ipo.id,
                BidRule.exchange == issue.exchange,
                BidRule.category == bid_rule.category,
            )
        )
        if existing_rule is None:
            existing_rule = BidRule(
                ipo_id=ipo.id, exchange=issue.exchange, category=bid_rule.category
            )
            db.add(existing_rule)
        _set_if_present(
            existing_rule,
            {
                "minimum_bid_quantity": bid_rule.minimum_bid_quantity,
                "maximum_bid_quantity": bid_rule.maximum_bid_quantity,
                "maximum_subscription_amount": bid_rule.maximum_subscription_amount,
            },
        )

    record = db.scalar(
        select(SourceRecord).where(
            SourceRecord.exchange == issue.exchange,
            SourceRecord.source_id == issue.source_id,
        )
    )
    previous_detail = None
    previous_error = None
    previous_subscription = None
    previous_subscription_endpoint = None
    if record is not None and isinstance(record.payload, dict):
        previous_detail = record.payload.get("detail")
        previous_error = record.payload.get("detail_error")
        previous_subscription = record.payload.get("subscription")
        previous_subscription_endpoint = record.payload.get("subscription_endpoint")
    combined_payload = {
        "discovery": issue.raw,
        "detail": issue.detail_raw if issue.detail_raw is not None else previous_detail,
        "detail_endpoint": issue.detail_endpoint or (record.endpoint if record else None),
        "detail_fetched_at": (
            issue.detail_fetched_at.isoformat()
            if isinstance(issue.detail_fetched_at, datetime)
            else issue.detail_fetched_at
        ),
        "detail_error": detail_error if detail_attempted else previous_error,
        "subscription": issue.subscription_raw
        if issue.subscription_raw is not None
        else previous_subscription,
        "subscription_endpoint": issue.subscription_endpoint
        or previous_subscription_endpoint,
    }
    if record is None:
        record = SourceRecord(
            exchange=issue.exchange,
            source_id=issue.source_id,
            endpoint=issue.endpoint,
            payload_hash=_payload_hash(combined_payload),
            payload=combined_payload,
        )
        db.add(record)
    _set_if_present(
        record,
        {
            "endpoint": issue.detail_endpoint or issue.endpoint,
            "payload_hash": _payload_hash(combined_payload),
            "payload": combined_payload,
            "raw_snapshot_uri": snapshot_uri,
            "last_seen_at": datetime.now(UTC),
        },
    )
    return inserted


def _mark_missing(db: Session, exchange: Exchange, seen: set[str]) -> None:
    listings = db.scalars(select(ExchangeListing).where(ExchangeListing.exchange == exchange)).all()
    for listing in listings:
        if listing.source_id not in seen:
            listing.missing_runs += 1
            listing.is_stale = listing.missing_runs >= 3


async def ingest_exchange(adapter, year: int) -> bool:
    exchange = adapter.exchange
    with SessionLocal() as db:
        run = IngestionRun(exchange=exchange, status="RUNNING")
        db.add(run)
        db.commit()
        db.refresh(run)
        try:
            issues = await adapter.fetch(year)
            if len(issues) < get_settings().source_minimum_rows:
                raise ValueError(f"Suspicious {exchange.value} response: only {len(issues)} rows")
            now = datetime.now(UTC)
            existing_listings = {
                listing.source_id: listing
                for listing in db.scalars(
                    select(ExchangeListing).where(ExchangeListing.exchange == exchange)
                ).all()
            }
            existing_records = {
                record.source_id: record
                for record in db.scalars(
                    select(SourceRecord).where(SourceRecord.exchange == exchange)
                ).all()
            }
            due_ids = {
                issue.source_id
                for issue in issues
                if issue.lifecycle == Lifecycle.OPEN
                or _detail_is_due(existing_listings.get(issue.source_id), now)
                or (
                    existing_listings.get(issue.source_id) is not None
                    and existing_listings[issue.source_id].ipo.lifecycle != issue.lifecycle
                )
            }
            due_issues = [issue for issue in issues if issue.source_id in due_ids]
            detail_errors: dict[str, str] = {}
            if due_issues:
                enriched, detail_errors = await adapter.enrich(due_issues)
                enriched_by_id = {issue.source_id: issue for issue in enriched}
                issues = [enriched_by_id.get(issue.source_id, issue) for issue in issues]
            hydrated_issues = []
            for issue in issues:
                record = existing_records.get(issue.source_id)
                stored = (
                    record.payload
                    if record is not None and isinstance(record.payload, dict)
                    else {}
                )
                updates = {"detail_error": detail_errors.get(issue.source_id)}
                if issue.detail_raw is None and stored.get("detail") is not None:
                    updates.update(
                        {
                            "detail_raw": stored["detail"],
                            "detail_endpoint": stored.get("detail_endpoint") or record.endpoint,
                            "detail_fetched_at": stored.get("detail_fetched_at"),
                        }
                    )
                if issue.source_id not in due_ids:
                    updates["detail_error"] = stored.get("detail_error")
                hydrated_issues.append(issue.model_copy(update=updates))
            issues = hydrated_issues
            issues = [issue.with_calculated_values() for issue in issues]
            snapshot_uri = _snapshot(issues, exchange)
            inserted = 0
            warnings: list[str] = []
            for issue in issues:
                inserted += int(
                    _upsert_issue(
                        db,
                        issue,
                        snapshot_uri,
                        detail_attempted=issue.source_id in due_ids,
                        detail_error=detail_errors.get(issue.source_id),
                        warnings=warnings,
                    )
                )
            _mark_missing(db, exchange, {issue.source_id for issue in issues})
            run.status = "SUCCEEDED"
            run.fetched_count = len(issues)
            run.inserted_count = inserted
            run.updated_count = len(issues) - inserted
            run.warnings = warnings + [
                f"detail:{source_id}: {error}" for source_id, error in detail_errors.items()
            ]
            run.finished_at = datetime.now(UTC)
            db.commit()
            logger.info(
                "ingestion_succeeded", extra={"exchange": exchange.value, "count": len(issues)}
            )
            return True
        except Exception as exc:
            db.rollback()
            run = db.get(IngestionRun, run.id)
            run.status = "FAILED"
            run.error = str(exc)[:4000]
            run.finished_at = datetime.now(UTC)
            db.commit()
            logger.exception("ingestion_failed", extra={"exchange": exchange.value})
            return False


async def _revalidate() -> None:
    settings = get_settings()
    if not settings.revalidation_url or not settings.revalidation_secret:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            settings.revalidation_url,
            headers={"Authorization": f"Bearer {settings.revalidation_secret}"},
        )
        response.raise_for_status()


async def run_ingestion(year: int | None = None) -> bool:
    selected_year = year or datetime.now(IST).year
    with SessionLocal() as lock_db:
        acquired = lock_db.scalar(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID})
        if not acquired:
            logger.warning("ingestion_skipped_lock_held")
            return False
        try:
            results = []
            for adapter in (NSEAdapter(), BSEAdapter()):
                results.append(await ingest_exchange(adapter, selected_year))
            if any(results):
                try:
                    await _revalidate()
                except Exception:
                    logger.exception("frontend_revalidation_failed")
            return all(results)
        finally:
            lock_db.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})
