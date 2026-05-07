"""refactor signals table for multi-timeframe

Revision ID: 154fdbdf9867
Revises: dee1660be5cc
Create Date: 2026-05-07 15:26:04.371893

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '154fdbdf9867'
down_revision: Union[str, Sequence[str], None] = 'dee1660be5cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename table
    op.rename_table('daily_scores', 'technical_signals')

    # 2. Add columns
    # We add 'id' as an Identity column which is the modern Postgres way for serials
    op.add_column('technical_signals', sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False))
    op.add_column('technical_signals', sa.Column('timeframe', sa.String(length=1), nullable=True))
    op.add_column('technical_signals', sa.Column('is_bullish', sa.Boolean(), nullable=True))
    op.add_column('technical_signals', sa.Column('rsi_signal', sa.String(), nullable=True))
    op.add_column('technical_signals', sa.Column('scored_at', sa.DateTime(), nullable=True))

    # 3. Backfill
    op.execute("UPDATE technical_signals SET timeframe = 'D', is_bullish = COALESCE(ema_signal = 'bullish', FALSE), scored_at = date")

    # 4. Handle Primary Key and Unique Constraint
    op.execute("ALTER TABLE technical_signals DROP CONSTRAINT daily_scores_pkey")
    op.create_primary_key('pk_technical_signals', 'technical_signals', ['id'])
    op.create_unique_constraint('uq_symbol_date_tf', 'technical_signals', ['symbol', 'date', 'timeframe'])

    # 5. Set non-nullable after backfill
    op.alter_column('technical_signals', 'timeframe', nullable=False)
    op.alter_column('technical_signals', 'is_bullish', nullable=False)


def downgrade() -> None:
    # 1. Drop new constraints
    op.drop_constraint('uq_symbol_date_tf', 'technical_signals', type_='unique')
    op.drop_constraint('pk_technical_signals', 'technical_signals', type_='primary')

    # 2. Restore old PK
    op.create_primary_key('daily_scores_pkey', 'technical_signals', ['date', 'symbol'])

    # 3. Drop new columns
    with op.batch_alter_table('technical_signals') as batch_op:
        batch_op.drop_column('scored_at')
        batch_op.drop_column('rsi_signal')
        batch_op.drop_column('is_bullish')
        batch_op.drop_column('timeframe')
        batch_op.drop_column('id')

    # 4. Rename back
    op.rename_table('technical_signals', 'daily_scores')



def downgrade() -> None:
    # 1. Drop new constraints
    op.drop_constraint('uq_symbol_date_tf', 'technical_signals', type_='unique')
    op.drop_constraint('pk_technical_signals', 'technical_signals', type_='primary')
    
    # 2. Restore old PK
    op.create_primary_key('daily_scores_pkey', 'technical_signals', ['date', 'symbol'])
    
    # 3. Drop new columns
    with op.batch_alter_table('technical_signals') as batch_op:
        batch_op.drop_column('scored_at')
        batch_op.drop_column('rsi_signal')
        batch_op.drop_column('is_bullish')
        batch_op.drop_column('timeframe')
        batch_op.drop_column('id')
        
    # 4. Rename back
    op.rename_table('technical_signals', 'daily_scores')
