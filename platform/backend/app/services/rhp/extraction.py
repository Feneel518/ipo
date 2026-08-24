"""PostgreSQL-backed happy-path RHP extraction worker.

Only documents represented by one ORIGINAL or OPTIMIZED processing file are
eligible here. CHUNK reconciliation is deliberately a later pipeline phase.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, or_, select, true
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.ingestion.rhp_storage import DownloadedPdf, _download_stored_pdf
from app.models import (
    IpoDocument,
    IpoExtractionJob,
    IpoExtractionRun,
    IpoMetric,
    RhpProcessingFile,
)
from app.services.rhp.gemini import (
    GeminiConfigurationError,
    GeminiFileProcessingError,
    GeminiRequestError,
    GeminiStructuredOutputError,
    create_gemini_client,
    delete_gemini_file,
    extract_rhp_v1,
    upload_pdf_to_gemini,
    wait_for_gemini_file,
)
from app.services.rhp.prompts import PROMPT_VERSION
from app.services.rhp.schema import SCHEMA_VERSION, RhpExtractionV1
from app.services.rhp.validation import normalize_extraction, validate_extraction

logger = logging.getLogger(__name__)
RETRY_DELAYS = (30, 120, 600)


def enqueue_ready_extractions(
    settings: Settings | None = None,
    *,
    document_id: int | None = None,
) -> int:
    """Queue versioned, single-file documents that have no matching job."""
    settings = settings or get_settings()
    processing_file_count = (
        select(func.count(RhpProcessingFile.id))
        .where(RhpProcessingFile.document_id == IpoDocument.id)
        .correlate(IpoDocument)
        .scalar_subquery()
    )
    matching_job = exists(
        select(IpoExtractionJob.id).where(
            IpoExtractionJob.document_sha256 == IpoDocument.content_sha256,
            IpoExtractionJob.model == settings.rhp_primary_model,
            IpoExtractionJob.prompt_version == settings.rhp_prompt_version,
            IpoExtractionJob.schema_version == settings.rhp_schema_version,
        )
    )
    with SessionLocal() as db:
        target_document = IpoDocument.id == document_id if document_id is not None else true()
        documents = db.scalars(
            select(IpoDocument)
            .where(
                IpoDocument.storage_status == "STORED",
                target_document,
                IpoDocument.content_sha256.is_not(None),
                IpoDocument.pdf_processing_status.in_(["READY", "READY_WITH_WARNINGS"]),
                processing_file_count == 1,
                ~matching_job,
            )
            .order_by(IpoDocument.id)
            .limit(settings.rhp_extraction_batch_size)
        ).all()
        for document in documents:
            db.add(
                IpoExtractionJob(
                    document_id=document.id,
                    document_sha256=document.content_sha256,
                    model=settings.rhp_primary_model,
                    prompt_version=settings.rhp_prompt_version,
                    schema_version=settings.rhp_schema_version,
                    status="QUEUED",
                    max_attempts=settings.rhp_extraction_max_attempts,
                )
            )
        db.commit()
        return len(documents)


def requeue_extraction(
    document_id: int,
    settings: Settings | None = None,
) -> int:
    """Queue a fresh auditable run while preserving all prior runs and metrics."""
    settings = settings or get_settings()
    with SessionLocal() as db:
        job = db.scalar(
            select(IpoExtractionJob)
            .where(
                IpoExtractionJob.document_id == document_id,
                IpoExtractionJob.model == settings.rhp_primary_model,
                IpoExtractionJob.prompt_version == settings.rhp_prompt_version,
                IpoExtractionJob.schema_version == settings.rhp_schema_version,
            )
            .with_for_update()
        )
        if job is None:
            raise ValueError(f"No matching extraction job exists for document {document_id}")
        if job.status in {"QUEUED", "PROCESSING", "RETRY"}:
            raise ValueError(f"Extraction job for document {document_id} is already active")
        if job.status in {"REVIEWED", "APPROVED"}:
            raise ValueError("Reviewed or approved extraction jobs cannot be requeued")
        job.status = "QUEUED"
        job.attempts = 0
        job.claimed_at = None
        job.completed_at = None
        job.next_attempt_at = None
        job.last_error_code = None
        job.last_error_message = None
        db.commit()
        return job.id


def claim_next_extraction_job(*, document_id: int | None = None) -> int | None:
    """Claim one due job using PostgreSQL row locking for worker concurrency."""
    now = datetime.now(UTC)
    with SessionLocal() as db:
        target_document = (
            IpoExtractionJob.document_id == document_id
            if document_id is not None
            else true()
        )
        job = db.scalar(
            select(IpoExtractionJob)
            .where(
                IpoExtractionJob.status.in_(["QUEUED", "RETRY"]),
                target_document,
                IpoExtractionJob.attempts < IpoExtractionJob.max_attempts,
                or_(
                    IpoExtractionJob.next_attempt_at.is_(None),
                    IpoExtractionJob.next_attempt_at <= now,
                ),
            )
            .order_by(IpoExtractionJob.created_at, IpoExtractionJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "PROCESSING"
        job.attempts = (job.attempts or 0) + 1
        job.claimed_at = now
        job.next_attempt_at = None
        job.last_error_code = None
        job.last_error_message = None
        db.commit()
        return job.id


def _load_job_work(job_id: int):
    with SessionLocal() as db:
        job = db.scalar(
            select(IpoExtractionJob)
            .options(selectinload(IpoExtractionJob.document).selectinload(IpoDocument.processing_files))
            .where(IpoExtractionJob.id == job_id)
        )
        if job is None:
            raise ValueError(f"Extraction job {job_id} does not exist")
        document = job.document
        files = document.processing_files
        if len(files) != 1 or files[0].kind == "CHUNK":
            raise ValueError("CHUNK_RECONCILIATION_NOT_IMPLEMENTED")
        processing_file = files[0]
        if job.prompt_version != PROMPT_VERSION or job.schema_version != SCHEMA_VERSION:
            raise ValueError("EXTRACTION_VERSION_UNAVAILABLE")
        newest_runs = sorted(job.runs, key=lambda item: item.id, reverse=True)
        resumable_run = next(
            (run for run in newest_runs if run.status == "FAILED" and run.raw_json),
            None,
        )
        resume_json = resumable_run.raw_json if resumable_run is not None else None
        return {
            "job_id": job.id,
            "document_id": document.id,
            "ipo_id": document.ipo_id,
            "document_sha256": job.document_sha256,
            "source_url": document.final_source_url or document.url,
            "processing_file_id": processing_file.id,
            "storage_key": processing_file.storage_key,
            "processing_sha256": processing_file.content_sha256,
            "page_count": processing_file.page_count,
            "model": job.model,
            "prompt_version": job.prompt_version,
            "schema_version": job.schema_version,
            "resume_json": resume_json,
        }


def _create_run(work: dict) -> int:
    with SessionLocal() as db:
        run = IpoExtractionRun(
            job_id=work["job_id"],
            document_id=work["document_id"],
            processing_file_id=work["processing_file_id"],
            document_sha256=work["document_sha256"],
            model=work["model"],
            prompt_version=work["prompt_version"],
            schema_version=work["schema_version"],
            status="DOWNLOADING",
            started_at=datetime.now(UTC),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id


def _set_processing_status(
    job_id: int,
    run_id: int,
    status: str,
    *,
    gemini_file_name: str | None = None,
    gemini_file_uri: str | None = None,
) -> None:
    with SessionLocal() as db:
        job = db.get(IpoExtractionJob, job_id)
        run = db.get(IpoExtractionRun, run_id)
        if job is None or run is None:
            raise RuntimeError("Extraction job or run disappeared while processing")
        job.status = status
        run.status = status
        if gemini_file_name is not None:
            run.gemini_file_name = gemini_file_name
        if gemini_file_uri is not None:
            run.gemini_file_uri = gemini_file_uri
        db.commit()


def _save_success(work: dict, run_id: int, generated) -> str:
    issues = validate_extraction(generated.extraction, page_count=work["page_count"])
    if generated.extraction.extraction_meta.warnings:
        issues.extend(
            {
                "code": "MODEL_WARNING",
                "severity": "WARN",
                "field_path": "extraction_meta.warnings",
                "message": warning,
            }
            for warning in generated.extraction.extraction_meta.warnings
        )
    if generated.extraction.extraction_meta.conflicts:
        issues.extend(
            {
                "code": "MODEL_CONFLICT",
                "severity": "VERIFY",
                "field_path": "extraction_meta.conflicts",
                "message": conflict,
            }
            for conflict in generated.extraction.extraction_meta.conflicts
        )
    final_status = "READY_WITH_WARNINGS" if issues else "READY"
    with SessionLocal() as db:
        job = db.get(IpoExtractionJob, work["job_id"])
        run = db.get(IpoExtractionRun, run_id)
        if job is None or run is None:
            raise RuntimeError("Extraction job or run disappeared before persistence")
        run.raw_json = generated.raw_json
        run.validation_issues = issues or None
        run.input_tokens = generated.input_tokens
        run.output_tokens = generated.output_tokens
        run.request_count = generated.request_count
        run.status = final_status
        run.completed_at = datetime.now(UTC)
        for metric in normalize_extraction(generated.extraction, issues=issues):
            run.metrics.append(
                IpoMetric(
                    ipo_id=work["ipo_id"],
                    document_id=work["document_id"],
                    metric=metric.metric,
                    financial_year=metric.financial_year,
                    numeric_value=metric.numeric_value,
                    text_value=metric.text_value,
                    unit=metric.unit,
                    source="RHP",
                    status=metric.status,
                    provenance=metric.provenance,
                    verification_status="UNVERIFIED",
                )
            )
        job.status = final_status
        job.completed_at = datetime.now(UTC)
        job.next_attempt_at = None
        db.commit()
    return final_status


def revalidate_stored_extractions(
    *,
    prompt_version: str,
    schema_version: str = SCHEMA_VERSION,
) -> tuple[int, int]:
    """Rebuild canonical rows from stored raw JSON using the current validator.

    Paid Gemini output is left untouched. Only completed, unapproved runs for the
    requested version are considered, so this can safely repair canonical rows
    after deterministic validation or normalization improves.
    """
    checked = 0
    warning_runs = 0
    with SessionLocal() as db:
        runs = db.scalars(
            select(IpoExtractionRun)
            .options(
                selectinload(IpoExtractionRun.processing_file),
                selectinload(IpoExtractionRun.metrics),
                selectinload(IpoExtractionRun.job),
            )
            .where(
                IpoExtractionRun.prompt_version == prompt_version,
                IpoExtractionRun.schema_version == schema_version,
                IpoExtractionRun.status.in_(["READY", "READY_WITH_WARNINGS"]),
                IpoExtractionRun.raw_json.is_not(None),
            )
            .order_by(IpoExtractionRun.id)
        ).all()
        for run in runs:
            extraction = RhpExtractionV1.model_validate(run.raw_json)
            page_count = run.processing_file.page_count if run.processing_file else 0
            issues = validate_extraction(extraction, page_count=page_count)
            issues.extend(
                {
                    "code": "MODEL_WARNING",
                    "severity": "WARN",
                    "field_path": "extraction_meta.warnings",
                    "message": warning,
                }
                for warning in extraction.extraction_meta.warnings
            )
            issues.extend(
                {
                    "code": "MODEL_CONFLICT",
                    "severity": "VERIFY",
                    "field_path": "extraction_meta.conflicts",
                    "message": conflict,
                }
                for conflict in extraction.extraction_meta.conflicts
            )
            run.metrics.clear()
            db.flush()
            for metric in normalize_extraction(extraction, issues=issues):
                run.metrics.append(
                    IpoMetric(
                        ipo_id=run.document.ipo_id,
                        document_id=run.document_id,
                        metric=metric.metric,
                        financial_year=metric.financial_year,
                        numeric_value=metric.numeric_value,
                        text_value=metric.text_value,
                        unit=metric.unit,
                        source="RHP",
                        status=metric.status,
                        provenance=metric.provenance,
                        verification_status="UNVERIFIED",
                    )
                )
            final_status = "READY_WITH_WARNINGS" if issues else "READY"
            run.validation_issues = issues or None
            run.status = final_status
            run.job.status = final_status
            checked += 1
            warning_runs += bool(issues)
        db.commit()
    return checked, warning_runs


def _classify_failure(exc: Exception, stage: str) -> tuple[str, bool]:
    if isinstance(exc, GeminiConfigurationError):
        return "GEMINI_NOT_CONFIGURED", False
    if isinstance(exc, GeminiStructuredOutputError):
        return "STRUCTURED_OUTPUT_INVALID", False
    if isinstance(exc, GeminiFileProcessingError):
        return ("GEMINI_TIMEOUT" if "timed out" in str(exc) else "GEMINI_PROCESSING_FAILED"), True
    if isinstance(exc, GeminiRequestError):
        code = exc.code
        if code == 429:
            return "GEMINI_RATE_LIMITED", True
        if isinstance(code, int) and code >= 500:
            return "GEMINI_SERVER_ERROR", True
        return "GEMINI_REQUEST_INVALID", False
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "GEMINI_TIMEOUT", True
    code = getattr(exc, "code", None)
    if code == 429:
        return "GEMINI_RATE_LIMITED", True
    if isinstance(code, int) and code >= 500:
        return "GEMINI_SERVER_ERROR", True
    if str(exc) == "CHUNK_RECONCILIATION_NOT_IMPLEMENTED":
        return "CHUNK_RECONCILIATION_NOT_IMPLEMENTED", False
    if str(exc) == "EXTRACTION_VERSION_UNAVAILABLE":
        return "EXTRACTION_VERSION_UNAVAILABLE", False
    if stage == "DOWNLOADING":
        return "R2_DOWNLOAD_FAILED", True
    if stage == "UPLOADING_TO_GEMINI":
        return "GEMINI_UPLOAD_FAILED", True
    return "EXTRACTION_FAILED", False


def _save_failure(
    job_id: int,
    run_id: int | None,
    exc: Exception,
    stage: str,
) -> None:
    error_code, retryable = _classify_failure(exc, stage)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        job = db.get(IpoExtractionJob, job_id)
        if job is None:
            return
        can_retry = retryable and job.attempts < job.max_attempts
        job.status = "RETRY" if can_retry else "FAILED"
        job.last_error_code = error_code
        job.last_error_message = str(exc)[:4000]
        job.next_attempt_at = (
            now + timedelta(seconds=RETRY_DELAYS[min(job.attempts - 1, len(RETRY_DELAYS) - 1)])
            if can_retry
            else None
        )
        if not can_retry:
            job.completed_at = now
        if run_id is not None:
            run = db.get(IpoExtractionRun, run_id)
            if run is not None:
                run.status = "FAILED"
                run.error_code = error_code
                run.error_message = str(exc)[:4000]
                run.completed_at = now
                tracked_errors = (GeminiStructuredOutputError, GeminiRequestError)
                if isinstance(exc, tracked_errors) and exc.raw_json is not None:
                    run.raw_json = exc.raw_json
                if isinstance(exc, tracked_errors):
                    run.input_tokens = exc.input_tokens
                    run.output_tokens = exc.output_tokens
                if isinstance(exc, GeminiRequestError):
                    run.request_count = exc.request_count
        db.commit()


def process_extraction_job(
    job_id: int,
    settings: Settings | None = None,
    *,
    client=None,
) -> bool:
    """Process one already-claimed job and persist every outcome."""
    settings = settings or get_settings()
    run_id: int | None = None
    downloaded: DownloadedPdf | None = None
    uploaded_name: str | None = None
    owns_client = client is None
    stage = "LOADING"
    try:
        work = _load_job_work(job_id)
        run_id = _create_run(work)
        stage = "DOWNLOADING"
        downloaded = _download_stored_pdf(
            work["storage_key"],
            work["processing_sha256"],
            "application/pdf",
            work["source_url"],
            settings,
        )
        if client is None:
            client = create_gemini_client(settings)
        stage = "UPLOADING_TO_GEMINI"
        _set_processing_status(job_id, run_id, stage)
        uploaded = upload_pdf_to_gemini(client, downloaded.path)
        uploaded_name = uploaded.name
        stage = "GEMINI_PROCESSING"
        _set_processing_status(
            job_id,
            run_id,
            stage,
            gemini_file_name=uploaded.name,
            gemini_file_uri=getattr(uploaded, "uri", None),
        )
        ready = wait_for_gemini_file(
            client,
            uploaded.name,
            timeout_seconds=settings.gemini_file_timeout_seconds,
            poll_seconds=settings.gemini_file_poll_seconds,
        )
        stage = "EXTRACTING"
        _set_processing_status(job_id, run_id, stage)
        generated = extract_rhp_v1(
            client,
            ready,
            model=work["model"],
            initial_json=work["resume_json"],
        )
        stage = "VALIDATING"
        _set_processing_status(job_id, run_id, stage)
        final_status = _save_success(work, run_id, generated)
        logger.info(
            "rhp_extraction_completed",
            extra={
                "job_id": job_id,
                "document_id": work["document_id"],
                "model": work["model"],
                "status": final_status,
            },
        )
        return True
    except Exception as exc:
        _save_failure(job_id, run_id, exc, stage)
        logger.exception("rhp_extraction_failed", extra={"job_id": job_id, "stage": stage})
        return False
    finally:
        if client is not None and uploaded_name is not None:
            try:
                delete_gemini_file(client, uploaded_name)
            except Exception:
                logger.warning("gemini_file_cleanup_failed", extra={"file_name": uploaded_name})
        if downloaded is not None:
            downloaded.cleanup()
        if owns_client and client is not None:
            client.close()


def process_extraction_batch(
    settings: Settings | None = None,
    *,
    limit: int | None = None,
    document_id: int | None = None,
) -> tuple[int, int, int]:
    settings = settings or get_settings()
    if not settings.gemini_configured:
        raise GeminiConfigurationError("GEMINI_API_KEY is not configured")
    queued = enqueue_ready_extractions(settings, document_id=document_id)
    succeeded = 0
    failed = 0
    for _ in range(limit or settings.rhp_extraction_batch_size):
        job_id = claim_next_extraction_job(document_id=document_id)
        if job_id is None:
            break
        if process_extraction_job(job_id, settings):
            succeeded += 1
        else:
            failed += 1
    return queued, succeeded, failed


async def process_extraction_batch_async(
    settings: Settings | None = None,
    *,
    limit: int | None = None,
    document_id: int | None = None,
) -> tuple[int, int, int]:
    return await asyncio.to_thread(
        process_extraction_batch,
        settings,
        limit=limit,
        document_id=document_id,
    )
