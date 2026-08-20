import argparse
import asyncio
import json
import logging
import sys

from app.ingestion.service import run_ingestion


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest current-year NSE and BSE equity IPO data")
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format=json.dumps(
            {"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}
        ),
    )
    succeeded = asyncio.run(run_ingestion(args.year))
    sys.exit(0 if succeeded else 1)


if __name__ == "__main__":
    main()
