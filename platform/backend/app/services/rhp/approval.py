"""Auditable human review and approval transitions for warning-bearing runs."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import IpoExtractionRun

REVIEW_DISPOSITIONS = {"ACCEPTED", "CORRECTED", "SKIPPED"}


def validate_review_resolutions(
    issues: list[dict], resolutions: list[dict[str, str]]
) -> list[dict[str, str]]:
    if len(resolutions) != len(issues):
        raise ValueError("Every validation issue requires exactly one review resolution")
    validated: list[dict[str, str]] = []
    for issue, resolution in zip(issues, resolutions, strict=True):
        issue_code = str(resolution.get("issue_code", "")).strip()
        disposition = str(resolution.get("disposition", "")).strip().upper()
        note = str(resolution.get("note", "")).strip()
        if issue_code != issue.get("code"):
            raise ValueError(f"Expected a resolution for issue {issue.get('code')}")
        if disposition not in REVIEW_DISPOSITIONS:
            raise ValueError(f"Unsupported review disposition: {disposition}")
        if not note:
            raise ValueError(f"Review resolution {issue_code} requires a note")
        validated.append(
            {"issue_code": issue_code, "disposition": disposition, "note": note[:1000]}
        )
    return validated


def review_extraction_run(
    run_id: int,
    *,
    reviewer: str,
    resolutions: list[dict[str, str]],
) -> None:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer is required")
    with SessionLocal() as db:
        run = db.scalar(
            select(IpoExtractionRun)
            .options(selectinload(IpoExtractionRun.metrics))
            .where(IpoExtractionRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise ValueError(f"Extraction run {run_id} does not exist")
        if run.status != "READY_WITH_WARNINGS":
            raise ValueError("Only READY_WITH_WARNINGS runs can transition to REVIEWED")
        issues = run.validation_issues or []
        if not issues:
            raise ValueError("Warning-bearing run has no issues to review")
        validated = validate_review_resolutions(issues, resolutions)
        run.status = "REVIEWED"
        run.reviewed_at = datetime.now(UTC)
        run.reviewed_by = reviewer[:200]
        run.review_resolutions = validated
        run.job.status = "REVIEWED"
        for metric in run.metrics:
            metric.verification_status = "REVIEWED"
        db.commit()


def approve_extraction_run(run_id: int, *, approver: str) -> None:
    approver = approver.strip()
    if not approver:
        raise ValueError("approver is required")
    with SessionLocal() as db:
        run = db.scalar(
            select(IpoExtractionRun)
            .options(selectinload(IpoExtractionRun.metrics))
            .where(IpoExtractionRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise ValueError(f"Extraction run {run_id} does not exist")
        if run.status != "REVIEWED":
            raise ValueError("Only REVIEWED runs can transition to APPROVED")
        if not run.review_resolutions:
            raise ValueError("Reviewed run is missing issue resolutions")
        run.status = "APPROVED"
        run.approved_at = datetime.now(UTC)
        run.approved_by = approver[:200]
        run.job.status = "APPROVED"
        for metric in run.metrics:
            metric.verification_status = "APPROVED"
        db.commit()
