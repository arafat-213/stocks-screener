"""paper_v2_pending_decision_price

v3/11 (P11.1) — persist the decision-close price on the pending-fills queue.

A buy is sized by ₹ notional = qty × decision-close price (engine ``_stamp_fills``).
The P11.0 queue stored only ``qty``, so a buy rehydrated after a restart lost its
price (read back as 0.0) → zero target notional → the fill was silently dropped,
breaking the D→D+1 fill discipline across process boundaries (11 §3e). This adds a
nullable ``decision_price`` so the live shell reconstructs the buy notional exactly;
sells/trims keep it for symmetry (their qty is fixed and 5.i restamps the open).

Revision ID: b7c4f1a2d3e8
Revises: 9ced06257609
Create Date: 2026-06-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c4f1a2d3e8"
down_revision: Union[str, Sequence[str], None] = "9ced06257609"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "paper_v2_pending_fills",
        sa.Column("decision_price", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("paper_v2_pending_fills", "decision_price")
