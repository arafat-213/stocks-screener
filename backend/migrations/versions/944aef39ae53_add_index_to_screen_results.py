"""add_index_to_screen_results

Revision ID: 944aef39ae53
Revises: 53ed1c4a283b
Create Date: 2026-05-23 15:23:01.994688

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "944aef39ae53"
down_revision: Union[str, Sequence[str], None] = "53ed1c4a283b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_sr_slug_date",
        "screen_results",
        ["screen_slug", "computed_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_sr_slug_date", table_name="screen_results")
