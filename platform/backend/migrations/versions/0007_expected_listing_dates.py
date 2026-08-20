"""Store estimated listing dates separately from confirmed listing dates.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("ipos")}
    if "expected_listing_date" not in columns:
        op.add_column("ipos", sa.Column("expected_listing_date", sa.Date(), nullable=True))

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("ipos")}
    if "ix_ipos_expected_listing_date" not in indexes:
        op.create_index("ix_ipos_expected_listing_date", "ipos", ["expected_listing_date"])

    op.execute(
        """
        UPDATE ipos
        SET expected_listing_date = close_date +
              CASE EXTRACT(DOW FROM close_date)
                WHEN 0 THEN 3
                WHEN 1 THEN 3
                WHEN 2 THEN 3
                WHEN 3 THEN 5
                WHEN 4 THEN 5
                WHEN 5 THEN 5
                WHEN 6 THEN 4
              END::integer
        WHERE listing_date IS NULL
          AND close_date IS NOT NULL
          AND expected_listing_date IS NULL
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("ipos")}
    if "ix_ipos_expected_listing_date" in indexes:
        op.drop_index("ix_ipos_expected_listing_date", table_name="ipos")
    op.drop_column("ipos", "expected_listing_date")
