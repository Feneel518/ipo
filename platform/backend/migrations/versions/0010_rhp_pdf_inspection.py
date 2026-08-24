"""Record RHP PDF inspection and Gemini direct-processing eligibility.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ipo_documents", sa.Column("pdf_page_count", sa.Integer(), nullable=True))
    op.add_column("ipo_documents", sa.Column("pdf_encrypted", sa.Boolean(), nullable=True))
    op.add_column("ipo_documents", sa.Column("pdf_malformed", sa.Boolean(), nullable=True))
    op.add_column(
        "ipo_documents",
        sa.Column(
            "pdf_inspection_status",
            sa.String(length=30),
            nullable=False,
            server_default="NOT_INSPECTED",
        ),
    )
    op.add_column(
        "ipo_documents", sa.Column("pdf_processing_decision", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "ipo_documents", sa.Column("gemini_direct_eligible", sa.Boolean(), nullable=True)
    )
    op.add_column("ipo_documents", sa.Column("pdf_inspection_error", sa.Text(), nullable=True))
    op.add_column(
        "ipo_documents",
        sa.Column("pdf_inspected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_ipo_documents_pdf_inspection_status",
        "ipo_documents",
        ["pdf_inspection_status"],
    )
    op.create_index(
        "ix_ipo_documents_pdf_processing_decision",
        "ipo_documents",
        ["pdf_processing_decision"],
    )


def downgrade() -> None:
    op.drop_index("ix_ipo_documents_pdf_processing_decision", table_name="ipo_documents")
    op.drop_index("ix_ipo_documents_pdf_inspection_status", table_name="ipo_documents")
    for column in (
        "pdf_inspected_at",
        "pdf_inspection_error",
        "gemini_direct_eligible",
        "pdf_processing_decision",
        "pdf_inspection_status",
        "pdf_malformed",
        "pdf_encrypted",
        "pdf_page_count",
    ):
        op.drop_column("ipo_documents", column)
