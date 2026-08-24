from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter


class UnprocessablePdfError(Exception):
    pass


@dataclass(frozen=True)
class PdfChunk:
    path: Path
    chunk_index: int
    original_start_page: int
    original_end_page: int
    page_count: int
    size_bytes: int


def _write_page_range(reader: PdfReader, destination: Path, start: int, end: int) -> int:
    writer = PdfWriter()
    for page_index in range(start, end):
        writer.add_page(reader.pages[page_index])
    with destination.open("wb") as handle:
        writer.write(handle)
    return destination.stat().st_size


def split_pdf_byte_aware(
    source: Path,
    output_dir: Path,
    *,
    max_pages: int = 300,
    max_bytes: int = 40 * 1024 * 1024,
) -> list[PdfChunk]:
    """Split a PDF until every chunk satisfies both page and byte limits."""
    if max_pages <= 0 or max_bytes <= 0:
        raise ValueError("PDF chunk limits must be positive")

    try:
        reader = PdfReader(str(source), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise UnprocessablePdfError("PDF requires a password")
        total_pages = len(reader.pages)
    except UnprocessablePdfError:
        raise
    except Exception as exc:
        raise UnprocessablePdfError(f"Unable to split PDF: {exc}") from exc

    if total_pages <= 0:
        raise UnprocessablePdfError("PDF contains no pages")

    output_dir.mkdir(parents=True, exist_ok=True)
    accepted: list[tuple[Path, int, int, int]] = []
    attempt = 0

    def ensure_safe(start: int, end: int) -> None:
        nonlocal attempt
        attempt += 1
        path = output_dir / f"candidate_{attempt:04d}_{start + 1:06d}_{end:06d}.pdf"
        try:
            size_bytes = _write_page_range(reader, path, start, end)
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise UnprocessablePdfError(f"Unable to write PDF chunk: {exc}") from exc

        page_count = end - start
        if page_count <= max_pages and size_bytes <= max_bytes:
            accepted.append((path, start, end, size_bytes))
            return

        path.unlink(missing_ok=True)
        if page_count <= 1:
            raise UnprocessablePdfError(
                f"Original page {start + 1} exceeds the {max_bytes}-byte chunk limit"
            )

        midpoint = start + page_count // 2
        ensure_safe(start, midpoint)
        ensure_safe(midpoint, end)

    for range_start in range(0, total_pages, max_pages):
        ensure_safe(range_start, min(range_start + max_pages, total_pages))

    return [
        PdfChunk(
            path=path,
            chunk_index=index,
            original_start_page=start + 1,
            original_end_page=end,
            page_count=end - start,
            size_bytes=size_bytes,
        )
        for index, (path, start, end, size_bytes) in enumerate(accepted)
    ]
