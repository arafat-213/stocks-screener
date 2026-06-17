"""
fundamentals.models — PIT storage schema for the Track-B fundamentals data layer (TB1).

The three write-target tables the rest of the layer (TB2–TB6) populates, plus the
ISIN→symbol PIT history the filing-index ingest (TB3) resolves against:

  - ``FundamentalsUniverse``  — survivorship-free spine: one row per ISIN ever
    listed in-window, with list/delist dates and exchange (§3.1).
  - ``FundamentalsSymbolHistory`` — ISIN→symbol over time (.NS), PIT-correct so a
    delisted/renamed name still resolves to the symbol it traded under (§3.1).
  - ``FundamentalsFilingIndex`` — the PIT clock: per ISIN-period, the public
    ``available_date`` (filing/submission timestamp, NEVER period_end) — this is
    the look-ahead guard (§3.2, problem §1.1).
  - ``FundamentalsLineItemVersion`` — standardized line items, with EVERY restated
    version kept as its own row keyed by ``available_date`` (§3.3 + §3.4 write-side).

Design notes (locked here, consumed downstream):
  - **ISIN is the key** (CLAUDE.md §1). Symbols carry the ``.NS`` suffix.
  - **Restatement = a new row, never an overwrite.** The uniqueness key on the
    line-item table is ``(isin, period_end, available_date)``: two versions of one
    period differ only by ``available_date`` (both retained); an exact-duplicate
    version is rejected (idempotency, CLAUDE.md §1). TB5 reads the latest version
    with ``available_date <= D − lag``.
  - All stored timestamps are **UTC** (``datetime.now(timezone.utc)``).

These models register on the shared ``app.db.models.Base`` so they live in the one
sanctioned metadata / Alembic migration chain — the package boundary is by code
location (``app/fundamentals/``), not a separate database.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.db.models import Base


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class FundamentalsUniverse(Base):
    """Survivorship-free universe master — one row per ISIN ever listed in-window."""

    __tablename__ = "fundamentals_universe"

    isin = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    # Listing exchange (TB0 §8.1 EXCHANGE_PRIORITY values: "NSE" / "BSE").
    exchange = Column(String, nullable=True)
    list_date = Column(Date, nullable=True)
    # NULL = still listed at end of window (the survivorship-free flag).
    delist_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class FundamentalsSymbolHistory(Base):
    """ISIN→symbol over time — PIT-correct symbol resolution for TB3 (§3.1)."""

    __tablename__ = "fundamentals_symbol_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    isin = Column(String, ForeignKey("fundamentals_universe.isin"), nullable=False)
    symbol = Column(String, nullable=False)  # .NS suffix per CLAUDE.md §1
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)  # NULL = open / current
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        # One symbol assignment per ISIN per start date; re-ingest is idempotent.
        UniqueConstraint(
            "isin", "symbol", "valid_from", name="uq_fund_symbol_isin_symbol_from"
        ),
        Index("ix_fund_symbol_isin", "isin"),
        Index("ix_fund_symbol_symbol", "symbol"),
    )


class FundamentalsFilingIndex(Base):
    """Filing index — the PIT clock carrying the public ``available_date`` (§3.2)."""

    __tablename__ = "fundamentals_filing_index"

    id = Column(Integer, primary_key=True, autoincrement=True)
    isin = Column(String, ForeignKey("fundamentals_universe.isin"), nullable=False)
    period_end = Column(Date, nullable=False)
    # Public filing/submission timestamp — NEVER period_end. The look-ahead guard.
    available_date = Column(Date, nullable=False)
    # "Annual" / "HalfYearly" / "Quarterly" (Ind-AS results filing type).
    statement_type = Column(String, nullable=True)
    # Source exchange the row was ingested from (TB0 §8.1 priority/dedup).
    source_exchange = Column(String, nullable=True)
    # Pointer to the source XBRL document (URL / path) — TB4 parses from here.
    document_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        # Idempotent ingest: one filing row per (ISIN, period, version, type).
        UniqueConstraint(
            "isin",
            "period_end",
            "available_date",
            "statement_type",
            name="uq_fund_filing_isin_period_avail_type",
        ),
        Index("ix_fund_filing_isin_avail", "isin", "available_date"),
        Index("ix_fund_filing_isin_period", "isin", "period_end"),
    )


class FundamentalsLineItemVersion(Base):
    """Standardized line items — every restated version kept (§3.3 + §3.4 write-side).

    The uniqueness key ``(isin, period_end, available_date)`` is the restatement
    invariant: a re-filed period writes a NEW row (later ``available_date``); the
    original version is never overwritten. An exact-duplicate version is rejected.
    """

    __tablename__ = "fundamentals_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    isin = Column(String, ForeignKey("fundamentals_universe.isin"), nullable=False)
    period_end = Column(Date, nullable=False)
    # Restatement version key: this figure was first publicly available on this date.
    available_date = Column(Date, nullable=False)
    statement_type = Column(String, nullable=True)
    source_exchange = Column(String, nullable=True)

    # The 8 standardized line items (TB4 target schema). NULL = not available —
    # NEVER zero-filled (TB4 / Rule 12). Units/currency are reconciled in TB6.
    revenue = Column(Float, nullable=True)
    net_income = Column(Float, nullable=True)
    ebit = Column(Float, nullable=True)
    total_equity = Column(Float, nullable=True)
    total_assets = Column(Float, nullable=True)
    total_debt = Column(Float, nullable=True)
    shares_outstanding = Column(Float, nullable=True)
    cfo = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        # §3.4: restatement = a new available_date row; exact duplicate rejected.
        UniqueConstraint(
            "isin",
            "period_end",
            "available_date",
            name="uq_fund_lineitem_isin_period_avail",
        ),
        Index("ix_fund_lineitem_isin_avail", "isin", "available_date"),
        Index("ix_fund_lineitem_isin_period", "isin", "period_end"),
    )
