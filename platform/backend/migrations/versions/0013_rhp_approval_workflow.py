"""Add auditable RHP extraction review and approval fields.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ipo_extraction_runs",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ipo_extraction_runs",
        sa.Column("reviewed_by", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "ipo_extraction_runs",
        sa.Column("review_resolutions", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ipo_extraction_runs",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ipo_extraction_runs",
        sa.Column("approved_by", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ipo_extraction_runs", "approved_by")
    op.drop_column("ipo_extraction_runs", "approved_at")
    op.drop_column("ipo_extraction_runs", "review_resolutions")
    op.drop_column("ipo_extraction_runs", "reviewed_by")
    op.drop_column("ipo_extraction_runs", "reviewed_at")
