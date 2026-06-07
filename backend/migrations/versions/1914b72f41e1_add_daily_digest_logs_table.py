"""add_daily_digest_logs_table

Revision ID: 1914b72f41e1
Revises: 0a68ae083e81
Create Date: 2026-06-07 14:56:36.810971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1914b72f41e1'
down_revision: Union[str, Sequence[str], None] = '0a68ae083e81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('daily_digest_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('regime_bullish', sa.Boolean(), nullable=False),
    sa.Column('new_signals', sa.JSON(), nullable=True),
    sa.Column('opened_positions', sa.JSON(), nullable=True),
    sa.Column('closed_positions', sa.JSON(), nullable=True),
    sa.Column('trail_moved', sa.JSON(), nullable=True),
    sa.Column('warnings', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_daily_digest_logs_date'), 'daily_digest_logs', ['date'], unique=True)
    op.create_index(op.f('ix_daily_digest_logs_id'), 'daily_digest_logs', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_daily_digest_logs_id'), table_name='daily_digest_logs')
    op.drop_index(op.f('ix_daily_digest_logs_date'), table_name='daily_digest_logs')
    op.drop_table('daily_digest_logs')
