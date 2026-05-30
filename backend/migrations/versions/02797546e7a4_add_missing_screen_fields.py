"""add missing screen fields

Revision ID: 02797546e7a4
Revises: 4a2e7e327667
Create Date: 2026-05-12 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "02797546e7a4"
down_revision: Union[str, Sequence[str], None] = "4a2e7e327667"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fundamental_cache", sa.Column("roe", sa.Float(), nullable=True))
    op.add_column(
        "technical_signals", sa.Column("momentum_12m", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("technical_signals", "momentum_12m")
    op.drop_column("fundamental_cache", "roe")
