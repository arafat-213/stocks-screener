"""add_paper_v2_alert_table_f5

Revision ID: 0a1f85aef724
Revises: c1e9a4f7b2d6
Create Date: 2026-06-29 22:06:34.145817

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a1f85aef724"
down_revision: Union[str, Sequence[str], None] = "c1e9a4f7b2d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "paper_v2_alert",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body_summary", sa.String(), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["paper_v2_portfolio.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_v2_alert_portfolio_created_at",
        "paper_v2_alert",
        ["portfolio_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_paper_v2_alert_portfolio_created_at", table_name="paper_v2_alert")
    op.drop_table("paper_v2_alert")
