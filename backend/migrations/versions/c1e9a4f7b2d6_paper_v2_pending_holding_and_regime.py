"""paper_v2_pending_holding_and_regime

v3/11 viz — enrich the pending-fills queue for the rebalance log:

  * ``holding_before`` — pre-trade shares of the position a fill acts on, captured at
    decision time. Lets the log render "holding (Δ)" (e.g. trim "10 (-2)", full exit
    "25 (-25)") which cannot be reconstructed historically from ``qty`` once the
    position has moved on.
  * ``deployable_fraction`` — the regime overlay's deployable fraction on the decision
    day (1.0 risk-on / risk_off_floor risk-off). Lets the log flag a regime-driven
    risk-off rebalance vs a routine one.

Both nullable: pre-existing rows have no captured value and the FE degrades gracefully.
(The new ``reason`` value ``force_exit`` reuses the existing column — no schema change.)

Revision ID: c1e9a4f7b2d6
Revises: 5d30f4bfa74d
Create Date: 2026-06-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1e9a4f7b2d6"
down_revision: Union[str, Sequence[str], None] = "5d30f4bfa74d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "paper_v2_pending_fills",
        sa.Column("holding_before", sa.Float(), nullable=True),
    )
    op.add_column(
        "paper_v2_pending_fills",
        sa.Column("deployable_fraction", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("paper_v2_pending_fills", "deployable_fraction")
    op.drop_column("paper_v2_pending_fills", "holding_before")
