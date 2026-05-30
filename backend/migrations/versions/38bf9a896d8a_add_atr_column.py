"""Add atr column to TechnicalSignal

Revision ID: 38bf9a896d8a
Revises: d142dda354d7
Create Date: 2026-05-08 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "38bf9a896d8a"
down_revision: Union[str, Sequence[str], None] = "d142dda354d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # add atr column to technical_signals
    op.add_column("technical_signals", sa.Column("atr", sa.Float(), nullable=True))


def downgrade() -> None:
    # remove atr column from technical_signals
    op.drop_column("technical_signals", "atr")
