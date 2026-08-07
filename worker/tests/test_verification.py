import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.scrapers.models import SourceIssue
from app.verification.service import build_report

NOW = datetime(2026, 8, 7, 12, tzinfo=UTC)


class FakeVerificationRepository:
    def __init__(self, *, include_extra: bool = False) -> None:
        self.include_extra = include_extra

    def current_ipos(self) -> list[dict[str, Any]]:
        rows = [
            {
                "name": "Example Limited",
                "symbol": "EXAMPLE",
                "exchange": "NSE",
                "board": "mainboard",
                "status": "open",
                "open_date": date(2026, 8, 7),
                "close_date": date(2026, 8, 11),
                "listing_date": None,
                "updated_at": NOW - timedelta(minutes=5),
            }
        ]
        if self.include_extra:
            rows.append(
                {
                    "name": "Stale Limited",
                    "symbol": "STALE",
                    "exchange": "BSE",
                    "board": "SME",
                    "status": "upcoming",
                    "open_date": None,
                    "close_date": None,
                    "listing_date": None,
                    "updated_at": NOW,
                }
            )
        return rows

    def table_freshness(self) -> list[dict[str, Any]]:
        return [
            {
                "table_name": "ipos",
                "row_count": 1,
                "freshest_at": NOW - timedelta(minutes=5),
            },
            {"table_name": "raw_snapshots", "row_count": 0, "freshest_at": None},
        ]

    def health_since(self, since: datetime) -> list[dict[str, Any]]:
        assert since == NOW - timedelta(hours=24)
        return [
            {
                "id": 1,
                "name": "calendar",
                "started_at": NOW - timedelta(minutes=6),
                "finished_at": NOW - timedelta(minutes=5),
                "status": "succeeded",
                "error": None,
            },
            {
                "id": 2,
                "name": "eod",
                "started_at": NOW - timedelta(hours=2),
                "finished_at": NOW - timedelta(hours=2),
                "status": "failed",
                "error": "download failed",
            },
        ]

    def current_health(self) -> list[dict[str, Any]]:
        return []


async def exchange_issues() -> list[SourceIssue]:
    return [
        SourceIssue(
            source="nse_mainboard",
            exchange="NSE",
            board="mainboard",
            source_id="EXAMPLE",
            payload={
                "companyName": "Example Limited",
                "symbol": "EXAMPLE",
                "series": "EQ",
                "status": "Active",
                "issueStartDate": "07-Aug-2026",
                "issueEndDate": "11-Aug-2026",
                "issuePrice": "100-110",
                "issueSize": "1000000",
            },
        )
    ]


def test_report_matches_database_to_fresh_exchange_read() -> None:
    report = asyncio.run(
        build_report(
            FakeVerificationRepository(), now=NOW, issue_fetcher=exchange_issues
        )
    )

    assert report["comparison"]["matches"] is True
    assert report["comparison"]["missing_from_database"] == []
    assert report["comparison"]["missing_from_exchange"] == []
    assert report["table_freshness"] == [
        {
            "table_name": "ipos",
            "row_count": 1,
            "freshest_at": NOW - timedelta(minutes=5),
            "age_seconds": 300,
        },
        {
            "table_name": "raw_snapshots",
            "row_count": 0,
            "freshest_at": None,
            "age_seconds": None,
        },
    ]
    assert report["health_24h"]["counts"] == {
        "total": 2,
        "succeeded": 1,
        "failed": 1,
        "running": 0,
        "stuck": 0,
    }


def test_report_flags_database_ipo_absent_from_exchange() -> None:
    report = asyncio.run(
        build_report(
            FakeVerificationRepository(include_extra=True),
            now=NOW,
            issue_fetcher=exchange_issues,
        )
    )

    assert report["comparison"]["matches"] is False
    assert [
        item["symbol"] for item in report["comparison"]["missing_from_exchange"]
    ] == ["STALE"]
