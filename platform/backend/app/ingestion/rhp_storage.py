import asyncio
import hashlib
import ipaddress
import logging
import os
import re
import socket
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import exists, or_, select, true
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.lifecycle import effective_lifecycle_expression
from app.models import Exchange, ExchangeListing, IpoDocument, Lifecycle, RhpProcessingFile
from app.services.rhp.inspector import (
    PdfInspection,
    PdfInspectionError,
    PdfProcessingDecision,
    choose_pdf_processing_path,
    inspect_pdf,
)
from app.services.rhp.preparer import PdfPreparationError, PreparedPdf, prepare_pdf_for_gemini

logger = logging.getLogger(__name__)
PDF_SIGNATURE = b"%PDF-"
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
RHP_TOKEN = re.compile(r"(^|[^A-Z])RHP([^A-Z]|$)")
NSE_URL_PATTERN = r"^https?://([^/@]+\.)?nseindia\.com(?::[0-9]+)?/"


class RhpArchiveError(Exception):
    """A retryable RHP archive failure."""


class RhpRejectedError(RhpArchiveError):
    """A permanent validation failure that should not be retried automatically."""


@dataclass
class DownloadedPdf:
    path: Path
    sha256: str
    size_bytes: int
    source_content_type: str | None
    final_url: str

    def cleanup(self) -> None:
        self.path.unlink(missing_ok=True)


def is_rhp_document(document_type: str, title: str) -> bool:
    combined = f"{document_type} {title}".upper()
    return bool(RHP_TOKEN.search(combined) or "RED HERRING" in combined)


def should_archive_rhp(lifecycle: Lifecycle, document_type: str, title: str) -> bool:
    """Only current and forthcoming IPOs are worth sending through extraction."""
    return lifecycle in {Lifecycle.UPCOMING, Lifecycle.OPEN} and is_rhp_document(
        document_type, title
    )


def _host_is_allowed(host: str, allowed_hosts: list[str]) -> bool:
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)


