"""Track canonical RHP copies stored in Cloudflare R2.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ipo_documents",
        sa.Column(
            "storage_status",
            sa.String(length=30),
            nullable=False,
            server_default="NOT_APPLICABLE",
        ),
    )
    op.add_column("ipo_documents", sa.Column("storage_key", sa.Text(), nullable=True))
    op.add_column(
        "ipo_documents", sa.Column("content_sha256", sa.String(length=64), nullable=True)
    )
    op.add_column("ipo_documents", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column(
        "ipo_documents", sa.Column("source_content_type", sa.String(length=200), nullable=True)
    )
    op.add_column("ipo_documents", sa.Column("final_source_url", sa.Text(), nullable=True))
    op.add_column(
        "ipo_documents",
        sa.Column("storage_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("ipo_documents", sa.Column("storage_error", sa.Text(), nullable=True))
    op.add_column(
        "ipo_documents",
        sa.Column("storage_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ipo_documents", sa.Column("stored_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "ipo_documents",
        sa.Column("storage_deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ipo_documents_storage_status", "ipo_documents", ["storage_status"])
    op.create_index("ix_ipo_documents_content_sha256", "ipo_documents", ["content_sha256"])
    op.execute(
        r"""
        UPDATE ipo_documents AS document
        SET storage_status = 'PENDING'
        FROM ipos AS ipo
        WHERE document.ipo_id = ipo.id
          AND CASE
                WHEN ipo.lifecycle IN ('WITHDRAWN', 'CANCELLED') THEN ipo.lifecycle
                WHEN ipo.listing_date IS NOT NULL AND ipo.listing_date <= CURRENT_DATE
                  THEN 'LISTED'::ipo_lifecycle
                WHEN ipo.open_date IS NOT NULL AND ipo.open_date > CURRENT_DATE
                  THEN 'UPCOMING'::ipo_lifecycle
                WHEN ipo.open_date IS NOT NULL
                  AND ipo.close_date IS NOT NULL
                  AND ipo.open_date <= CURRENT_DATE
                  AND ipo.close_date >= CURRENT_DATE
                  THEN 'OPEN'::ipo_lifecycle
                WHEN ipo.close_date IS NOT NULL AND ipo.close_date < CURRENT_DATE
                  THEN 'CLOSED'::ipo_lifecycle
                ELSE ipo.lifecycle
              END IN ('UPCOMING', 'OPEN')
          AND (
                document.url ~* '^https?://([^/@]+\.)?nseindia\.com(?::[0-9]+)?/'
                OR NOT EXISTS (
                    SELECT 1
                    FROM ipo_exchange_listings AS listing
                    WHERE listing.ipo_id = ipo.id
                      AND listing.exchange = 'NSE'
                )
              )
          AND (
               upper(document.document_type) = 'RHP'
            OR upper(document.document_type) LIKE '%RED_HERRING%'
            OR upper(document.title) ~ '(^|[^A-Z])RHP([^A-Z]|$)'
            OR upper(document.title) LIKE '%RED HERRING%'
          )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_ipo_documents_content_sha256", table_name="ipo_documents")
    op.drop_index("ix_ipo_documents_storage_status", table_name="ipo_documents")
    for column in (
        "storage_deleted_at",
        "stored_at",
        "storage_attempted_at",
        "storage_error",
        "storage_attempts",
        "final_source_url",
        "source_content_type",
        "size_bytes",
        "content_sha256",
        "storage_key",
        "storage_status",
    ):
        op.drop_column("ipo_documents", column)
