"""
TB6 — corporate-action consistency invariant tests (Rule 9: encode WHY each matters).

All tests use an in-memory SQLite DB — no network, no Postgres.

Test matrix:
  1. market_cap_raw is continuous across a 2:1 split (raw × raw convention).
  2. book_to_price_raw is continuous across the same split.
  3. Adjusted price × raw shares gives a ×2 discontinuity — proves why raw × raw is needed.
  4. reconcile_ca_consistency marks an ISIN ok when shares ratio matches adj_factor step.
  5. reconcile_ca_consistency surfaces a mismatch when shares ratio diverges from step.
"""

import datetime

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base
from app.fundamentals.ca_consistency import (
    book_to_price_raw,
    market_cap_raw,
    reconcile_ca_consistency,
)
from app.fundamentals.models import FundamentalsLineItemVersion, FundamentalsUniverse

ISIN = "INE001A01036"

# ── split scenario constants ──────────────────────────────────────────────────
# 2:1 split on 2022-06-01.
# Pre-split: close_raw=1000, adj_factor=0.5 → close=500; shares=100_000_000
# Post-split: close_raw=500,  adj_factor=1.0 → close=500; shares=200_000_000
# total_equity=10_000_000_000 (₹10B, monetary — not per-share, constant across splits)

CLOSE_RAW_PRE = 1000.0
CLOSE_ADJ_PRE = 500.0  # close_raw × adj_factor = 1000 × 0.5
SHARES_PRE = 100_000_000.0
ADJ_FACTOR_PRE = 0.5

CLOSE_RAW_POST = 500.0
CLOSE_ADJ_POST = 500.0  # close_raw × adj_factor = 500 × 1.0
SHARES_POST = 200_000_000.0
ADJ_FACTOR_POST = 1.0

TOTAL_EQUITY = 10_000_000_000.0  # ₹10B — monetary total, split-invariant

SPLIT_EXDATE = datetime.date(2022, 6, 1)
PERIOD_PRE = datetime.date(2022, 3, 31)  # FY22 balance sheet (pre-split shares)
PERIOD_POST = datetime.date(2023, 3, 31)  # FY23 balance sheet (post-split shares)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(FundamentalsUniverse(isin=ISIN, exchange="NSE"))
        s.commit()
        yield s


def _add_snapshots(
    session: Session,
    shares_pre: float = SHARES_PRE,
    shares_post: float = SHARES_POST,
) -> None:
    """Insert two annual snapshots straddling the split."""
    # FY22 filing: available 30 days after period_end
    session.add(
        FundamentalsLineItemVersion(
            isin=ISIN,
            period_end=PERIOD_PRE,
            available_date=datetime.date(2022, 4, 30),
            statement_type="Annual",
            total_equity=TOTAL_EQUITY,
            shares_outstanding=shares_pre,
        )
    )
    # FY23 filing: available 30 days after period_end
    session.add(
        FundamentalsLineItemVersion(
            isin=ISIN,
            period_end=PERIOD_POST,
            available_date=datetime.date(2023, 4, 30),
            statement_type="Annual",
            total_equity=TOTAL_EQUITY,
            shares_outstanding=shares_post,
        )
    )
    session.commit()


