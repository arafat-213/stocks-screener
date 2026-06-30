"""F3 — Turnover-to-date vs backtest expectation tests (specs/v3/12 F3).

WHY these tests matter (Rule 9):
- Live turnover must match Σ|qty × fill_price| / avg_nav for forward fills. The formula
  is the two-way definition: every buy and sell counted. A bug that omits one side (e.g.
  only buys) halves the reported turnover vs the frozen S3 expectation.
- Warm-start fills must be excluded. Fills with decision_date < go_live are replay,
  not forward accrual. Including them would inflate live turnover with non-live trades.
- Expected turnover must come from S3_EXPECTED_TURNOVER_TWO_WAY_PCT (a documented frozen
  constant in s3_config.py), not a literal in the endpoint. A test that reads the
  constant via the same import path as the endpoint ensures the two stay in sync.
- Basis must be "two-way". The convention (buys + sells counted) is the same as
  backtest_v2 metrics._compute_annualized_turnover; if the endpoint silently uses
  one-way, ratio comparisons against the 581% expected figure are off by 2×.
- No forward fills or no forward days yields live=0, ratio=0 (not an error).
"""

from __future__ import annotations

import datetime
from datetime import date

import pytest

from app.db.models import (
    PaperV2DailySnapshot,
    PaperV2PendingFill,
    PaperV2Portfolio,
)
from app.paper_v2.live_engine import PROBATION_BOOK_NAME
from app.paper_v2.s3_config import S3_EXPECTED_TURNOVER_TWO_WAY_PCT

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GO_LIVE = datetime.datetime(2026, 6, 23, tzinfo=datetime.timezone.utc)
_GO_LIVE_DATE = date(2026, 6, 23)


def _make_book(db) -> PaperV2Portfolio:
    pf = PaperV2Portfolio(
        name=PROBATION_BOOK_NAME,
        starting_capital=1_000_000.0,
        cash=1_000_000.0,
        is_active=True,
        last_processed_date=date(2026, 6, 30),
        created_at=_GO_LIVE,
    )
    db.add(pf)
    db.flush()
    return pf


def _make_fill(
    db,
    portfolio_id: int,
    *,
    decision_date: date,
    side: str = "buy",
    qty: float = 10.0,
    fill_price: float = 100.0,
    cost_rupees: float = 10.0,
    status: str = "filled",
    reason: str = "rebalance",
) -> PaperV2PendingFill:
    f = PaperV2PendingFill(
        portfolio_id=portfolio_id,
        isin="INE000000001",
        symbol="TEST.NS",
        side=side,
        qty=qty,
        reason=reason,
        decision_date=decision_date,
        decision_price=fill_price,
        status=status,
        fill_date=decision_date + datetime.timedelta(days=1),
        fill_price=fill_price,
        cost_rupees=cost_rupees,
    )
    db.add(f)
    db.flush()
    return f


def _make_fwd_snapshot(
    db, portfolio_id: int, *, snap_date: date, equity: float = 1_000_000.0
) -> PaperV2DailySnapshot:
    s = PaperV2DailySnapshot(
        portfolio_id=portfolio_id,
        date=snap_date,
        equity=equity,
        cash=500_000.0,
        invested_value=500_000.0,
        exposure=0.5,
        n_positions=10,
        index_level=10_000.0,
        is_forward=True,
    )
    db.add(s)
    db.flush()
    return s


