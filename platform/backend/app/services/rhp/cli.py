import argparse
import json
import logging
import sys

from app.services.rhp.extraction import (
    process_extraction_batch,
    refresh_calculated_metrics,
    requeue_extraction,
    revalidate_stored_extractions,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract READY single-file RHPs with Gemini")
    parser.add_argument("--limit", type=int, default=None, help="Maximum jobs to process")
    parser.add_argument("--document-id", type=int, default=None, help="Process only this RHP")
    parser.add_argument(
        "--rerun-document-id",
        type=int,
        action="append",
        help="Create a fresh run for a completed document while retaining its prior runs",
    )
    parser.add_argument(
        "--revalidate-prompt-version",
        help="Rebuild canonical rows for completed runs from their stored raw JSON",
    )
    parser.add_argument(
        "--refresh-calculated-metrics",
        action="store_true",
        help="Refresh derived metrics without changing reported facts or review state",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format=json.dumps(
            {"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}
        ),
    )
    try:
        if args.refresh_calculated_metrics:
            if (
                args.revalidate_prompt_version
                or args.rerun_document_id
                or args.document_id is not None
                or args.limit is not None
            ):
                parser.error("--refresh-calculated-metrics cannot be combined with other options")
            refreshed_runs, calculated_rows = refresh_calculated_metrics()
            logging.info(
                "rhp_calculated_metrics_refreshed runs=%s rows=%s",
                refreshed_runs,
                calculated_rows,
            )
            sys.exit(0)
        elif args.revalidate_prompt_version:
            if args.rerun_document_id or args.document_id is not None or args.limit is not None:
                parser.error(
                    "--revalidate-prompt-version cannot be combined with extraction options"
                )
            checked, warning_runs = revalidate_stored_extractions(
                prompt_version=args.revalidate_prompt_version
            )
            logging.info(
                "rhp_revalidation_finished checked=%s warning_runs=%s",
                checked,
                warning_runs,
            )
            sys.exit(0)
        elif args.rerun_document_id:
            if args.document_id is not None or args.limit is not None:
                parser.error("--rerun-document-id cannot be combined with --document-id or --limit")
            queued = succeeded = failed = 0
            for document_id in args.rerun_document_id:
                requeue_extraction(document_id)
                batch_queued, batch_succeeded, batch_failed = process_extraction_batch(
                    limit=1,
                    document_id=document_id,
                )
                queued += batch_queued
                succeeded += batch_succeeded
                failed += batch_failed
        else:
            queued, succeeded, failed = process_extraction_batch(
                limit=args.limit,
                document_id=args.document_id,
            )
    except Exception:
        logging.exception("rhp_extraction_batch_failed")
        sys.exit(1)
    logging.info(
        "rhp_extraction_batch_finished queued=%s succeeded=%s failed=%s",
        queued,
        succeeded,
        failed,
    )
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
