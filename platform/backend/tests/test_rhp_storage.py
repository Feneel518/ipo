import hashlib
import zipfile

import pytest

from app.config import Settings
from app.ingestion.rhp_storage import (
    RhpRejectedError,
    _extract_pdf_from_zip,
    _host_is_allowed,
    _upload_pdf,
    is_rhp_document,
    should_archive_rhp,
)
from app.models import Lifecycle


def fake_pdf(label: bytes = b"RHP") -> bytes:
    return b"%PDF-1.7\n" + label + b"\n" + (b"0" * 2048) + b"\n%%EOF"


def test_only_rhp_documents_are_queued():
    assert is_rhp_document("RHP", "Offer document")
    assert is_rhp_document("OFFER_DOCUMENT", "Red Herring Prospectus")
    assert is_rhp_document("PROSPECTUS", "Company RHP filing")
    assert not is_rhp_document("DRHP", "Draft prospectus")
    assert not is_rhp_document("ADVERTISEMENT", "Issue advertisement")


def test_only_upcoming_and_open_rhps_are_archived():
    assert should_archive_rhp(Lifecycle.UPCOMING, "RHP", "Offer document")
    assert should_archive_rhp(Lifecycle.OPEN, "RHP", "Offer document")
    assert not should_archive_rhp(Lifecycle.CLOSED, "RHP", "Offer document")
    assert not should_archive_rhp(Lifecycle.LISTED, "RHP", "Offer document")
    assert not should_archive_rhp(Lifecycle.OPEN, "ADVERTISEMENT", "Issue advertisement")


def test_allowed_host_matching_does_not_accept_suffix_confusion():
    assert _host_is_allowed("www.nseindia.com", ["nseindia.com"])
    assert not _host_is_allowed("nseindia.com.attacker.test", ["nseindia.com"])
    assert not _host_is_allowed("fakenseindia.com", ["nseindia.com"])


def test_zip_transport_extracts_preferred_rhp_pdf_only(tmp_path):
    archive_path = tmp_path / "exchange-response.zip"
    expected = fake_pdf(b"CANONICAL RHP")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("annexure.pdf", fake_pdf(b"ANNEXURE") * 2)
        archive.writestr("company-rhp.pdf", expected)
        archive.writestr("readme.txt", "not stored")

    extracted = _extract_pdf_from_zip(archive_path, max_bytes=10 * 1024 * 1024)
    try:
        assert extracted.suffix == ".pdf"
        assert extracted.read_bytes() == expected
        assert hashlib.sha256(extracted.read_bytes()).hexdigest()
    finally:
        extracted.unlink(missing_ok=True)


def test_zip_without_pdf_is_rejected(tmp_path):
    archive_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("readme.txt", "no prospectus here")

    with pytest.raises(RhpRejectedError, match="does not contain a PDF"):
        _extract_pdf_from_zip(archive_path, max_bytes=1024 * 1024)


def test_r2_upload_forces_pdf_content_type(monkeypatch, tmp_path):
    pdf_path = tmp_path / "rhp.pdf"
    pdf_path.write_bytes(fake_pdf())
    calls = []

    class FakeClient:
        def upload_file(self, filename, bucket, key, ExtraArgs):
            calls.append((filename, bucket, key, ExtraArgs))

    monkeypatch.setattr("app.ingestion.rhp_storage._r2_client", lambda settings: FakeClient())
    from app.ingestion.rhp_storage import DownloadedPdf

    downloaded = DownloadedPdf(
        path=pdf_path,
        sha256="a" * 64,
        size_bytes=pdf_path.stat().st_size,
        source_content_type="application/zip",
        final_url="https://www.bseindia.com/rhp.zip",
    )
    settings = Settings(
        r2_bucket="ipo",
        r2_endpoint_url="https://account.r2.cloudflarestorage.com",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
    )

    _upload_pdf(downloaded, "rhp/2026/1/hash.pdf", settings)

    assert calls[0][1:3] == ("ipo", "rhp/2026/1/hash.pdf")
    assert calls[0][3]["ContentType"] == "application/pdf"
    assert calls[0][3]["ContentDisposition"] == "inline"


def test_r2_delete_uses_the_recorded_object_key(monkeypatch):
    calls = []

    class FakeClient:
        def delete_object(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("app.ingestion.rhp_storage._r2_client", lambda settings: FakeClient())
    from app.ingestion.rhp_storage import _delete_object

    settings = Settings(
        r2_bucket="ipo",
        r2_endpoint_url="https://account.r2.cloudflarestorage.com",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
    )
    _delete_object("rhp/2026/1/hash.pdf", settings)

    assert calls == [{"Bucket": "ipo", "Key": "rhp/2026/1/hash.pdf"}]
