import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.services.rhp.inspector import (
    PdfInspection,
    PdfProcessingDecision,
    choose_pdf_processing_path,
    inspect_pdf,
)
from app.services.rhp.optimizer import PdfOptimizationError, optimize_pdf
from app.services.rhp.splitter import UnprocessablePdfError, split_pdf_byte_aware


class PdfPreparationError(Exception):
    pass


@dataclass(frozen=True)
class PreparedPdf:
    path: Path
    kind: str
    chunk_index: int | None
    original_start_page: int
    original_end_page: int
    page_count: int
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class PreparedPdfSet:
    files: list[PreparedPdf]
    optimization_error: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _prepared(
    path: Path,
    *,
    kind: str,
    chunk_index: int | None,
    start_page: int,
    end_page: int,
    page_count: int,
    size_bytes: int,
) -> PreparedPdf:
    return PreparedPdf(
        path=path,
        kind=kind,
        chunk_index=chunk_index,
        original_start_page=start_page,
        original_end_page=end_page,
        page_count=page_count,
        size_bytes=size_bytes,
        sha256=_sha256(path),
    )


def prepare_pdf_for_gemini(
    source: Path,
    inspection: PdfInspection,
    output_dir: Path,
    *,
    direct_max_bytes: int,
    direct_max_pages: int,
    chunk_max_bytes: int,
    chunk_max_pages: int,
) -> PreparedPdfSet:
    """Return direct, optimized, or byte-aware split PDFs with original-page mappings."""
    decision = choose_pdf_processing_path(
        inspection.size_bytes,
        inspection.page_count,
        max_bytes=direct_max_bytes,
        max_pages=direct_max_pages,
    )
    if decision == PdfProcessingDecision.DIRECT:
        return PreparedPdfSet(
            files=[
                _prepared(
                    source,
                    kind="ORIGINAL",
                    chunk_index=None,
                    start_page=1,
                    end_page=inspection.page_count,
                    page_count=inspection.page_count,
                    size_bytes=inspection.size_bytes,
                )
            ]
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    split_source = source
    optimization_error: str | None = None

    if inspection.size_bytes > direct_max_bytes:
        optimized_path = output_dir / "optimized.pdf"
        try:
            optimize_pdf(source, optimized_path)
            optimized_inspection = inspect_pdf(optimized_path)
            if optimized_inspection.page_count != inspection.page_count:
                raise PdfOptimizationError("PDF optimization changed the page count")
            optimized_decision = choose_pdf_processing_path(
                optimized_inspection.size_bytes,
                optimized_inspection.page_count,
                max_bytes=direct_max_bytes,
                max_pages=direct_max_pages,
            )
            if optimized_decision == PdfProcessingDecision.DIRECT:
                return PreparedPdfSet(
                    files=[
                        _prepared(
                            optimized_path,
                            kind="OPTIMIZED",
                            chunk_index=None,
                            start_page=1,
                            end_page=optimized_inspection.page_count,
                            page_count=optimized_inspection.page_count,
                            size_bytes=optimized_inspection.size_bytes,
                        )
                    ]
                )
            if optimized_inspection.size_bytes < inspection.size_bytes:
                split_source = optimized_path
        except Exception as exc:
            optimization_error = str(exc)
            optimized_path.unlink(missing_ok=True)

    try:
        chunks = split_pdf_byte_aware(
            split_source,
            output_dir / "chunks",
            max_pages=chunk_max_pages,
            max_bytes=chunk_max_bytes,
        )
    except UnprocessablePdfError as exc:
        raise PdfPreparationError(str(exc)) from exc

    files = [
        _prepared(
            chunk.path,
            kind="CHUNK",
            chunk_index=chunk.chunk_index,
            start_page=chunk.original_start_page,
            end_page=chunk.original_end_page,
            page_count=chunk.page_count,
            size_bytes=chunk.size_bytes,
        )
        for chunk in chunks
    ]
    unsafe_file_exists = any(
        file.size_bytes > chunk_max_bytes or file.page_count > chunk_max_pages
        for file in files
    )
    if unsafe_file_exists:
        raise PdfPreparationError("Generated PDF chunks exceed configured safety limits")
    return PreparedPdfSet(files=files, optimization_error=optimization_error)
