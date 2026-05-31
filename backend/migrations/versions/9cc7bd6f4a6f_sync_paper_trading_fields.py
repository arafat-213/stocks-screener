"""sync_paper_trading_fields

Revision ID: 9cc7bd6f4a6f
Revises: 36d91b228660
Create Date: 2026-05-30 12:00:02.804815

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9cc7bd6f4a6f"
down_revision: Union[str, Sequence[str], None] = "36d91b228660"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    columns = [col["name"] for col in inspector.get_columns("paper_positions")]
    if "exit_price" not in columns:
        # Add missing columns to paper_positions
        op.add_column(
            "paper_positions", sa.Column("exit_price", sa.Float(), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    columns = [col["name"] for col in inspector.get_columns("paper_positions")]
    if "exit_price" in columns:
        op.drop_column("paper_positions", "exit_price")
