"""Store IPO allotment, refund, and share-credit dates.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


DATE_FIELDS = ("allotment_date", "refund_date", "credit_date")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("ipos")}

    for field in DATE_FIELDS:
        if field not in columns:
            op.add_column("ipos", sa.Column(field, sa.Date(), nullable=True))
        estimated_field = f"{field}_is_estimated"
        if estimated_field not in columns:
            op.add_column(
                "ipos",
                sa.Column(
                    estimated_field,
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )

    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("ipos")}
    for field in DATE_FIELDS:
        index_name = f"ix_ipos_{field}"
        if index_name not in existing_indexes:
            op.create_index(index_name, "ipos", [field])

    # Existing records receive a clearly-labelled business-day estimate. A
    # subsequent ingestion replaces it when an exchange supplies an official date.
    op.execute(
        """
        UPDATE ipos
        SET allotment_date = COALESCE(allotment_date, listing_date -
              CASE EXTRACT(DOW FROM listing_date)
                WHEN 0 THEN 3 WHEN 1 THEN 4 WHEN 2 THEN 4 ELSE 2
              END::integer),
            allotment_date_is_estimated = CASE
              WHEN allotment_date IS NULL THEN TRUE ELSE allotment_date_is_estimated
            END,
            refund_date = COALESCE(refund_date, listing_date -
              CASE EXTRACT(DOW FROM listing_date)
                WHEN 0 THEN 2 WHEN 1 THEN 3 ELSE 1
              END::integer),
            refund_date_is_estimated = CASE
              WHEN refund_date IS NULL THEN TRUE ELSE refund_date_is_estimated
            END,
            credit_date = COALESCE(credit_date, listing_date -
              CASE EXTRACT(DOW FROM listing_date)
                WHEN 0 THEN 2 WHEN 1 THEN 3 ELSE 1
              END::integer),
            credit_date_is_estimated = CASE
              WHEN credit_date IS NULL THEN TRUE ELSE credit_date_is_estimated
            END
        WHERE listing_date IS NOT NULL
          AND (allotment_date IS NULL OR refund_date IS NULL OR credit_date IS NULL)
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("ipos")}
    for field in reversed(DATE_FIELDS):
        index_name = f"ix_ipos_{field}"
        if index_name in indexes:
            op.drop_index(index_name, table_name="ipos")
        op.drop_column("ipos", f"{field}_is_estimated")
        op.drop_column("ipos", field)
