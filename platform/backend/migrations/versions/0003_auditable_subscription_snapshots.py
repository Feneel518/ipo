"""Store auditable, intraday subscription observations.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    columns = sa.inspect(op.get_bind()).get_columns("subscription_snapshots")
    return {item["name"] for item in columns}


def upgrade() -> None:
    columns = _columns()
    renames = {
        "offered_quantity": "shares_reserved_for_category",
        "bid_quantity": "raw_exchange_bid_quantity",
        "subscription_multiple": "calculated_subscription",
    }
    for old, new in renames.items():
        if old in columns and new not in columns:
            op.alter_column("subscription_snapshots", old, new_column_name=new)

    columns = _columns()
    if "observed_at" not in columns:
        op.add_column(
            "subscription_snapshots",
            sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "source_reported_multiple" not in columns:
        op.add_column(
            "subscription_snapshots",
            sa.Column("source_reported_multiple", sa.Numeric(18, 6)),
        )
    if "source" not in columns:
        op.add_column(
            "subscription_snapshots",
            sa.Column("source", sa.Text(), nullable=False, server_default="legacy"),
        )
    if "bid_data_scope" not in columns:
        op.add_column(
            "subscription_snapshots",
            sa.Column(
                "bid_data_scope",
                sa.String(30),
                nullable=False,
                server_default="LEGACY",
            ),
        )

    inspector = sa.inspect(op.get_bind())
    old_columns = {"ipo_id", "exchange", "snapshot_date", "category"}
    unique_constraints = inspector.get_unique_constraints("subscription_snapshots")
    for constraint in unique_constraints:
        if set(constraint.get("column_names") or []) == old_columns:
            op.drop_constraint(constraint["name"], "subscription_snapshots", type_="unique")

    unique_constraints = sa.inspect(op.get_bind()).get_unique_constraints(
        "subscription_snapshots"
    )
    if not any(item["name"] == "uq_subscription_observation" for item in unique_constraints):
        op.create_unique_constraint(
            "uq_subscription_observation",
            "subscription_snapshots",
            ["ipo_id", "exchange", "captured_at", "category", "bid_data_scope"],
        )


def downgrade() -> None:
    op.drop_constraint("uq_subscription_observation", "subscription_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_subscription_daily_category",
        "subscription_snapshots",
        ["ipo_id", "exchange", "snapshot_date", "category"],
    )
    op.drop_column("subscription_snapshots", "bid_data_scope")
    op.drop_column("subscription_snapshots", "source")
    op.drop_column("subscription_snapshots", "source_reported_multiple")
    op.drop_column("subscription_snapshots", "observed_at")
    op.alter_column(
        "subscription_snapshots",
        "calculated_subscription",
        new_column_name="subscription_multiple",
    )
    op.alter_column(
        "subscription_snapshots",
        "raw_exchange_bid_quantity",
        new_column_name="bid_quantity",
    )
    op.alter_column(
        "subscription_snapshots",
        "shares_reserved_for_category",
        new_column_name="offered_quantity",
    )
