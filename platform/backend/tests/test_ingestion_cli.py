from types import SimpleNamespace

import pytest

from app.ingestion import cli


@pytest.mark.asyncio
async def test_automatic_pipeline_runs_extraction_when_gemini_is_configured(monkeypatch):
    calls = []

    async def fake_ingestion(year, *, ready_rhp_document_ids):
        calls.append(("ingest", year))
        ready_rhp_document_ids.update({42, 7})
        return True

    async def fake_extraction(settings, *, limit, document_id):
        calls.append(("extract", document_id, limit, settings))
        return 1, 1, 0

    settings = SimpleNamespace(gemini_configured=True)
    monkeypatch.setattr(cli, "run_ingestion", fake_ingestion)
    monkeypatch.setattr(cli, "process_extraction_batch_async", fake_extraction)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert await cli.run_automatic_pipeline(2026)
    assert calls == [
        ("ingest", 2026),
        ("extract", 7, 1, settings),
        ("extract", 42, 1, settings),
    ]


@pytest.mark.asyncio
async def test_automatic_pipeline_skips_extraction_without_gemini(monkeypatch):
    async def fake_ingestion(year, *, ready_rhp_document_ids):
        ready_rhp_document_ids.add(7)
        return True

    async def unexpected_extraction(settings, **kwargs):
        raise AssertionError("Gemini extraction should not run without credentials")

    monkeypatch.setattr(cli, "run_ingestion", fake_ingestion)
    monkeypatch.setattr(cli, "process_extraction_batch_async", unexpected_extraction)
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(gemini_configured=False),
    )

    assert await cli.run_automatic_pipeline()


@pytest.mark.asyncio
async def test_automatic_pipeline_skips_extraction_when_no_rhp_was_added(monkeypatch):
    async def fake_ingestion(year, *, ready_rhp_document_ids):
        return True

    async def unexpected_extraction(settings, **kwargs):
        raise AssertionError("Gemini extraction should only run for a newly stored RHP")

    monkeypatch.setattr(cli, "run_ingestion", fake_ingestion)
    monkeypatch.setattr(cli, "process_extraction_batch_async", unexpected_extraction)
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(gemini_configured=True),
    )

    assert await cli.run_automatic_pipeline()


@pytest.mark.asyncio
async def test_automatic_pipeline_reports_extraction_failures(monkeypatch):
    async def fake_ingestion(year, *, ready_rhp_document_ids):
        ready_rhp_document_ids.add(7)
        return True

    async def fake_extraction(settings, **kwargs):
        return 1, 0, 1

    monkeypatch.setattr(cli, "run_ingestion", fake_ingestion)
    monkeypatch.setattr(cli, "process_extraction_batch_async", fake_extraction)
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(gemini_configured=True),
    )

    assert not await cli.run_automatic_pipeline()


@pytest.mark.asyncio
async def test_automatic_pipeline_reports_worker_errors(monkeypatch):
    async def fake_ingestion(year, *, ready_rhp_document_ids):
        ready_rhp_document_ids.add(7)
        return True

    async def fake_extraction(settings, **kwargs):
        raise RuntimeError("R2 unavailable")

    monkeypatch.setattr(cli, "run_ingestion", fake_ingestion)
    monkeypatch.setattr(cli, "process_extraction_batch_async", fake_extraction)
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(gemini_configured=True),
    )

    assert not await cli.run_automatic_pipeline()
