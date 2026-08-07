import argparse
import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.config import get_settings
from app.verification.repository import VerificationRepository
from app.verification.service import build_report


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Dump exchange parity, table freshness, and 24-hour job health"
    )
    result.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero on IPO mismatch, failed runs, or stuck runs",
    )
    return result


def main() -> None:
    args = parser().parse_args()
    settings = get_settings()
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL is required")
    repository = VerificationRepository(settings.database_url.get_secret_value())
    try:
        report = asyncio.run(build_report(repository))
    except Exception as exc:
        raise SystemExit(f"verification failed: {type(exc).__name__}: {exc}") from exc
    print(json.dumps(report, default=_json_default, indent=2, sort_keys=True))
    counts = report["health_24h"]["counts"]
    if args.strict and (
        not report["comparison"]["matches"]
        or counts["failed"] > 0
        or counts["stuck"] > 0
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
