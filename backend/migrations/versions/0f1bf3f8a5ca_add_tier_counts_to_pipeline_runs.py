"""add tier counts to pipeline runs

Revision ID: 0f1bf3f8a5ca
Revises: bd36d63c5fdf
Create Date: 2026-05-11 18:31:10.583705

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f1bf3f8a5ca'
down_revision: Union[str, Sequence[str], None] = 'bd36d63c5fdf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('pipeline_runs', sa.Column('tier1_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('pipeline_runs', sa.Column('tier2_count', sa.Integer(), nullable=True, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('pipeline_runs', 'tier2_count')
    op.drop_column('pipeline_runs', 'tier1_count')
