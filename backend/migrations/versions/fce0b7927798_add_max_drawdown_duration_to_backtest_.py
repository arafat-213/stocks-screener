"""add_max_drawdown_duration_to_backtest_run

Revision ID: fce0b7927798
Revises: 5b08cee4ec3b
Create Date: 2026-06-09 12:02:10.938125

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fce0b7927798"
down_revision: Union[str, Sequence[str], None] = "5b08cee4ec3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "backtest_runs", sa.Column("max_drawdown_duration", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("backtest_runs", "max_drawdown_duration")