def _make_warmstart_snapshot(
    db, portfolio_id: int, *, snap_date: date, equity: float = 1_000_000.0
) -> PaperV2DailySnapshot:
    s = PaperV2DailySnapshot(
        portfolio_id=portfolio_id,
        date=snap_date,
        equity=equity,
        cash=500_000.0,
        invested_value=500_000.0,
        exposure=0.5,
        n_positions=10,
        index_level=10_000.0,
        is_forward=False,
    )
    db.add(s)
    db.flush()
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_live_turnover_matches_sum_notional_over_avg_nav(client, db):
    """Live turnover = Σ|qty × fill_price| / avg_nav, annualized.

    With known fill values we can verify the formula directly. A bug in the
    notional sum (e.g. using qty only, or omitting one fill) produces a wrong ratio.
    """
    book = _make_book(db)
    # 252 forward days → exactly 1 year, so annualized = raw ratio
    for i in range(252):
        _make_fwd_snapshot(
            db,
            book.id,
            snap_date=date(2026, 6, 23) + datetime.timedelta(days=i),
            equity=1_000_000.0,
        )

    # Two fills on a forward date: buy 100 shares at 500, sell 50 shares at 600
    _make_fill(
        db,
        book.id,
        decision_date=_GO_LIVE_DATE,
        side="buy",
        qty=100.0,
        fill_price=500.0,
    )
    _make_fill(
        db,
        book.id,
        decision_date=_GO_LIVE_DATE,
        side="sell",
        qty=50.0,
        fill_price=600.0,
    )

    resp = client.get("/api/v2/paper/turnover")
    assert resp.status_code == 200
    data = resp.json()

    # Expected: (100×500 + 50×600) / 1_000_000 × (252/252) × 100
    # = (50_000 + 30_000) / 1_000_000 × 100 = 80_000 / 1_000_000 × 100 = 8.0%
    expected_live = (100.0 * 500.0 + 50.0 * 600.0) / 1_000_000.0 * 100.0
    assert abs(data["live_annualized_pct"] - expected_live) < 0.001


def test_basis_is_always_two_way(client, db):
    """basis field must always be 'two-way' — the convention the expected figure uses.

    The frozen S3 expected turnover (581%) was measured as two-way (buys + sells).
    A one-way live figure would produce a ratio off by ~2×. Asserting the basis label
    prevents silent convention drift.
    """
    book = _make_book(db)
    _make_fwd_snapshot(db, book.id, snap_date=_GO_LIVE_DATE)

    resp = client.get("/api/v2/paper/turnover")
    assert resp.status_code == 200
    assert resp.json()["basis"] == "two-way"


def test_expected_pct_matches_frozen_constant(client, db):
    """expected_pct must equal S3_EXPECTED_TURNOVER_TWO_WAY_PCT from s3_config.py.

    The expected figure is a frozen documented constant (FINAL_OOS R10.3, `10` §R10.3).
    If the endpoint uses a hardcoded literal instead of the constant, a future update
    to s3_config.py would silently diverge. This test imports the same constant the
    endpoint imports to catch that drift.
    """
    _make_book(db)
    resp = client.get("/api/v2/paper/turnover")
    assert resp.status_code == 200
    assert resp.json()["expected_pct"] == pytest.approx(
        S3_EXPECTED_TURNOVER_TWO_WAY_PCT
    )


def test_warm_start_fills_excluded(client, db):
    """Fills with decision_date < go_live must not count toward live turnover.

    The warm-start replay bootstraps the portfolio using historical data — those
    trades are not forward accrual. Including them would inflate live turnover
    by counting non-live execution.
    """
    book = _make_book(db)
    _make_fwd_snapshot(db, book.id, snap_date=_GO_LIVE_DATE)

    # Warm-start fill: decision_date before go_live
    _make_fill(
        db,
        book.id,
        decision_date=date(2026, 6, 20),  # 3 days before go_live 2026-06-23
        side="buy",
        qty=1000.0,
        fill_price=1000.0,  # huge notional
    )
    # One small forward fill to ensure non-zero if warm-start was included
    _make_fill(
        db,
        book.id,
        decision_date=_GO_LIVE_DATE,
        side="buy",
        qty=1.0,
        fill_price=1.0,
    )

    resp = client.get("/api/v2/paper/turnover")
    assert resp.status_code == 200
    data = resp.json()
    # If warm-start was included: (1_000_000 + 1) / 1_000_000 × (252/1) × 100 ≈ 25_200%
    # If excluded correctly: only 1×1 = 1 / 1_000_000 × (252/1) × 100 ≈ 0.0252%
    assert data["live_annualized_pct"] < 1.0, (
        f"Warm-start fills were included: live={data['live_annualized_pct']:.2f}%"
    )


