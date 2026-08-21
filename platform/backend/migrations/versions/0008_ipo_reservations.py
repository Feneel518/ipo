"""Persist official IPO reservation master data.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ipo_reservations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ipo_id", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("parent_category", sa.String(length=40), nullable=True),
        sa.Column("shares", sa.Numeric(24, 4), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("is_actual", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_derived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ipo_id"], ["ipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ipo_id", "category"),
    )
    op.create_index("ix_ipo_reservations_ipo_id", "ipo_reservations", ["ipo_id"])
    op.execute(
        """
        INSERT INTO ipo_reservations (
            ipo_id, category, parent_category, shares, source_url,
            source_type, as_of_date, is_actual, is_derived
        )
        SELECT DISTINCT ON (ipo_id, category)
            ipo_id,
            category,
            CASE WHEN category IN ('BNII', 'SNII') THEN 'NII' ELSE NULL END,
            shares_reserved_for_category,
            source,
            'EXCHANGE_CATEGORY',
            snapshot_date,
            TRUE,
            FALSE
        FROM subscription_snapshots
        WHERE shares_reserved_for_category IS NOT NULL
          AND shares_reserved_for_category > 0
          AND category IN (
              'QIB', 'NII', 'BNII', 'SNII', 'RETAIL', 'INDIVIDUAL',
              'EMPLOYEE', 'SHAREHOLDER', 'MARKET_MAKER'
          )
        ORDER BY ipo_id, category, captured_at DESC, observed_at DESC
        ON CONFLICT (ipo_id, category) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_ipo_reservations_ipo_id", table_name="ipo_reservations")
    op.drop_table("ipo_reservations")
