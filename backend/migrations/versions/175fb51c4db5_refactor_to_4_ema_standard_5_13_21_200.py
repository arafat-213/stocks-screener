"""Refactor to 4-EMA Standard (5, 13, 21, 200)

Revision ID: 175fb51c4db5
Revises: fce0b7927798
Create Date: 2026-06-09 12:51:24.106092

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "175fb51c4db5"
down_revision: Union[str, Sequence[str], None] = "fce0b7927798"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. paper_positions renames and drops
    op.alter_column(
        "paper_positions", "ema20_at_signal", new_column_name="ema21_at_signal"
    )
    op.alter_column(
        "paper_positions",
        "strategy_tags",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        existing_nullable=True,
    )

    # 2. technical_signals renames and drops
    op.alter_column("technical_signals", "ema20_level", new_column_name="ema21_level")
    op.alter_column("technical_signals", "ema_slope_20", new_column_name="ema_slope_21")
    op.drop_column("technical_signals", "ema26_level")

    # 3. technical_signals nullability and other tweaks (SKIP ID ALTER)
    op.alter_column(
        "technical_signals",
        "is_bullish",
        existing_type=sa.BOOLEAN(),
        nullable=False,
        existing_server_default=sa.text("false"),
    )

    # 4. Cleanup redundant index if exists
    # op.drop_index('ix_sr_slug_date', table_name='screen_results')
    pass


def downgrade() -> None:
    # reverse 3
    op.alter_column(
        "technical_signals",
        "is_bullish",
        existing_type=sa.BOOLEAN(),
        nullable=True,
        existing_server_default=sa.text("false"),
    )

    # reverse 2
    op.add_column(
        "technical_signals", sa.Column("ema26_level", sa.FLOAT(), nullable=True)
    )
    op.alter_column("technical_signals", "ema_slope_21", new_column_name="ema_slope_20")
    op.alter_column("technical_signals", "ema21_level", new_column_name="ema20_level")

    # reverse 1
    op.alter_column(
        "paper_positions",
        "strategy_tags",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
    )
    op.alter_column(
        "paper_positions", "ema21_at_signal", new_column_name="ema20_at_signal"
    )
