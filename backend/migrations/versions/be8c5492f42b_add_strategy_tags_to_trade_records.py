"""add strategy tags to trade records

Revision ID: be8c5492f42b
Revises: 4205d5b4a8d2
Create Date: 2026-05-31 15:12:17.333206

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "be8c5492f42b"
down_revision: Union[str, Sequence[str], None] = "4205d5b4a8d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("paper_trades", sa.Column("strategy_tags", sa.JSON(), nullable=True))
    op.add_column("trade_journal", sa.Column("strategy_tags", sa.JSON(), nullable=True))

    # Also add indexes that were detected if they look safe
    op.create_index(
        "ix_ts_above_200ema", "technical_signals", ["above_200ema"], unique=False
    )
    op.create_index("ix_ts_rs_score", "technical_signals", ["rs_score"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_ts_rs_score", table_name="technical_signals")
    op.drop_index("ix_ts_above_200ema", table_name="technical_signals")
    op.drop_column("trade_journal", "strategy_tags")
    op.drop_column("paper_trades", "strategy_tags")