def test_pending_fills_excluded(client, db):
    """Fills with status='pending' must not count toward live turnover.

    Pending fills haven't executed; including them would count hypothetical trades.
    This matches the same exclusion in F2 (cost ledger).
    """
    book = _make_book(db)
    _make_fwd_snapshot(db, book.id, snap_date=_GO_LIVE_DATE)

    # Pending forward fill — large notional
    _make_fill(
        db,
        book.id,
        decision_date=_GO_LIVE_DATE,
        side="buy",
        qty=1000.0,
        fill_price=1000.0,
        status="pending",
    )

    resp = client.get("/api/v2/paper/turnover")
    assert resp.status_code == 200
    data = resp.json()
    # Only pending → no forward fills → live should be 0.0
    assert data["live_annualized_pct"] == pytest.approx(0.0)
    assert data["ratio"] == pytest.approx(0.0)


def test_no_fills_returns_zero_live(client, db):
    """No forward fills → live_annualized_pct=0.0, ratio=0.0.

    On go-live day or before any rebalance fires, the endpoint must return a valid
    zero-filled response rather than raising an error.
    """
    book = _make_book(db)
    _make_fwd_snapshot(db, book.id, snap_date=_GO_LIVE_DATE)

    resp = client.get("/api/v2/paper/turnover")
    assert resp.status_code == 200
    data = resp.json()
    assert data["live_annualized_pct"] == pytest.approx(0.0)
    assert data["ratio"] == pytest.approx(0.0)
    assert data["n_forward_days"] == 1


def test_no_book_returns_zero_response(client, db):
    """No active book → valid zero-filled TurnoverResponse, not a 404 or 500.

    The page loads before the book is armed; it must not crash.
    """
    resp = client.get("/api/v2/paper/turnover")
    assert resp.status_code == 200
    data = resp.json()
    assert data["live_annualized_pct"] == pytest.approx(0.0)
    assert data["expected_pct"] == pytest.approx(S3_EXPECTED_TURNOVER_TWO_WAY_PCT)
    assert data["basis"] == "two-way"


def test_ratio_computed_from_live_over_expected(client, db):
    """ratio = live_annualized_pct / expected_pct.

    The ratio is the primary signal for the fidelity check. A bug that inverts it
    (expected / live) or omits it entirely produces a misleading gauge.
    """
    book = _make_book(db)
    # 252 forward days = 1 annualization year
    for i in range(252):
        _make_fwd_snapshot(
            db,
            book.id,
            snap_date=date(2026, 6, 23) + datetime.timedelta(days=i),
            equity=1_000_000.0,
        )

    # Fill to produce live_annualized_pct = S3_EXPECTED_TURNOVER_TWO_WAY_PCT (ratio ≈ 1.0)
    # live = notional / avg_nav × (252/252) × 100 → notional = expected/100 × avg_nav
    target_notional = S3_EXPECTED_TURNOVER_TWO_WAY_PCT / 100.0 * 1_000_000.0
    _make_fill(
        db,
        book.id,
        decision_date=_GO_LIVE_DATE,
        side="buy",
        qty=target_notional,
        fill_price=1.0,
    )

    resp = client.get("/api/v2/paper/turnover")
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["ratio"] - 1.0) < 0.01, (
        f"Expected ratio ≈ 1.0, got {data['ratio']:.4f}"
    )


def test_n_forward_days_reflects_is_forward_snapshots(client, db):
    """n_forward_days counts only is_forward=True snapshots (not warm-start).

    The annualization denominator must use forward trading days, not total elapsed
    days. A warm-start snapshot (is_forward=False) must not inflate n_forward_days
    and thereby shrink the annualization factor.
    """
    book = _make_book(db)
    # 5 forward snapshots
    for i in range(5):
        _make_fwd_snapshot(
            db,
            book.id,
            snap_date=date(2026, 6, 23) + datetime.timedelta(days=i),
        )
    # 3 warm-start snapshots (must NOT be counted)
    for i in range(3):
        _make_warmstart_snapshot(
            db,
            book.id,
            snap_date=date(2026, 6, 18) + datetime.timedelta(days=i),
        )

    resp = client.get("/api/v2/paper/turnover")
    assert resp.status_code == 200
    assert resp.json()["n_forward_days"] == 5
