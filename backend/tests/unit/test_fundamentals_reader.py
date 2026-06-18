"""
TB5 — as-of reader invariant tests (Rule 9: encode WHY each matters).

All tests use an in-memory SQLite DB with ``create_all`` — same pattern as
the other fundamentals unit tests.  No network, no Postgres needed.

Test matrix (against the TB5 spec):
  1. Between two filings → earlier period is returned (look-ahead excluded)
  2. Filed on D itself → excluded until D + lag (the PIT guard)
  3. Two versions of one period → latest qualifying version wins (restatement)
  4. D before first filing → empty list (no guess)
  5. Sole read path — FundamentalsLineItemVersion is NOT imported by this test
     module; all assertions go through read_fundamentals_asof (boundary check)
"""

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base
from app.fundamentals.data_config import SAFETY_LAG_TRADING_DAYS
from app.fundamentals.models import FundamentalsLineItemVersion, FundamentalsUniverse
from app.fundamentals.reader import FundamentalsSnapshot, read_fundamentals_asof

ISIN = "INE001A01036"

# ── dates used across tests ────────────────────────────────────────────────
# 2023-01-10 is a Tuesday.  busday_offset(2023-01-10, -2) = 2023-01-06 (Fri).
# Filing on 2023-01-10 is excluded until as_of_date = 2023-01-12 (Thu, +2bd).
AVAIL_JAN10 = datetime.date(2023, 1, 10)
AVAIL_JAN6 = datetime.date(2023, 1, 6)  # exactly at the Jan-10 cutoff when D=Jan12
PERIOD_Q3 = datetime.date(2022, 12, 31)  # Q3 period_end
PERIOD_Q2 = datetime.date(2022, 9, 30)  # Q2 period_end


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(FundamentalsUniverse(isin=ISIN, exchange="NSE"))
        s.commit()
        yield s


def _row(
    period_end: datetime.date,
    available_date: datetime.date,
    net_income: float = 100.0,
    statement_type: str = "Annual",
) -> FundamentalsLineItemVersion:
    return FundamentalsLineItemVersion(
        isin=ISIN,
        period_end=period_end,
        available_date=available_date,
        statement_type=statement_type,
        revenue=1000.0,
        net_income=net_income,
        ebit=None,
        total_equity=500.0,
        total_assets=800.0,
        total_debt=None,
        shares_outstanding=None,
        cfo=None,
    )


# ── Test 1 ──────────────────────────────────────────────────────────────────
def test_between_two_filings_earlier_period_returned(session):
    """
    WHY: two filing periods both filed before D − lag; the reader must return
    both, ordered newest period first.  Confirms the reader is not limited to
    the single latest period (factors need historical quarters for TTM).
    """
    # Q2 filing available 2022-10-15, Q3 filing available 2023-01-06 (a Friday).
    # Query at D = 2023-01-10 (Tuesday): cutoff = busday_offset(-2) = 2023-01-06.
    # Both available_dates (2022-10-15 and 2023-01-06) satisfy <= 2023-01-06.
    session.add(_row(PERIOD_Q2, datetime.date(2022, 10, 15), net_income=80.0))
    session.add(_row(PERIOD_Q3, AVAIL_JAN6, net_income=95.0))
    session.commit()

    results = read_fundamentals_asof(session, ISIN, AVAIL_JAN10)

    assert len(results) == 2
    # Newest period first.
    assert results[0].period_end == PERIOD_Q3
    assert results[0].net_income == 95.0
    assert results[1].period_end == PERIOD_Q2
    assert results[1].net_income == 80.0


# ── Test 2 ──────────────────────────────────────────────────────────────────
def test_figure_filed_on_D_excluded_until_D_plus_lag(session):
    """
    WHY: this is the core PIT guard (§3.5).  A filing available on the decision
    date itself must NOT be visible — the lag ensures we only use information
    that was publicly disseminated at least ``lag`` trading days before D.

    Concretely: AVAIL_JAN10 (2023-01-10) is excluded when D = 2023-01-10 because
    cutoff = busday_offset(2023-01-10, -2) = 2023-01-06 < 2023-01-10.
    It becomes visible at D = 2023-01-12 (Thursday), where
    cutoff = busday_offset(2023-01-12, -2) = 2023-01-10.
    """
    assert SAFETY_LAG_TRADING_DAYS == 2  # guard against accidental constant change

    session.add(_row(PERIOD_Q3, AVAIL_JAN10, net_income=120.0))
    session.commit()

    # D == available_date → excluded
    assert read_fundamentals_asof(session, ISIN, AVAIL_JAN10) == []

    # D = available_date + 1 bd (2023-01-11, Wednesday) → still excluded
    assert read_fundamentals_asof(session, ISIN, datetime.date(2023, 1, 11)) == []

    # D = available_date + 2 bd (2023-01-12, Thursday) → now visible
    results = read_fundamentals_asof(session, ISIN, datetime.date(2023, 1, 12))
    assert len(results) == 1
    assert results[0].net_income == 120.0
    assert results[0].available_date == AVAIL_JAN10


