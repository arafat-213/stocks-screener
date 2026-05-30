"""merge_heads

Revision ID: 8f2ced134407
Revises: 9cc7bd6f4a6f, bb53787bd712
Create Date: 2026-05-30 16:57:12.442465

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "8f2ced134407"
down_revision: Union[str, Sequence[str], None] = ("9cc7bd6f4a6f", "bb53787bd712")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
