"""add_quality_tier_to_screen_results

Revision ID: db96f22308eb
Revises: 944aef39ae53
Create Date: 2026-05-24 12:31:30.878307

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "db96f22308eb"
down_revision: Union[str, Sequence[str], None] = "944aef39ae53"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "screen_results", sa.Column("quality_tier", sa.String(length=1), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("screen_results", "quality_tier")
