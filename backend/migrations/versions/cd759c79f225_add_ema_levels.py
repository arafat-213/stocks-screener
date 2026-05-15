"""add ema levels

Revision ID: cd759c79f225
Revises: b171d59174c9
Create Date: 2026-05-15 18:18:59.714221

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd759c79f225'
down_revision: Union[str, Sequence[str], None] = 'b171d59174c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('technical_signals', sa.Column('ema5_level', sa.Float(), nullable=True))
    op.add_column('technical_signals', sa.Column('ema13_level', sa.Float(), nullable=True))
    op.add_column('technical_signals', sa.Column('ema20_level', sa.Float(), nullable=True))
    op.add_column('technical_signals', sa.Column('ema26_level', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('technical_signals', 'ema26_level')
    op.drop_column('technical_signals', 'ema20_level')
    op.drop_column('technical_signals', 'ema13_level')
    op.drop_column('technical_signals', 'ema5_level')
