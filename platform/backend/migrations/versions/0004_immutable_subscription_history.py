"""Make subscription observations immutable and content-addressed.

Revision ID: 0004
Revises: 0003
"""

import hashlib
import json
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _canonical(value: object) -> str | None:
    if value is None:
        return None
    return format(Decimal(value).normalize(), "f")


def _content_hash(row: sa.Row) -> str:
    values = [
        row.shares_reserved_for_category,
        row.raw_exchange_bid_quantity,
        row.applications,
        row.calculated_subscription,
        row.source_reported_multiple,
    ]
    payload = json.dumps([_canonical(value) for value in values], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def upgrade() -> None:
    op.add_column("subscription_snapshots", sa.Column("content_hash", sa.String(64)))

    table = sa.table(
        "subscription_snapshots",
        sa.column("id", sa.BigInteger()),
        sa.column("shares_reserved_for_category", sa.Numeric()),
        sa.column("raw_exchange_bid_quantity", sa.Numeric()),
        sa.column("applications", sa.Numeric()),
        sa.column("calculated_subscription", sa.Numeric()),
        sa.column("source_reported_multiple", sa.Numeric()),
        sa.column("content_hash", sa.String(64)),
    )
    bind = op.get_bind()
    for row in bind.execute(sa.select(table)).mappings():
        bind.execute(
            table.update().where(table.c.id == row.id).values(content_hash=_content_hash(row))
        )

    op.alter_column("subscription_snapshots", "content_hash", nullable=False)
    op.drop_constraint("uq_subscription_observation", "subscription_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_subscription_observation",
        "subscription_snapshots",
        ["ipo_id", "exchange", "captured_at", "category", "bid_data_scope", "content_hash"],
    )


def downgrade() -> None:
    # A changed observation can share its source timestamp with an earlier row.
    # Keep the earliest observation so the old narrower constraint can be restored.
    op.execute(
        """
        DELETE FROM subscription_snapshots newer
        USING subscription_snapshots older
        WHERE newer.ipo_id = older.ipo_id
          AND newer.exchange = older.exchange
          AND newer.captured_at = older.captured_at
          AND newer.category = older.category
          AND newer.bid_data_scope = older.bid_data_scope
          AND newer.id > older.id
        """
    )
    op.drop_constraint("uq_subscription_observation", "subscription_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_subscription_observation",
        "subscription_snapshots",
        ["ipo_id", "exchange", "captured_at", "category", "bid_data_scope"],
    )
    op.drop_column("subscription_snapshots", "content_hash")
