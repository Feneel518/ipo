"""Opt-in five-document acceptance test.

Run only with an intentionally selected corpus and API key:

RUN_LIVE_GEMINI_TESTS=1 RHP_TEST_PDF_DIR=/path/to/five-rhps pytest -m live_gemini -q
"""

import os
from pathlib import Path

import pytest
from google import genai

from app.services.rhp.gemini import (
    delete_gemini_file,
    extract_rhp_v1,
    upload_pdf_to_gemini,
    wait_for_gemini_file,
)
from app.services.rhp.inspector import inspect_pdf
from app.services.rhp.validation import validate_extraction


@pytest.mark.live_gemini
def test_five_real_single_file_rhps():
    if os.getenv("RUN_LIVE_GEMINI_TESTS") != "1":
        pytest.skip("set RUN_LIVE_GEMINI_TESTS=1 to incur live Gemini API usage")
    api_key = os.getenv("GEMINI_API_KEY")
    corpus_dir = os.getenv("RHP_TEST_PDF_DIR")
    if not api_key or not corpus_dir:
        pytest.fail("GEMINI_API_KEY and RHP_TEST_PDF_DIR are required")

    paths = sorted(Path(corpus_dir).glob("*.pdf"))
    assert len(paths) == 5, "the acceptance corpus must contain exactly five PDFs"
    client = genai.Client(api_key=api_key)
    try:
        for path in paths:
            inspection = inspect_pdf(path)
            assert inspection.size_bytes <= 45 * 1024 * 1024
            assert inspection.page_count <= 1000
            uploaded = upload_pdf_to_gemini(client, path)
            try:
                ready = wait_for_gemini_file(client, uploaded.name)
                generated = extract_rhp_v1(
                    client,
                    ready,
                    model="gemini-3.5-flash-lite",
                )
                issues = validate_extraction(
                    generated.extraction,
                    page_count=inspection.page_count,
                )
                assert generated.raw_json
                assert not issues, f"{path.name}: {issues}"
            finally:
                delete_gemini_file(client, uploaded.name)
    finally:
        client.close()
