"""add_paper_v2_scorecard_snapshot_table

Revision ID: 42a9ea26fbe2
Revises: 1b67f5d050b2
Create Date: 2026-07-01 12:29:53.929502

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "42a9ea26fbe2"
down_revision: Union[str, Sequence[str], None] = "1b67f5d050b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "paper_v2_scorecard_snapshot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("clean_months_passed", sa.Integer(), nullable=False),
        sa.Column("clock_reset_at", sa.Date(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["paper_v2_portfolio.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id",
            "as_of_date",
            "trigger",
            name="uq_paper_v2_scorecard_snap_portfolio_asof_trigger",
        ),
    )
    op.create_index(
        "ix_paper_v2_scorecard_snap_portfolio_asof",
        "paper_v2_scorecard_snapshot",
        ["portfolio_id", "as_of_date"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_paper_v2_scorecard_snap_portfolio_asof",
        table_name="paper_v2_scorecard_snapshot",
    )
    op.drop_table("paper_v2_scorecard_snapshot")
