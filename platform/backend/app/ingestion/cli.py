import argparse
import asyncio
import json
import logging
import sys

from app.config import get_settings
from app.ingestion.service import run_ingestion
from app.services.rhp.extraction import process_extraction_batch_async


async def run_automatic_pipeline(year: int | None = None) -> bool:
    """Ingest exchange data and drain the Gemini queue when it is configured.

    Keeping this orchestration in the cron entry point lets API deployments omit
    Gemini/R2 secrets while making a single ingestion cron an end-to-end worker.
    """
    ready_document_ids: set[int] = set()
    ingestion_succeeded = await run_ingestion(
        year,
        ready_rhp_document_ids=ready_document_ids,
    )
    settings = get_settings()
    if not settings.gemini_configured:
        logging.info("rhp_extraction_skipped_gemini_not_configured")
        return ingestion_succeeded
    if not ready_document_ids:
        logging.info("rhp_extraction_skipped_no_new_rhp")
        return ingestion_succeeded

    queued = succeeded = failed = 0
    for document_id in sorted(ready_document_ids):
        try:
            batch_queued, batch_succeeded, batch_failed = (
                await process_extraction_batch_async(
                    settings,
                    limit=1,
                    document_id=document_id,
                )
            )
            queued += batch_queued
            succeeded += batch_succeeded
            failed += batch_failed
        except Exception:
            failed += 1
            logging.exception(
                "rhp_extraction_failed_for_new_document",
                extra={"document_id": document_id},
            )
    logging.info(
        "rhp_extraction_batch_finished queued=%s succeeded=%s failed=%s",
        queued,
        succeeded,
        failed,
    )
    return ingestion_succeeded and failed == 0


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
    succeeded = asyncio.run(run_automatic_pipeline(args.year))
    sys.exit(0 if succeeded else 1)


if __name__ == "__main__":
    main()
