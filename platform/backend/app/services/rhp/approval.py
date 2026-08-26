"""Auditable human review and approval transitions for warning-bearing runs."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import IpoExtractionRun

REVIEW_DISPOSITIONS = {"ACCEPTED", "CORRECTED", "SKIPPED"}
AUTO_APPROVER = "system:auto-approval"


def automatic_review_resolutions(issues: list[dict]) -> list[dict[str, str]]:
    """Accept every issue under the operator-configured automatic policy."""
    return [
        {
            "issue_code": str(issue.get("code", "UNKNOWN")),
            "disposition": "ACCEPTED",
            "note": "Automatically accepted by the configured RHP publication policy.",
        }
        for issue in issues
    ]


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


def auto_approve_extraction_run(run_id: int) -> None:
    """Apply an auditable system review and approval to a warning-bearing run."""
    with SessionLocal() as db:
        run = db.get(IpoExtractionRun, run_id)
        if run is None:
            raise ValueError(f"Extraction run {run_id} does not exist")
        if run.status == "APPROVED":
            return
        if run.status == "READY_WITH_WARNINGS":
            issues = run.validation_issues or []
        elif run.status == "REVIEWED":
            issues = []
        else:
            raise ValueError("Only READY_WITH_WARNINGS or REVIEWED runs can be auto-approved")
    if issues:
        review_extraction_run(
            run_id,
            reviewer=AUTO_APPROVER,
            resolutions=automatic_review_resolutions(issues),
        )
    approve_extraction_run(run_id, approver=AUTO_APPROVER)


def auto_approve_pending_extractions() -> tuple[int, int]:
    """Approve pending rows for the currently configured extraction version."""
    from app.config import get_settings

    settings = get_settings()
    with SessionLocal() as db:
        run_ids = db.scalars(
            select(IpoExtractionRun.id)
            .where(
                IpoExtractionRun.status.in_(["READY_WITH_WARNINGS", "REVIEWED"]),
                IpoExtractionRun.model == settings.rhp_primary_model,
                IpoExtractionRun.prompt_version == settings.rhp_prompt_version,
                IpoExtractionRun.schema_version == settings.rhp_schema_version,
            )
            .order_by(IpoExtractionRun.id)
        ).all()
    approved = failed = 0
    for run_id in run_ids:
        try:
            auto_approve_extraction_run(run_id)
            approved += 1
        except Exception:
            failed += 1
    return approved, failed
