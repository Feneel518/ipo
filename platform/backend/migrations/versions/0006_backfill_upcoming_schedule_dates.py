"""Backfill schedule estimates before a listing date is announced.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE ipos
        SET allotment_date = COALESCE(allotment_date, close_date +
              CASE EXTRACT(DOW FROM close_date)
                WHEN 5 THEN 3 WHEN 6 THEN 2 ELSE 1
              END::integer),
            allotment_date_is_estimated = CASE
              WHEN allotment_date IS NULL THEN TRUE ELSE allotment_date_is_estimated
            END,
            refund_date = COALESCE(refund_date, close_date +
              CASE EXTRACT(DOW FROM close_date)
                WHEN 4 THEN 4 WHEN 5 THEN 4 WHEN 6 THEN 3 WHEN 0 THEN 2 ELSE 2
              END::integer),
            refund_date_is_estimated = CASE
              WHEN refund_date IS NULL THEN TRUE ELSE refund_date_is_estimated
            END,
            credit_date = COALESCE(credit_date, close_date +
              CASE EXTRACT(DOW FROM close_date)
                WHEN 4 THEN 4 WHEN 5 THEN 4 WHEN 6 THEN 3 WHEN 0 THEN 2 ELSE 2
              END::integer),
            credit_date_is_estimated = CASE
              WHEN credit_date IS NULL THEN TRUE ELSE credit_date_is_estimated
            END
        WHERE close_date IS NOT NULL
          AND (allotment_date IS NULL OR refund_date IS NULL OR credit_date IS NULL)
        """
    )


def downgrade() -> None:
    # Estimates cannot be distinguished by which anchor generated them after
    # official updates may have occurred, so retain the non-destructive data.
    pass