def _validate_url(url: str, allowed_hosts: list[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RhpRejectedError("RHP URL must be an absolute HTTP or HTTPS URL")
    if parsed.username or parsed.password:
        raise RhpRejectedError("RHP URL must not contain credentials")
    host = parsed.hostname.rstrip(".").lower()
    if not allowed_hosts or not _host_is_allowed(host, allowed_hosts):
        raise RhpRejectedError(f"RHP source host is not allowed: {host}")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(host, port)
    except socket.gaierror as exc:
        raise RhpArchiveError(f"Could not resolve RHP source host: {host}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise RhpRejectedError("RHP source resolved to a non-public IP address")


def _temporary_path(suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix="ipodekho-rhp-", suffix=suffix)
    os.close(descriptor)
    return Path(name)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _zip_candidate_rank(info: zipfile.ZipInfo) -> tuple[int, int]:
    name = info.filename.upper()
    preferred = int("RHP" in name or "RED_HERRING" in name or "RED HERRING" in name)
    return preferred, info.file_size


def _extract_pdf_from_zip(archive_path: Path, max_bytes: int) -> Path:
    destination = _temporary_path(".pdf")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            candidates = [
                info
                for info in archive.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".pdf")
            ]
            if not candidates:
                raise RhpRejectedError("ZIP response does not contain a PDF")
            candidate = max(candidates, key=_zip_candidate_rank)
            if candidate.flag_bits & 0x1:
                raise RhpRejectedError("RHP PDF inside ZIP is encrypted")
            if candidate.file_size > max_bytes:
                raise RhpRejectedError("RHP PDF inside ZIP exceeds the configured size limit")

            total = 0
            with archive.open(candidate) as source, destination.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise RhpRejectedError(
                            "Extracted RHP PDF exceeds the configured size limit"
                        )
                    target.write(chunk)
        with destination.open("rb") as file_handle:
            if file_handle.read(len(PDF_SIGNATURE)) != PDF_SIGNATURE:
                raise RhpRejectedError("ZIP member does not have a PDF signature")
        return destination
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise RhpRejectedError("RHP response is not a readable ZIP archive") from exc
    except Exception:
        destination.unlink(missing_ok=True)
        raise


async def download_rhp(url: str, settings: Settings | None = None) -> DownloadedPdf:
    settings = settings or get_settings()
    current_url = url
    download_path = _temporary_path(".download")
    pdf_path: Path | None = None
    content_type: str | None = None
    try:
        timeout = httpx.Timeout(
            connect=settings.rhp_download_connect_timeout_seconds,
            read=settings.rhp_download_read_timeout_seconds,
            write=settings.rhp_download_read_timeout_seconds,
            pool=settings.rhp_download_connect_timeout_seconds,
        )
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for redirect_number in range(settings.rhp_max_redirects + 1):
                await asyncio.to_thread(
                    _validate_url, current_url, settings.rhp_allowed_host_list
                )
                async with client.stream(
                    "GET",
                    current_url,
                    headers={
                        "User-Agent": "IPODekho-RHP-Ingest/1.0",
                        "Accept": "application/pdf,application/zip,*/*;q=0.5",
                    },
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise RhpArchiveError("RHP redirect did not include a location")
                        if redirect_number >= settings.rhp_max_redirects:
                            raise RhpArchiveError("RHP response exceeded the redirect limit")
                        current_url = urljoin(str(response.url), location)
                        continue

                    response.raise_for_status()
                    content_type = response.headers.get("content-type")
                    length = response.headers.get("content-length")
                    if length and int(length) > settings.rhp_download_max_bytes:
                        raise RhpRejectedError("RHP response exceeds the configured size limit")

                    total = 0
                    with download_path.open("wb") as file_handle:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            total += len(chunk)
                            if total > settings.rhp_download_max_bytes:
                                raise RhpRejectedError(
                                    "RHP response exceeds the configured size limit"
                                )
                            file_handle.write(chunk)
                    break
            else:  # pragma: no cover - loop always exits by break or exception
                raise RhpArchiveError("RHP download did not complete")

        if download_path.stat().st_size < 1024:
            raise RhpRejectedError("RHP response is unexpectedly small")
        with download_path.open("rb") as file_handle:
            signature = file_handle.read(5)
        if signature == PDF_SIGNATURE:
            pdf_path = download_path
        elif signature.startswith(ZIP_SIGNATURES):
            pdf_path = await asyncio.to_thread(
                _extract_pdf_from_zip, download_path, settings.rhp_download_max_bytes
            )
            download_path.unlink(missing_ok=True)
        else:
            raise RhpRejectedError("RHP response is neither a PDF nor a ZIP containing a PDF")

        sha256, size_bytes = await asyncio.to_thread(_sha256_file, pdf_path)
        return DownloadedPdf(
            path=pdf_path,
            sha256=sha256,
            size_bytes=size_bytes,
            source_content_type=content_type,
            final_url=current_url,
        )
    except httpx.HTTPStatusError as exc:
        if 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
            raise RhpRejectedError(f"RHP source returned HTTP {exc.response.status_code}") from exc
        raise RhpArchiveError(f"RHP source returned HTTP {exc.response.status_code}") from exc
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise RhpArchiveError(f"RHP download failed: {exc}") from exc
    finally:
        if pdf_path != download_path:
            download_path.unlink(missing_ok=True)


def _r2_client(settings: Settings):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def _upload_pdf(downloaded: DownloadedPdf, object_key: str, settings: Settings) -> None:
    _upload_local_pdf(
        downloaded.path,
        object_key,
        downloaded.sha256,
        settings,
    )


def _upload_local_pdf(
    path: Path,
    object_key: str,
    sha256: str,
    settings: Settings,
    *,
    metadata: dict[str, str] | None = None,
) -> None:
    object_metadata = {"sha256": sha256}
    if metadata:
        object_metadata.update(metadata)
    _r2_client(settings).upload_file(
        str(path),
        settings.r2_bucket,
        object_key,
        ExtraArgs={
            "ContentType": "application/pdf",
            "ContentDisposition": "inline",
            "Metadata": object_metadata,
        },
    )


def _delete_object(object_key: str, settings: Settings) -> None:
    _r2_client(settings).delete_object(Bucket=settings.r2_bucket, Key=object_key)


def _download_stored_pdf(
    object_key: str,
    expected_sha256: str | None,
    source_content_type: str | None,
    final_url: str,
    settings: Settings,
) -> DownloadedPdf:
    path = _temporary_path(".pdf")
    try:
        _r2_client(settings).download_file(settings.r2_bucket, object_key, str(path))
        with path.open("rb") as source:
            if source.read(len(PDF_SIGNATURE)) != PDF_SIGNATURE:
                raise RhpArchiveError("Stored RHP does not have a PDF signature")
        sha256, size_bytes = _sha256_file(path)
        if expected_sha256 and sha256 != expected_sha256:
            raise RhpArchiveError("Stored RHP SHA-256 does not match its database record")
        return DownloadedPdf(
            path=path,
            sha256=sha256,
            size_bytes=size_bytes,
            source_content_type=source_content_type,
            final_url=final_url,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


async def delete_archived_rhp(document_id: int) -> bool:
    """Delete a canonical PDF after its Gemini result has committed to the database.

    The extraction worker is responsible for calling this only after its extraction
    transaction succeeds. Retaining the hash and timestamps provides a small audit trail
    without continuing to pay for object storage.
    """
    settings = get_settings()
    if not settings.r2_configured:
        raise RuntimeError("R2 is not fully configured")

    with SessionLocal() as db:
        document = db.get(IpoDocument, document_id)
        if document is None:
            raise ValueError(f"RHP document {document_id} does not exist")
        if document.storage_status == "DELETED":
            return False
        if document.storage_status not in {"STORED", "DELETE_FAILED"} or not document.storage_key:
            raise ValueError(f"RHP document {document_id} does not have a stored object")
        object_keys = {document.storage_key}
        object_keys.update(file.storage_key for file in document.processing_files)

    try:
        for object_key in object_keys:
            await asyncio.to_thread(_delete_object, object_key, settings)
    except Exception as exc:
        with SessionLocal() as db:
            document = db.get(IpoDocument, document_id)
            document.storage_status = "DELETE_FAILED"
            document.storage_error = str(exc)[:4000]
            db.commit()
        raise

    with SessionLocal() as db:
        document = db.get(IpoDocument, document_id)
        document.storage_status = "DELETED"
        document.storage_key = None
        document.size_bytes = None
        document.processing_files.clear()
        document.storage_error = None
        document.storage_deleted_at = datetime.now(UTC)
        db.commit()
    return True


async def archive_pending_rhps(
    document_ids: set[int] | None = None,
    *,
    ready_document_ids: set[int] | None = None,
) -> tuple[int, int]:
    """Archive a small post-ingestion batch without coupling R2 health to exchange data."""
    settings = get_settings()
    if not settings.r2_configuration_requested:
        return 0, 0
    if not settings.r2_configured:
        raise RuntimeError("R2 configuration is incomplete; set all four R2_* variables")

    now = datetime.now(UTC)
    retry_before = now - timedelta(minutes=15)
    stale_before = now - timedelta(hours=1)
    current_lifecycle = effective_lifecycle_expression()
    has_nse_listing = exists(
        select(1).where(
            ExchangeListing.ipo_id == IpoDocument.ipo_id,
            ExchangeListing.exchange == Exchange.NSE,
        )
    )
    stored_needs_processing = (
        (IpoDocument.storage_status == "STORED")
        & (IpoDocument.storage_key.is_not(None))
        & or_(
            IpoDocument.pdf_processing_status == "NOT_PREPARED",
            (
                (IpoDocument.pdf_processing_status == "FAILED")
                & (
                    (IpoDocument.storage_attempted_at.is_(None))
                    | (IpoDocument.storage_attempted_at <= retry_before)
                )
            ),
        )
    )
    target_documents = (
        IpoDocument.id.in_(document_ids) if document_ids is not None else true()
    )
    with SessionLocal() as db:
        documents = db.scalars(
            select(IpoDocument)
            .join(IpoDocument.ipo)
            .options(selectinload(IpoDocument.ipo))
            .where(
                current_lifecycle.in_([Lifecycle.UPCOMING, Lifecycle.OPEN]),
                target_documents,
                or_(IpoDocument.url.op("~*")(NSE_URL_PATTERN), ~has_nse_listing),
                IpoDocument.storage_attempts < 5,
                or_(
                    IpoDocument.storage_status == "PENDING",
                    (
                        (IpoDocument.storage_status == "FAILED")
                        & (
                            (IpoDocument.storage_attempted_at.is_(None))
                            | (IpoDocument.storage_attempted_at <= retry_before)
                        )
                    ),
                    (
                        (IpoDocument.storage_status == "DOWNLOADING")
                        & (IpoDocument.storage_attempted_at <= stale_before)
                    ),
                    stored_needs_processing,
                ),
            )
            .order_by(IpoDocument.id)
            .limit(settings.rhp_archive_batch_size)
        ).all()
        work = [
            (
                item.id,
                item.ipo_id,
                item.ipo.open_date,
                item.storage_status,
                item.storage_key,
                item.content_sha256,
                item.source_content_type,
                item.final_source_url or item.url,
            )
            for item in documents
        ]

    stored = 0
    failed = 0
    for (
        document_id,
        ipo_id,
        open_date,
        initial_storage_status,
        stored_object_key,
        stored_sha256,
        stored_content_type,
        stored_final_url,
    ) in work:
        reuse_stored_pdf = initial_storage_status == "STORED" and bool(stored_object_key)
        with SessionLocal() as db:
            document = db.get(IpoDocument, document_id)
            document.storage_status = "DOWNLOADING"
            document.storage_attempts = (document.storage_attempts or 0) + 1
            document.storage_attempted_at = datetime.now(UTC)
            document.storage_error = None
            source_url = document.url
            db.commit()

        downloaded: DownloadedPdf | None = None
        try:
            year = open_date.year if open_date else datetime.now(UTC).year
            if reuse_stored_pdf:
                downloaded = await asyncio.to_thread(
                    _download_stored_pdf,
                    stored_object_key,
                    stored_sha256,
                    stored_content_type,
                    stored_final_url,
                    settings,
                )
                object_key = stored_object_key
            else:
                downloaded = await download_rhp(source_url, settings)
                object_key = f"rhp/{year}/{ipo_id}/{downloaded.sha256}.pdf"
                await asyncio.to_thread(_upload_pdf, downloaded, object_key, settings)

            inspection: PdfInspection | None = None
            inspection_error: PdfInspectionError | None = None
            decision: PdfProcessingDecision | None = None
            prepared_files: list[tuple[PreparedPdf, str]] = []
            preparation_error: str | None = None
            preparation_warning: str | None = None
            try:
                inspection = await asyncio.to_thread(inspect_pdf, downloaded.path)
                decision = choose_pdf_processing_path(
                    inspection.size_bytes,
                    inspection.page_count,
                    max_bytes=settings.gemini_safe_pdf_bytes,
                    max_pages=settings.gemini_max_pdf_pages,
                )
            except PdfInspectionError as exc:
                inspection_error = exc

            if inspection is not None:
                try:
                    with tempfile.TemporaryDirectory(
                        prefix="ipodekho-rhp-processing-"
                    ) as directory:
                        prepared_set = await asyncio.to_thread(
                            prepare_pdf_for_gemini,
                            downloaded.path,
                            inspection,
                            Path(directory),
                            direct_max_bytes=settings.gemini_safe_pdf_bytes,
                            direct_max_pages=settings.gemini_max_pdf_pages,
                            chunk_max_bytes=settings.rhp_chunk_max_bytes,
                            chunk_max_pages=settings.rhp_chunk_max_pages,
                        )
                        preparation_warning = prepared_set.optimization_error
                        for prepared in prepared_set.files:
                            if prepared.kind == "ORIGINAL":
                                processing_key = object_key
                            else:
                                filename = (
                                    f"chunk-{prepared.chunk_index:04d}-{prepared.sha256}.pdf"
                                    if prepared.chunk_index is not None
                                    else f"optimized-{prepared.sha256}.pdf"
                                )
                                processing_key = (
                                    f"rhp-processing/{year}/{ipo_id}/{downloaded.sha256}/{filename}"
                                )
                                await asyncio.to_thread(
                                    _upload_local_pdf,
                                    prepared.path,
                                    processing_key,
                                    prepared.sha256,
                                    settings,
                                    metadata={
                                        "kind": prepared.kind.lower(),
                                        "original-start-page": str(prepared.original_start_page),
                                        "original-end-page": str(prepared.original_end_page),
                                    },
                                )
                            prepared_files.append((prepared, processing_key))
                except PdfPreparationError as exc:
                    preparation_error = str(exc)

            with SessionLocal() as db:
                document = db.get(IpoDocument, document_id)
                document.storage_status = "STORED"
                document.storage_key = object_key
                document.content_sha256 = downloaded.sha256
                document.size_bytes = downloaded.size_bytes
                document.source_content_type = downloaded.source_content_type
                document.final_source_url = downloaded.final_url
                document.storage_error = None
                document.stored_at = datetime.now(UTC)
                document.pdf_page_count = inspection.page_count if inspection else None
                document.pdf_encrypted = (
                    inspection.encrypted if inspection else inspection_error.encrypted
                )
                document.pdf_malformed = bool(inspection_error and not inspection_error.encrypted)
                document.pdf_inspection_status = (
                    "INSPECTED"
                    if inspection
                    else "ENCRYPTED"
                    if inspection_error.encrypted
                    else "MALFORMED"
                )
                document.pdf_processing_decision = decision.value if decision else None
                document.gemini_direct_eligible = decision == PdfProcessingDecision.DIRECT
                document.pdf_inspection_error = (
                    str(inspection_error)[:4000] if inspection_error else None
                )
                document.pdf_inspected_at = datetime.now(UTC)
                document.processing_files.clear()
                for prepared, processing_key in prepared_files:
                    document.processing_files.append(
                        RhpProcessingFile(
                            kind=prepared.kind,
                            chunk_index=prepared.chunk_index,
                            storage_key=processing_key,
                            content_sha256=prepared.sha256,
                            size_bytes=prepared.size_bytes,
                            page_count=prepared.page_count,
                            original_start_page=prepared.original_start_page,
                            original_end_page=prepared.original_end_page,
                        )
                    )
                if inspection_error:
                    document.pdf_processing_status = "BLOCKED"
                    document.pdf_processing_error = str(inspection_error)[:4000]
                elif preparation_error:
                    document.pdf_processing_status = "FAILED"
                    document.pdf_processing_error = preparation_error[:4000]
                elif preparation_warning:
                    document.pdf_processing_status = "READY_WITH_WARNINGS"
                    document.pdf_processing_error = preparation_warning[:4000]
                else:
                    document.pdf_processing_status = "READY"
                    document.pdf_processing_error = None
                document.pdf_processing_prepared_at = datetime.now(UTC)
                db.commit()
            if (
                ready_document_ids is not None
                and prepared_files
                and not inspection_error
                and not preparation_error
            ):
                ready_document_ids.add(document_id)
            stored += 1
        except Exception as exc:
            status = (
                "STORED"
                if reuse_stored_pdf
                else "REJECTED"
                if isinstance(exc, RhpRejectedError)
                else "FAILED"
            )
            with SessionLocal() as db:
                document = db.get(IpoDocument, document_id)
                document.storage_status = status
                document.storage_error = str(exc)[:4000]
                if reuse_stored_pdf:
                    document.pdf_processing_status = "FAILED"
                    document.pdf_processing_error = str(exc)[:4000]
                db.commit()
            failed += 1
            logger.exception(
                "rhp_archive_failed",
                extra={"ipo_id": ipo_id, "document_id": document_id, "status": status},
            )
        finally:
            if downloaded is not None:
                downloaded.cleanup()

    return stored, failed
