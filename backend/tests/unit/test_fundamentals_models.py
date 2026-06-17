"""TB1 — PIT storage schema invariants for the Track-B fundamentals layer.

These tests encode WHY the schema is shaped this way (Rule 9), not just that it
exists:

  - A *restatement* of a period MUST be a new row, not an overwrite — so the
    as-of reader (TB5) can return "the figure as known on date D" and never lose
    the earlier vintage. The schema must therefore admit two rows for one
    (isin, period_end) that differ only by ``available_date``.
  - Ingest MUST be idempotent (CLAUDE.md §1) — re-writing the *same* version
    (identical isin / period_end / available_date) must be rejected, so a
    re-run never silently duplicates a vintage.

Uses an isolated in-memory SQLite engine, matching the project's test DB choice
(``tests/conftest.py``); no network, no Postgres.
"""

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base

# Importing the module registers the fundamentals tables on the shared Base.
from app.fundamentals.models import (
    FundamentalsFilingIndex,
    FundamentalsLineItemVersion,
    FundamentalsUniverse,
)

ISIN = "INE002A01018"  # RELIANCE
PERIOD_END = datetime.date(2022, 3, 31)
V1_AVAIL = datetime.date(2022, 5, 10)  # first filing
V2_AVAIL = datetime.date(2022, 8, 1)  # restatement (later vintage)


@pytest.fixture
def session():
    """Isolated in-memory DB with only the fundamentals schema created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    # Universe parent row (the survivorship-free spine the rest hangs on).
    sess.add(FundamentalsUniverse(isin=ISIN, name="Reliance", exchange="NSE"))
    sess.commit()
    yield sess
    sess.close()
    Base.metadata.drop_all(bind=engine)


def _line_item(available_date, **overrides):
    kwargs = dict(
        isin=ISIN,
        period_end=PERIOD_END,
        available_date=available_date,
        net_income=100.0,
        total_equity=500.0,
    )
    kwargs.update(overrides)
    return FundamentalsLineItemVersion(**kwargs)


def test_restatement_keeps_both_versions(session):
    """Two versions of one (isin, period_end) differing only by available_date
    must BOTH persist — the restatement invariant (§3.4 write-side)."""
    session.add(_line_item(V1_AVAIL, net_income=100.0))
    session.add(_line_item(V2_AVAIL, net_income=120.0))  # restated upward
    session.commit()

    rows = (
        session.query(FundamentalsLineItemVersion)
        .filter_by(isin=ISIN, period_end=PERIOD_END)
        .order_by(FundamentalsLineItemVersion.available_date)
        .all()
    )
    assert len(rows) == 2
    assert [r.available_date for r in rows] == [V1_AVAIL, V2_AVAIL]
    # The original vintage is preserved untouched alongside the restatement.
    assert [r.net_income for r in rows] == [100.0, 120.0]


def test_duplicate_version_rejected(session):
    """An exact-duplicate version (same isin/period_end/available_date) must be
    rejected — re-ingest is idempotent, never a silent dup (CLAUDE.md §1)."""
    session.add(_line_item(V1_AVAIL))
    session.commit()

    session.add(_line_item(V1_AVAIL, net_income=999.0))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    rows = session.query(FundamentalsLineItemVersion).filter_by(isin=ISIN).all()
    assert len(rows) == 1
    assert rows[0].net_income == 100.0  # the first write stands


def test_unavailable_line_item_is_null_not_zero(session):
    """A line item the parser could not map is NULL, never 0 (TB4 / Rule 12)."""
    session.add(_line_item(V1_AVAIL, net_income=None, ebit=None))
    session.commit()
    row = session.query(FundamentalsLineItemVersion).filter_by(isin=ISIN).one()
    assert row.net_income is None
    assert row.ebit is None


def test_filing_index_idempotent_on_full_version_key(session):
    """The filing index dedups on (isin, period_end, available_date, statement_type)
    so re-running the index ingest never duplicates a filing row."""
    common = dict(
        isin=ISIN,
        period_end=PERIOD_END,
        available_date=V1_AVAIL,
        statement_type="Annual",
        source_exchange="NSE",
    )
    session.add(FundamentalsFilingIndex(**common))
    session.commit()

    session.add(FundamentalsFilingIndex(**common, document_url="http://dup"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert session.query(FundamentalsFilingIndex).count() == 1


def test_filing_index_distinct_statement_types_coexist(session):
    """An Annual and a Quarterly filing can share a period_end + available_date
    (different statement types) — both are legitimate, distinct filings."""
    base = dict(isin=ISIN, period_end=PERIOD_END, available_date=V1_AVAIL)
    session.add(FundamentalsFilingIndex(**base, statement_type="Annual"))
    session.add(FundamentalsFilingIndex(**base, statement_type="Quarterly"))
    session.commit()
    assert session.query(FundamentalsFilingIndex).count() == 2
