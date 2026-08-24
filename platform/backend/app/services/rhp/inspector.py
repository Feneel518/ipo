from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pypdf import PdfReader


class PdfInspectionError(Exception):
    """The PDF cannot be inspected safely enough for downstream processing."""

    def __init__(self, message: str, *, encrypted: bool = False) -> None:
        super().__init__(message)
        self.encrypted = encrypted


class PdfProcessingDecision(StrEnum):
    DIRECT = "DIRECT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TOO_MANY_PAGES = "TOO_MANY_PAGES"
    TOO_LARGE_AND_TOO_MANY_PAGES = "TOO_LARGE_AND_TOO_MANY_PAGES"


@dataclass(frozen=True)
class PdfInspection:
    size_bytes: int
    page_count: int
    encrypted: bool


def inspect_pdf(path: Path) -> PdfInspection:
    """Parse enough of a local PDF to establish its Gemini processing constraints."""
    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        raise PdfInspectionError(f"Unable to read PDF: {exc}") from exc

    try:
        reader = PdfReader(str(path), strict=False)
    except Exception as exc:
        raise PdfInspectionError(f"Unable to parse PDF: {exc}") from exc

    encrypted = reader.is_encrypted
    if encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise PdfInspectionError(
                "PDF is encrypted and cannot be opened", encrypted=True
            ) from exc
        if not unlocked:
            raise PdfInspectionError("PDF requires a password", encrypted=True)

    try:
        page_count = len(reader.pages)
    except Exception as exc:
        raise PdfInspectionError(
            f"Unable to read PDF pages: {exc}", encrypted=encrypted
        ) from exc

    if page_count <= 0:
        raise PdfInspectionError("PDF contains no pages", encrypted=encrypted)

    return PdfInspection(
        size_bytes=size_bytes,
        page_count=page_count,
        encrypted=encrypted,
    )


def choose_pdf_processing_path(
    size_bytes: int,
    page_count: int,
    *,
    max_bytes: int,
    max_pages: int,
) -> PdfProcessingDecision:
    """Return an explicit decision; values exactly at either limit remain direct."""
    too_large = size_bytes > max_bytes
    too_many_pages = page_count > max_pages

    if too_large and too_many_pages:
        return PdfProcessingDecision.TOO_LARGE_AND_TOO_MANY_PAGES
    if too_large:
        return PdfProcessingDecision.FILE_TOO_LARGE
    if too_many_pages:
        return PdfProcessingDecision.TOO_MANY_PAGES
    return PdfProcessingDecision.DIRECT
