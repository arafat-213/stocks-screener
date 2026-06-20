"""add_debt_equity_ratio_to_fundamentals_line_items

TBE5b: supplementary disclosed D/E ratio field — fallback source for the
leverage factor when total_debt is NULL (results-only filings carry
DebtEquityRatio but no balance-sheet borrowings).

Revision ID: a3f8e2d1c094
Revises: c4e1f7a9b2d3
Create Date: 2026-06-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f8e2d1c094"
down_revision: Union[str, Sequence[str], None] = "c4e1f7a9b2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "fundamentals_line_items",
        sa.Column("debt_equity_ratio", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("fundamentals_line_items", "debt_equity_ratio")
