"""Add normalized IPO master data and lifecycle enrichment state.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)
    ipo_columns = (
        set() if inspector is None else {column["name"] for column in inspector.get_columns("ipos")}
    )
    listing_columns = (
        set()
        if inspector is None
        else {column["name"] for column in inspector.get_columns("ipo_exchange_listings")}
    )
    tables = set() if inspector is None else set(inspector.get_table_names())
    market_type = postgresql.ENUM(
        "BOOK_BUILT", "FIXED_PRICE", "UNKNOWN", name="ipo_market_type", create_type=False
    )
    market_type.create(bind, checkfirst=True)
    bid_rule_exchange = postgresql.ENUM(
        "NSE", "BSE", name="bid_rule_exchange", create_type=False
    )
    bid_rule_exchange.create(bind, checkfirst=True)

    if "market_type" not in ipo_columns:
        op.add_column(
            "ipos",
            sa.Column("market_type", market_type, nullable=False, server_default="UNKNOWN"),
        )
    if "final_issue_price" not in ipo_columns:
        op.add_column("ipos", sa.Column("final_issue_price", sa.Numeric(18, 4)))
    if "tick_size" not in ipo_columns:
        op.add_column("ipos", sa.Column("tick_size", sa.Numeric(18, 4)))
    if "minimum_bid_quantity" not in ipo_columns:
        op.add_column("ipos", sa.Column("minimum_bid_quantity", sa.BigInteger()))
    if "minimum_retail_investment" not in ipo_columns:
        op.add_column("ipos", sa.Column("minimum_retail_investment", sa.Numeric(24, 4)))
    if "issue_size_crore_is_estimated" not in ipo_columns:
        op.add_column(
            "ipos",
            sa.Column(
                "issue_size_crore_is_estimated",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    op.execute(
        """
        UPDATE ipos
        SET market_type = CASE
            WHEN UPPER(issue_type) LIKE '%FIXED%' THEN 'FIXED_PRICE'::ipo_market_type
            WHEN UPPER(issue_type) LIKE '%BOOK%' THEN 'BOOK_BUILT'::ipo_market_type
            ELSE 'UNKNOWN'::ipo_market_type
        END,
        issue_type = 'IPO'
        """
    )

    listing_additions = {
        "series": sa.Column("series", sa.String(20)),
        "scrip_code": sa.Column("scrip_code", sa.String(20)),
        "source_status": sa.Column("source_status", sa.String(80)),
        "master_data_last_fetched_at": sa.Column(
            "master_data_last_fetched_at", sa.DateTime(timezone=True)
        ),
        "next_refresh_at": sa.Column("next_refresh_at", sa.DateTime(timezone=True)),
        "detail_failure_count": sa.Column(
            "detail_failure_count", sa.Integer(), nullable=False, server_default="0"
        ),
        "detail_last_error": sa.Column("detail_last_error", sa.Text()),
        "master_data_finalized_at": sa.Column(
            "master_data_finalized_at", sa.DateTime(timezone=True)
        ),
    }
    for name, column in listing_additions.items():
        if name not in listing_columns:
            op.add_column("ipo_exchange_listings", column)
    listing_indexes = (
        set()
        if inspector is None
        else {index["name"] for index in inspector.get_indexes("ipo_exchange_listings")}
    )
    if "ix_ipo_exchange_listings_next_refresh_at" not in listing_indexes:
        op.create_index(
            "ix_ipo_exchange_listings_next_refresh_at",
            "ipo_exchange_listings",
            ["next_refresh_at"],
        )
    op.execute(
        """
        UPDATE ipo_exchange_listings AS listing
        SET next_refresh_at = NOW()
        FROM ipos AS ipo
        WHERE listing.ipo_id = ipo.id
          AND EXTRACT(YEAR FROM COALESCE(ipo.open_date, ipo.created_at::date)) =
              EXTRACT(YEAR FROM CURRENT_DATE)
        """
    )

    if "ipo_bid_rules" not in tables:
        op.create_table(
            "ipo_bid_rules",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "ipo_id",
                sa.BigInteger(),
                sa.ForeignKey("ipos.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("exchange", bid_rule_exchange, nullable=False),
            sa.Column("category", sa.String(40), nullable=False),
            sa.Column("minimum_bid_quantity", sa.BigInteger()),
            sa.Column("maximum_bid_quantity", sa.BigInteger()),
            sa.Column("maximum_subscription_amount", sa.Numeric(24, 4)),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("ipo_id", "exchange", "category"),
        )
        op.create_index("ix_ipo_bid_rules_ipo_id", "ipo_bid_rules", ["ipo_id"])


def downgrade() -> None:
    op.drop_index("ix_ipo_bid_rules_ipo_id", table_name="ipo_bid_rules")
    op.drop_table("ipo_bid_rules")
    op.drop_index(
        "ix_ipo_exchange_listings_next_refresh_at", table_name="ipo_exchange_listings"
    )
    for column in (
        "master_data_finalized_at",
        "detail_last_error",
        "detail_failure_count",
        "next_refresh_at",
        "master_data_last_fetched_at",
        "source_status",
        "scrip_code",
        "series",
    ):
        op.drop_column("ipo_exchange_listings", column)
    for column in (
        "issue_size_crore_is_estimated",
        "minimum_retail_investment",
        "minimum_bid_quantity",
        "tick_size",
        "final_issue_price",
        "market_type",
    ):
        op.drop_column("ipos", column)
    postgresql.ENUM(name="bid_rule_exchange").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="ipo_market_type").drop(op.get_bind(), checkfirst=True)