def _price_reader(
    adj_factor_pre: float = ADJ_FACTOR_PRE,
    adj_factor_post: float = ADJ_FACTOR_POST,
):
    """Return a PriceReader that yields a synthetic split around SPLIT_EXDATE."""

    def _reader(isin: str, start: datetime.date, end: datetime.date) -> pd.DataFrame:
        rows = [
            {
                "date": pd.Timestamp("2022-05-31"),
                "close_raw": CLOSE_RAW_PRE,
                "adj_factor": adj_factor_pre,
            },
            {
                "date": pd.Timestamp(SPLIT_EXDATE),
                "close_raw": CLOSE_RAW_POST,
                "adj_factor": adj_factor_post,
            },
        ]
        return pd.DataFrame(rows)

    return _reader


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — market_cap_raw is continuous across a 2:1 split (WHY: a ×2
# discontinuity in market cap would corrupt any price-relative factor).
# ─────────────────────────────────────────────────────────────────────────────
def test_market_cap_raw_continuous_across_split():
    mc_pre = market_cap_raw(CLOSE_RAW_PRE, SHARES_PRE)
    mc_post = market_cap_raw(CLOSE_RAW_POST, SHARES_POST)
    # 1000 × 100M = 100B  and  500 × 200M = 100B  — identical, split-invariant.
    assert mc_pre == pytest.approx(100_000_000_000.0)
    assert mc_post == pytest.approx(100_000_000_000.0)
    assert mc_pre == pytest.approx(mc_post, rel=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — book_to_price_raw is continuous across the same 2:1 split (WHY:
# a step-change in B/P at a pure accounting event is a look-ahead error).
# ─────────────────────────────────────────────────────────────────────────────
def test_book_to_price_raw_continuous_across_split():
    b2p_pre = book_to_price_raw(TOTAL_EQUITY, CLOSE_RAW_PRE, SHARES_PRE)
    b2p_post = book_to_price_raw(TOTAL_EQUITY, CLOSE_RAW_POST, SHARES_POST)
    # 10B / 100B = 0.1 both sides.
    assert b2p_pre == pytest.approx(0.1, rel=1e-9)
    assert b2p_post == pytest.approx(0.1, rel=1e-9)
    assert b2p_pre == pytest.approx(b2p_post, rel=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — adjusted price × raw shares creates an artificial ×2 jump (WHY:
# proves the basis mismatch that raw × raw is designed to prevent).
# ─────────────────────────────────────────────────────────────────────────────
def test_adjusted_price_times_raw_shares_is_discontinuous():
    # Both dates show the same adjusted price (500), but shares step from 100M → 200M.
    mc_wrong_pre = CLOSE_ADJ_PRE * SHARES_PRE  # 500 × 100M = 50B
    mc_wrong_post = CLOSE_ADJ_POST * SHARES_POST  # 500 × 200M = 100B
    # The ratio must be ≈ 2 — a pure accounting event creates a ×2 discontinuity.
    assert mc_wrong_post / mc_wrong_pre == pytest.approx(2.0, rel=1e-9)
    # And the correct raw × raw computation is NOT equal to the wrong one pre-split.
    mc_correct_pre = market_cap_raw(CLOSE_RAW_PRE, SHARES_PRE)
    assert mc_correct_pre != pytest.approx(mc_wrong_pre, rel=1e-3)


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — reconcile marks ISIN ok when XBRL shares ratio matches adj_factor
# step (WHY: ensures the reconciler accepts a correctly reported split).
# ─────────────────────────────────────────────────────────────────────────────
def test_reconcile_ok_when_shares_ratio_matches_adj_factor_step(session):
    # FY22: 100M shares, FY23: 200M shares (2:1 split correctly reflected in XBRL).
    _add_snapshots(session, shares_pre=SHARES_PRE, shares_post=SHARES_POST)

    start = datetime.date(2022, 1, 1)
    end = datetime.date(2022, 12, 31)
    report = reconcile_ca_consistency(session, _price_reader(), [ISIN], start, end)

    assert ISIN in report.ok_isins, f"Expected ISIN in ok_isins; got {report}"
    assert len(report.mismatches) == 0
    assert report.ok


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — reconcile surfaces a mismatch when XBRL shares ratio diverges from
# the adj_factor step (WHY: a silent mismatch would corrupt every per-share
# factor — market cap, earnings yield, B/P — without any error signal).
# ─────────────────────────────────────────────────────────────────────────────
def test_reconcile_surfaces_mismatch_when_shares_inconsistent_with_adj_factor(session):
    # XBRL only shows +10% shares (110M), but adj_factor implies a 2:1 split (×2).
    _add_snapshots(session, shares_pre=SHARES_PRE, shares_post=110_000_000.0)

    start = datetime.date(2022, 1, 1)
    end = datetime.date(2022, 12, 31)
    report = reconcile_ca_consistency(session, _price_reader(), [ISIN], start, end)

    assert len(report.mismatches) == 1, f"Expected 1 mismatch; got {report.mismatches}"
    m = report.mismatches[0]
    assert m.isin == ISIN
    assert m.ex_date == SPLIT_EXDATE
    assert m.step_ratio == pytest.approx(2.0, rel=1e-6)
    # Observed ratio = 110M / 100M = 1.1; expected = 2.0 → >2% tolerance breach.
    assert m.shares_ratio_observed == pytest.approx(1.1, rel=1e-6)
    assert not report.ok
