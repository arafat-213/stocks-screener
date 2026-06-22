"""add_paper_v2_tables_s3_probation

v3/11 (P11.0) — v2-native paper book for the S3 forward probation. Three tables,
ISIN-keyed, mirroring ``backtest_v2`` portfolio state. The v1 ``paper_*`` tables
(swing-trade, symbol/ATR/EMA) are left untouched — v1 removal is a separate later
sprint (11 §2/§9), so this is additive, not a replacement of v1 schema.

  * paper_v2_portfolio    — the book (cash, starting capital, replay clock).
  * paper_v2_positions    — open holdings: backtest_v2 Position fields + S3
                            selection metadata + last-seen ``adj_factor`` so the
                            §5e CA-reconciliation can detect a moving anchor.
  * paper_v2_pending_fills — the persisted pending-fills queue (§3e): a decision
                            at day D's close queues a row; the next session's job
                            fills it at D+1's open and marks it ``filled``.

Revision ID: 9ced06257609
Revises: a3f8e2d1c094
Create Date: 2026-06-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9ced06257609"
down_revision: Union[str, Sequence[str], None] = "a3f8e2d1c094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "paper_v2_portfolio",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("starting_capital", sa.Float(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_processed_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "paper_v2_pending_fills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("fill_date", sa.Date(), nullable=True),
        sa.Column("fill_price", sa.Float(), nullable=True),
        sa.Column("cost_rupees", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["portfolio_id"], ["paper_v2_portfolio.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_v2_fill_portfolio_status",
        "paper_v2_pending_fills",
        ["portfolio_id", "status"],
        unique=False,
    )
    op.create_table(
        "paper_v2_positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("cost_basis", sa.Float(), nullable=False),
        sa.Column("last_price", sa.Float(), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("days_held", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("composite_score", sa.Float(), nullable=True),
        sa.Column("target_weight", sa.Float(), nullable=True),
        sa.Column("regime_state_at_entry", sa.String(), nullable=True),
        sa.Column("last_adj_factor", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["portfolio_id"], ["paper_v2_portfolio.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id", "isin", name="uq_paper_v2_pos_portfolio_isin"
        ),
    )
    op.create_index(
        "ix_paper_v2_pos_portfolio",
        "paper_v2_positions",
        ["portfolio_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_paper_v2_pos_portfolio", table_name="paper_v2_positions")
    op.drop_table("paper_v2_positions")
    op.drop_index(
        "ix_paper_v2_fill_portfolio_status", table_name="paper_v2_pending_fills"
    )
    op.drop_table("paper_v2_pending_fills")
    op.drop_table("paper_v2_portfolio")
