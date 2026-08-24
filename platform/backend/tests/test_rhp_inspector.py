from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.services.rhp.inspector import (
    PdfInspectionError,
    PdfProcessingDecision,
    choose_pdf_processing_path,
    inspect_pdf,
)


def write_pdf(path: Path, pages: int = 1, password: str | None = None) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if password is not None:
        writer.encrypt(password)
    with path.open("wb") as target:
        writer.write(target)


def test_inspect_pdf_records_size_pages_and_encryption(tmp_path):
    path = tmp_path / "rhp.pdf"
    write_pdf(path, pages=3)

    result = inspect_pdf(path)

    assert result.size_bytes == path.stat().st_size
    assert result.page_count == 3
    assert result.encrypted is False


def test_empty_password_encrypted_pdf_can_be_inspected(tmp_path):
    path = tmp_path / "encrypted.pdf"
    write_pdf(path, pages=2, password="")

    result = inspect_pdf(path)

    assert result.page_count == 2
    assert result.encrypted is True


def test_password_protected_pdf_is_flagged(tmp_path):
    path = tmp_path / "encrypted.pdf"
    write_pdf(path, password="secret")

    with pytest.raises(PdfInspectionError, match="requires a password") as caught:
        inspect_pdf(path)

    assert caught.value.encrypted is True


def test_malformed_pdf_is_flagged(tmp_path):
    path = tmp_path / "malformed.pdf"
    path.write_bytes(b"%PDF-1.7\nnot a valid document\n%%EOF")

    with pytest.raises(PdfInspectionError, match="Unable to parse PDF") as caught:
        inspect_pdf(path)

    assert caught.value.encrypted is False


@pytest.mark.parametrize(
    ("size_bytes", "page_count", "expected"),
    [
        (45, 1000, PdfProcessingDecision.DIRECT),
        (46, 1000, PdfProcessingDecision.FILE_TOO_LARGE),
        (45, 1001, PdfProcessingDecision.TOO_MANY_PAGES),
        (46, 1001, PdfProcessingDecision.TOO_LARGE_AND_TOO_MANY_PAGES),
    ],
)
def test_processing_decision_is_explicit(size_bytes, page_count, expected):
    assert (
        choose_pdf_processing_path(
            size_bytes,
            page_count,
            max_bytes=45,
            max_pages=1000,
        )
        == expected
    )
