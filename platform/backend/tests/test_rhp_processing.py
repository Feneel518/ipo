from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.services.rhp.inspector import inspect_pdf
from app.services.rhp.optimizer import optimize_pdf
from app.services.rhp.preparer import prepare_pdf_for_gemini
from app.services.rhp.splitter import UnprocessablePdfError, split_pdf_byte_aware


def write_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as target:
        writer.write(target)


def test_structural_optimization_preserves_pages(tmp_path):
    source = tmp_path / "source.pdf"
    destination = tmp_path / "optimized.pdf"
    write_pdf(source, 4)

    optimize_pdf(source, destination)

    assert destination.exists()
    assert inspect_pdf(destination).page_count == 4


def test_page_split_preserves_original_page_mapping(tmp_path):
    source = tmp_path / "source.pdf"
    write_pdf(source, 7)

    chunks = split_pdf_byte_aware(
        source,
        tmp_path / "chunks",
        max_pages=3,
        max_bytes=1024 * 1024,
    )

    assert [(item.original_start_page, item.original_end_page) for item in chunks] == [
        (1, 3),
        (4, 6),
        (7, 7),
    ]
    assert all(item.page_count <= 3 for item in chunks)
    assert sum(item.page_count for item in chunks) == 7


def test_oversized_chunk_is_recursively_split_by_bytes(tmp_path):
    source = tmp_path / "source.pdf"
    one_page = tmp_path / "one.pdf"
    two_pages = tmp_path / "two.pdf"
    write_pdf(source, 4)
    write_pdf(one_page, 1)
    write_pdf(two_pages, 2)
    byte_limit = (one_page.stat().st_size + two_pages.stat().st_size) // 2

    chunks = split_pdf_byte_aware(
        source,
        tmp_path / "chunks",
        max_pages=4,
        max_bytes=byte_limit,
    )

    assert len(chunks) == 4
    assert all(item.page_count == 1 for item in chunks)
    assert all(item.size_bytes <= byte_limit for item in chunks)
    assert [(item.original_start_page, item.original_end_page) for item in chunks] == [
        (1, 1),
        (2, 2),
        (3, 3),
        (4, 4),
    ]


def test_single_page_over_byte_limit_is_rejected(tmp_path):
    source = tmp_path / "source.pdf"
    write_pdf(source, 1)

    with pytest.raises(UnprocessablePdfError, match="Original page 1 exceeds"):
        split_pdf_byte_aware(
            source,
            tmp_path / "chunks",
            max_pages=1,
            max_bytes=10,
        )


def test_preparer_creates_safe_chunks_for_too_many_pages(tmp_path):
    source = tmp_path / "source.pdf"
    write_pdf(source, 5)
    inspection = inspect_pdf(source)

    prepared = prepare_pdf_for_gemini(
        source,
        inspection,
        tmp_path / "processing",
        direct_max_bytes=1024 * 1024,
        direct_max_pages=2,
        chunk_max_bytes=1024 * 1024,
        chunk_max_pages=2,
    )

    assert [item.kind for item in prepared.files] == ["CHUNK", "CHUNK", "CHUNK"]
    assert [(item.original_start_page, item.original_end_page) for item in prepared.files] == [
        (1, 2),
        (3, 4),
        (5, 5),
    ]
    assert all(item.page_count <= 2 for item in prepared.files)
    assert all(item.path.exists() for item in prepared.files)


def test_preparer_uses_smaller_optimized_pdf_when_it_fits(tmp_path):
    source = tmp_path / "source.pdf"
    optimized_probe = tmp_path / "optimized-probe.pdf"
    write_pdf(source, 20)
    optimize_pdf(source, optimized_probe)
    direct_byte_limit = (source.stat().st_size + optimized_probe.stat().st_size) // 2
    assert optimized_probe.stat().st_size < direct_byte_limit < source.stat().st_size

    prepared = prepare_pdf_for_gemini(
        source,
        inspect_pdf(source),
        tmp_path / "processing",
        direct_max_bytes=direct_byte_limit,
        direct_max_pages=1000,
        chunk_max_bytes=1024 * 1024,
        chunk_max_pages=300,
    )

    assert len(prepared.files) == 1
    assert prepared.files[0].kind == "OPTIMIZED"
    assert prepared.files[0].page_count == 20
    assert prepared.files[0].size_bytes <= direct_byte_limit
