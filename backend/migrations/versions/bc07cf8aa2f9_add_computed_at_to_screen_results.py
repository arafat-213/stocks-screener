"""add_computed_at_to_screen_results

Revision ID: bc07cf8aa2f9
Revises: 3d6b1f192149
Create Date: 2026-05-10 12:54:43.215584

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'bc07cf8aa2f9'
down_revision: Union[str, Sequence[str], None] = '3d6b1f192149'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('screen_results', 'computed_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.Date(),
               existing_nullable=True,
               postgresql_using='computed_at::date')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('screen_results', 'computed_at',
               existing_type=sa.Date(),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=True)
