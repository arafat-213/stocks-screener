"""add_market_breadth_table

Revision ID: 934e63731fa2
Revises: 175fb51c4db5
Create Date: 2026-06-11 20:03:09.271125

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "934e63731fa2"
down_revision: Union[str, Sequence[str], None] = "175fb51c4db5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "market_breadth",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("breadth_pct", sa.Float(), nullable=False),
        sa.Column("stock_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("date"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("market_breadth")
