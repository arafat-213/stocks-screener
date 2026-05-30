"""add paper trading tables

Revision ID: 53ed1c4a283b
Revises: ad73737a882d
Create Date: 2026-05-22 15:31:05.337295

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "53ed1c4a283b"
down_revision: Union[str, Sequence[str], None] = "ad73737a882d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Tables already created in a partial/manual run.
    # This migration exists to sync the alembic version.
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