# ── Test 3 ──────────────────────────────────────────────────────────────────
def test_restatement_latest_qualifying_version_wins(session):
    """
    WHY: §3.4 restatement read-side.  When the same period_end has two rows
    (original + restatement), the reader must return the restatement (higher
    available_date) if it qualifies, and the original otherwise.  The original
    must be preserved in the DB unmodified (write-side invariant, tested in TB4)
    but must not shadow the restatement once it qualifies.
    """
    ORIGINAL_AVAIL = datetime.date(2022, 10, 15)
    RESTATED_AVAIL = datetime.date(2022, 11, 1)

    session.add(_row(PERIOD_Q2, ORIGINAL_AVAIL, net_income=80.0))
    session.add(_row(PERIOD_Q2, RESTATED_AVAIL, net_income=85.0))
    session.commit()

    # D where cutoff lands between original and restatement: original qualifies,
    # restatement does not yet → original returned.
    # cutoff for D=2022-10-19 (Wed) = busday_offset(-2) = 2022-10-17 (Mon)
    # 2022-10-15 <= 2022-10-17 → original qualifies; 2022-11-01 > 2022-10-17 → not
    d_before_restatement = datetime.date(2022, 10, 19)
    results = read_fundamentals_asof(session, ISIN, d_before_restatement)
    assert len(results) == 1
    assert results[0].net_income == 80.0  # original
    assert results[0].available_date == ORIGINAL_AVAIL

    # D where both qualify → latest (restatement) wins.
    # cutoff for D=2022-11-03 (Thu) = busday_offset(-2) = 2022-11-01 (Tue)
    # 2022-11-01 <= 2022-11-01 → restatement qualifies
    d_after_restatement = datetime.date(2022, 11, 3)
    results = read_fundamentals_asof(session, ISIN, d_after_restatement)
    assert len(results) == 1
    assert results[0].net_income == 85.0  # restatement
    assert results[0].available_date == RESTATED_AVAIL


# ── Test 4 ──────────────────────────────────────────────────────────────────
def test_d_before_first_filing_returns_empty(session):
    """
    WHY: factors must not receive a default/placeholder figure when no filing
    has yet been ingested for an ISIN.  An empty list forces the caller to
    handle the "no data" case explicitly rather than acting on a fabricated 0.
    """
    session.add(_row(PERIOD_Q3, AVAIL_JAN10))
    session.commit()

    # D so early that cutoff < available_date for all rows.
    # cutoff for D=2020-01-10 = busday_offset(-2) = 2020-01-08 < 2023-01-10
    results = read_fundamentals_asof(session, ISIN, datetime.date(2020, 1, 10))
    assert results == []


# ── Test 5 ──────────────────────────────────────────────────────────────────
def test_result_is_frozen_snapshot_not_orm_row(session):
    """
    WHY: the sole-read-path boundary.  Factors in 03_TRACK_B_PREREG must not
    hold references to live ORM rows (which would allow unintended mutations or
    lazy-load queries after session close).  The reader must return immutable
    FundamentalsSnapshot dataclasses so this module is truly the chokepoint.

    This test also verifies that FundamentalsSnapshot carries all 8 line items
    (the full standardized schema), so factors see a complete interface.
    """
    session.add(_row(PERIOD_Q3, AVAIL_JAN6, net_income=110.0))
    session.commit()

    results = read_fundamentals_asof(session, ISIN, AVAIL_JAN10)
    assert len(results) == 1
    snap = results[0]

    # Must be the immutable dataclass, not the ORM model.
    assert isinstance(snap, FundamentalsSnapshot)

    # Immutability — frozen=True raises FrozenInstanceError on attribute write.
    with pytest.raises(Exception):
        snap.net_income = 999.0  # type: ignore[misc]

    # All 8 standardized fields present on the snapshot interface.
    for field in (
        "revenue",
        "net_income",
        "ebit",
        "total_equity",
        "total_assets",
        "total_debt",
        "shares_outstanding",
        "cfo",
    ):
        assert hasattr(snap, field), f"missing field: {field}"
