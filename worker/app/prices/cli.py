import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import date

from app.config import get_settings
from app.prices.history import scrape_past_ipos
from app.prices.repository import PriceRepository
from app.prices.service import PriceIngestionService


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Ingest official exchange EOD prices")
    commands = result.add_subparsers(dest="command", required=True)
    backfill = commands.add_parser("backfill", help="one-off historical IPO backfill")
    backfill.add_argument("--start", required=True, type=_date)
    backfill.add_argument("--end", type=_date, default=date.today())
    daily = commands.add_parser("daily", help="idempotent daily price update")
    daily.add_argument("--date", type=_date, default=date.today())
    return result


def main() -> None:
    args = parser().parse_args()
    settings = get_settings()
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL is required")
    repository = PriceRepository(settings.database_url.get_secret_value())
    service = PriceIngestionService(repository)
    if args.command == "backfill":
        if args.start > args.end:
            raise SystemExit("--start must be on or before --end")
        historical = asyncio.run(scrape_past_ipos(args.start, args.end))
        seeded = repository.upsert_ipos(historical.ipos)
        result = asyncio.run(service.backfill(args.start, args.end))
    else:
        seeded = 0
        result = asyncio.run(service.daily(args.date))
    output = {
        "ipos_seeded": seeded,
        "rejected_ipos": (
            len(historical.rejected) if args.command == "backfill" else 0
        ),
        **asdict(result),
    }
    print(json.dumps(output, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
