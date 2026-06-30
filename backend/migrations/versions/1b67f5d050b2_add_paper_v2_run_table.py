"""add_paper_v2_run_table

Revision ID: 1b67f5d050b2
Revises: 0a1f85aef724
Create Date: 2026-06-30 13:13:05.606316

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1b67f5d050b2"
down_revision: Union[str, Sequence[str], None] = "0a1f85aef724"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "paper_v2_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("days_processed", sa.Integer(), nullable=False),
        sa.Column("first_date", sa.Date(), nullable=True),
        sa.Column("last_date", sa.Date(), nullable=True),
        sa.Column("error_class", sa.String(), nullable=True),
        sa.Column("error_msg", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["portfolio_id"], ["paper_v2_portfolio.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_v2_run_portfolio_started_at",
        "paper_v2_run",
        ["portfolio_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_paper_v2_run_portfolio_started_at", table_name="paper_v2_run")
    op.drop_table("paper_v2_run")
