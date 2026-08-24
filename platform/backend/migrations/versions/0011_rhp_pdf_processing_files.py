"""Store Gemini-safe RHP processing files and original page mappings.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ipo_documents",
        sa.Column(
            "pdf_processing_status",
            sa.String(length=30),
            nullable=False,
            server_default="NOT_PREPARED",
        ),
    )
    op.add_column("ipo_documents", sa.Column("pdf_processing_error", sa.Text(), nullable=True))
    op.add_column(
        "ipo_documents",
        sa.Column("pdf_processing_prepared_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_ipo_documents_pdf_processing_status",
        "ipo_documents",
        ["pdf_processing_status"],
    )
    op.create_table(
        "rhp_processing_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("original_start_page", sa.Integer(), nullable=False),
        sa.Column("original_end_page", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["ipo_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "kind", "chunk_index"),
    )
    op.create_index(
        "ix_rhp_processing_files_document_id", "rhp_processing_files", ["document_id"]
    )
    op.create_index(
        "ix_rhp_processing_files_document_chunk",
        "rhp_processing_files",
        ["document_id", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_rhp_processing_files_document_chunk", table_name="rhp_processing_files")
    op.drop_index("ix_rhp_processing_files_document_id", table_name="rhp_processing_files")
    op.drop_table("rhp_processing_files")
    op.drop_index("ix_ipo_documents_pdf_processing_status", table_name="ipo_documents")
    for column in (
        "pdf_processing_prepared_at",
        "pdf_processing_error",
        "pdf_processing_status",
    ):
        op.drop_column("ipo_documents", column)
