"""add_position_size_to_backtest_trade

Revision ID: 5b08cee4ec3b
Revises: 688f08625149
Create Date: 2026-06-08 21:24:09.027073

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b08cee4ec3b"
down_revision: Union[str, Sequence[str], None] = "688f08625149"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "backtest_trades", sa.Column("position_size", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("backtest_trades", "position_size")
