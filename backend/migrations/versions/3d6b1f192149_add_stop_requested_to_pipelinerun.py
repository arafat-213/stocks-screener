"""add_stop_requested_to_pipelinerun

Revision ID: 3d6b1f192149
Revises: 02797546e7a4
Create Date: 2026-05-10 12:24:42.888158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d6b1f192149'
down_revision: Union[str, Sequence[str], None] = '02797546e7a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('pipeline_runs', sa.Column('stop_requested', sa.Boolean(), server_default=sa.text('false'), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('pipeline_runs', 'stop_requested')
