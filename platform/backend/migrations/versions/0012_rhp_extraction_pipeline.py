"""Add versioned RHP extraction jobs, runs, and canonical metrics.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ipo_extraction_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("document_sha256", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="QUEUED", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["ipo_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_sha256",
            "model",
            "prompt_version",
            "schema_version",
            name="uq_ipo_extraction_job_identity",
        ),
    )
    op.create_index("ix_ipo_extraction_jobs_document_id", "ipo_extraction_jobs", ["document_id"])
    op.create_index(
        "ix_ipo_extraction_jobs_document_sha256",
        "ipo_extraction_jobs",
        ["document_sha256"],
    )
    op.create_index("ix_ipo_extraction_jobs_status", "ipo_extraction_jobs", ["status"])
    op.create_index(
        "ix_ipo_extraction_jobs_next_attempt_at",
        "ipo_extraction_jobs",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_ipo_extraction_jobs_claim",
        "ipo_extraction_jobs",
        ["status", "next_attempt_at", "created_at"],
    )

    op.create_table(
        "ipo_extraction_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("processing_file_id", sa.BigInteger(), nullable=True),
        sa.Column("document_sha256", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("validation_issues", sa.JSON(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("request_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("gemini_file_name", sa.Text(), nullable=True),
        sa.Column("gemini_file_uri", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["ipo_extraction_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["ipo_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["processing_file_id"], ["rhp_processing_files.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ipo_extraction_runs_job_id", "ipo_extraction_runs", ["job_id"])
    op.create_index(
        "ix_ipo_extraction_runs_document_id", "ipo_extraction_runs", ["document_id"]
    )
    op.create_index(
        "ix_ipo_extraction_runs_processing_file_id",
        "ipo_extraction_runs",
        ["processing_file_id"],
    )
    op.create_index("ix_ipo_extraction_runs_status", "ipo_extraction_runs", ["status"])
    op.create_index(
        "ix_ipo_extraction_runs_identity",
        "ipo_extraction_runs",
        ["document_sha256", "model"],
    )

    op.create_table(
        "ipo_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ipo_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("extraction_run_id", sa.BigInteger(), nullable=False),
        sa.Column("metric", sa.String(length=100), nullable=False),
        sa.Column("financial_year", sa.String(length=20), nullable=True),
        sa.Column("numeric_value", sa.Numeric(24, 6), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="RHP", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["ipo_id"], ["ipos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["ipo_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"], ["ipo_extraction_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extraction_run_id",
            "metric",
            "financial_year",
            name="uq_ipo_metric_run_metric_period",
        ),
    )
    op.create_index("ix_ipo_metrics_ipo_id", "ipo_metrics", ["ipo_id"])
    op.create_index("ix_ipo_metrics_document_id", "ipo_metrics", ["document_id"])
    op.create_index(
        "ix_ipo_metrics_extraction_run_id", "ipo_metrics", ["extraction_run_id"]
    )
    op.create_index("ix_ipo_metrics_metric", "ipo_metrics", ["metric"])
    op.create_index("ix_ipo_metrics_ipo_metric", "ipo_metrics", ["ipo_id", "metric"])


def downgrade() -> None:
    op.drop_table("ipo_metrics")
    op.drop_table("ipo_extraction_runs")
    op.drop_table("ipo_extraction_jobs")
