"""add_fundamentals_pit_tables

Track-B (TB1) point-in-time fundamentals storage schema: the survivorship-free
universe master, ISIN->symbol PIT history, the filing index (the look-ahead
clock) and the restatement-versioned standardized line items.

Restatement invariant (line items): the unique key is
(isin, period_end, available_date) — a re-filed period is a NEW row, never an
overwrite; an exact-duplicate version is rejected (idempotency).

Revision ID: c4e1f7a9b2d3
Revises: 934e63731fa2
Create Date: 2026-06-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e1f7a9b2d3"
down_revision: Union[str, Sequence[str], None] = "934e63731fa2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "fundamentals_universe",
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("exchange", sa.String(), nullable=True),
        sa.Column("list_date", sa.Date(), nullable=True),
        sa.Column("delist_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("isin"),
    )
    op.create_table(
        "fundamentals_symbol_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["isin"], ["fundamentals_universe.isin"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "isin", "symbol", "valid_from", name="uq_fund_symbol_isin_symbol_from"
        ),
    )
    op.create_index("ix_fund_symbol_isin", "fundamentals_symbol_history", ["isin"])
    op.create_index("ix_fund_symbol_symbol", "fundamentals_symbol_history", ["symbol"])
    op.create_table(
        "fundamentals_filing_index",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("available_date", sa.Date(), nullable=False),
        sa.Column("statement_type", sa.String(), nullable=True),
        sa.Column("source_exchange", sa.String(), nullable=True),
        sa.Column("document_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["isin"], ["fundamentals_universe.isin"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "isin",
            "period_end",
            "available_date",
            "statement_type",
            name="uq_fund_filing_isin_period_avail_type",
        ),
    )
    op.create_index(
        "ix_fund_filing_isin_avail",
        "fundamentals_filing_index",
        ["isin", "available_date"],
    )
    op.create_index(
        "ix_fund_filing_isin_period",
        "fundamentals_filing_index",
        ["isin", "period_end"],
    )
    op.create_table(
        "fundamentals_line_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("available_date", sa.Date(), nullable=False),
        sa.Column("statement_type", sa.String(), nullable=True),
        sa.Column("source_exchange", sa.String(), nullable=True),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("net_income", sa.Float(), nullable=True),
        sa.Column("ebit", sa.Float(), nullable=True),
        sa.Column("total_equity", sa.Float(), nullable=True),
        sa.Column("total_assets", sa.Float(), nullable=True),
        sa.Column("total_debt", sa.Float(), nullable=True),
        sa.Column("shares_outstanding", sa.Float(), nullable=True),
        sa.Column("cfo", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["isin"], ["fundamentals_universe.isin"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "isin",
            "period_end",
            "available_date",
            name="uq_fund_lineitem_isin_period_avail",
        ),
    )
    op.create_index(
        "ix_fund_lineitem_isin_avail",
        "fundamentals_line_items",
        ["isin", "available_date"],
    )
    op.create_index(
        "ix_fund_lineitem_isin_period",
        "fundamentals_line_items",
        ["isin", "period_end"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_fund_lineitem_isin_period", "fundamentals_line_items")
    op.drop_index("ix_fund_lineitem_isin_avail", "fundamentals_line_items")
    op.drop_table("fundamentals_line_items")
    op.drop_index("ix_fund_filing_isin_period", "fundamentals_filing_index")
    op.drop_index("ix_fund_filing_isin_avail", "fundamentals_filing_index")
    op.drop_table("fundamentals_filing_index")
    op.drop_index("ix_fund_symbol_symbol", "fundamentals_symbol_history")
    op.drop_index("ix_fund_symbol_isin", "fundamentals_symbol_history")
    op.drop_table("fundamentals_symbol_history")
    op.drop_table("fundamentals_universe")
