import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from app.scrapers import fetch_ipo_issues
from app.scrapers.models import NormalizedIPO, SourceIssue
from app.scrapers.normalizer import IPONormalizer


class ReportRepository(Protocol):
    def current_ipos(self) -> list[dict[str, Any]]: ...

    def table_freshness(self) -> list[dict[str, Any]]: ...

    def health_since(self, since: datetime) -> list[dict[str, Any]]: ...

    def current_health(self) -> list[dict[str, Any]]: ...


def _key(item: dict[str, Any] | NormalizedIPO) -> tuple[str, str]:
    if isinstance(item, dict):
        return str(item["exchange"]), str(item["symbol"])
    return item.exchange, item.symbol


def _ipo_dict(ipo: NormalizedIPO) -> dict[str, Any]:
    return {
        "name": ipo.name,
        "symbol": ipo.symbol,
        "exchange": ipo.exchange,
        "board": ipo.board,
        "status": ipo.status,
        "open_date": ipo.open_date,
        "close_date": ipo.close_date,
        "listing_date": ipo.listing_date,
        "sources": ipo.sources,
    }


async def build_report(
    repository: ReportRepository,
    *,
    now: datetime | None = None,
    issue_fetcher: Callable[[], Awaitable[list[SourceIssue]]] = fetch_ipo_issues,
) -> dict[str, Any]:
    """Compare the database with a fresh read of the official exchange feeds."""

    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)

    issues, database_ipos, freshness, health, current_health = await asyncio.gather(
        issue_fetcher(),
        asyncio.to_thread(repository.current_ipos),
        asyncio.to_thread(repository.table_freshness),
        asyncio.to_thread(repository.health_since, generated_at - timedelta(hours=24)),
        asyncio.to_thread(repository.current_health),
    )
    normalized = IPONormalizer(
        today=generated_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
    ).merge(issues)
    exchange_ipos = [
        ipo for ipo in normalized.ipos if ipo.status in {"upcoming", "open"}
    ]
    database_by_key = {_key(item): item for item in database_ipos}
    exchange_by_key = {_key(item): item for item in exchange_ipos}
    database_keys = set(database_by_key)
    exchange_keys = set(exchange_by_key)

    freshness_output = []
    for item in freshness:
        freshest_at = item["freshest_at"]
        age_seconds = (
            max(0, int((generated_at - freshest_at).total_seconds()))
            if freshest_at is not None
            else None
        )
        freshness_output.append({**item, "age_seconds": age_seconds})

    counts = Counter(str(item["status"]) for item in health)
    stuck = sum(
        item["status"] == "running"
        and item["started_at"] < generated_at - timedelta(minutes=20)
        for item in health
    )
    return {
        "generated_at": generated_at,
        "comparison": {
            "matches": database_keys == exchange_keys and not normalized.rejected,
            "database_count": len(database_ipos),
            "exchange_count": len(exchange_ipos),
            "database_current": database_ipos,
            "exchange_current": [_ipo_dict(ipo) for ipo in exchange_ipos],
            "missing_from_database": [
                _ipo_dict(exchange_by_key[key])
                for key in sorted(exchange_keys - database_keys)
            ],
            "missing_from_exchange": [
                database_by_key[key] for key in sorted(database_keys - exchange_keys)
            ],
            "rejected_exchange_rows": [
                {
                    "source": item.source,
                    "source_id": item.source_id,
                    "reason": item.reason,
                }
                for item in normalized.rejected
            ],
        },
        "table_freshness": freshness_output,
        "health_24h": {
            "since": generated_at - timedelta(hours=24),
            "counts": {
                "total": len(health),
                "succeeded": counts["succeeded"],
                "failed": counts["failed"],
                "running": counts["running"],
                "stuck": stuck,
            },
            "runs": health,
            "current": current_health,
        },
    }
