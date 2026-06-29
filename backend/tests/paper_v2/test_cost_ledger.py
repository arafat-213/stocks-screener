"""F2 — Realized-vs-modeled cost ledger tests (specs/v3/12 F2).

WHY these tests matter (Rule 9):
- Realized cost must reconcile exactly to Σ cost_rupees + timing slippage. The
  formula is the definition of "what we paid": statutory fees stored at fill time
  plus the price drift between decision-close and fill-open (next-open vs close).
  If either component is missing the cost is understated.
- within_band must flip at the pessimistic threshold, not at base. The gate in
  §2.3 is 'realized ≤ pessimistic' — the range [base, pessimistic] is the BAND;
  being below base is still within band. A bug that treats base as the ceiling
  would produce false failures.
- Pending fills must be excluded. They haven't executed; including them would
  inflate realized cost with hypothetical trades and distort the %/yr drag.
- Annualisation must use forward-day count from paper_v2_daily_snapshot
  (is_forward=True only), not calendar days. Warm-start replay is backtest, not
  live elapsed time — the same boundary the NAV curve divides at go-live.
- Modeled cost must come from costs.py fill_cost / effective_price (Rule 5). Any
  inline re-derivation of the statutory formula or slippage model drifts the
  moment rates change. The test asserts the endpoint output matches what costs.py
  returns directly.
"""

from __future__ import annotations

import datetime
from datetime import date

from app.backtest_v2.costs import CostConfig, effective_price, fill_cost
from app.db.models import (
    PaperV2DailySnapshot,
    PaperV2PendingFill,
    PaperV2Portfolio,
)
from app.paper_v2.live_engine import PROBATION_BOOK_NAME

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GO_LIVE = datetime.datetime(2026, 6, 23, tzinfo=datetime.timezone.utc)


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
    decision_price: float = 100.0,
    fill_price: float = 101.0,
    cost_rupees: float = 15.0,
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
        decision_price=decision_price,
        status=status,
        fill_date=decision_date + datetime.timedelta(days=1),
        fill_price=fill_price,
        cost_rupees=cost_rupees,
    )
    db.add(f)
    db.flush()
    return f


def _make_fwd_snapshot(
    db, portfolio_id: int, *, snap_date: date, equity: float = 1_010_000.0
):
    s = PaperV2DailySnapshot(
        portfolio_id=portfolio_id,
        date=snap_date,
        equity=equity,
        cash=500_000.0,
        invested_value=510_000.0,
        exposure=0.505,
        n_positions=10,
        index_level=10_000.0,
        is_forward=True,
    )
    db.add(s)
    db.flush()
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_realized_cost_reconciles_to_statutory_plus_timing_slippage(client, db):
    """Realized cost = stored cost_rupees + |fill_price - decision_price| × qty.

    This is the definition: statutory fees (already computed at fill time) plus
    the timing drift from decision-close to next-open (the paper-fill caveat).
    A bug that drops the timing component understates cost; dropping statutory
    overstates consistency with the model.
    """
    book = _make_book(db)
    _make_fill(
        db,
        book.id,
        decision_date=date(2026, 6, 25),
        side="buy",
        qty=10.0,
        decision_price=100.0,
        fill_price=103.0,  # 3 rupee timing slippage per share
        cost_rupees=25.0,
        status="filled",
    )
    _make_fwd_snapshot(db, book.id, snap_date=date(2026, 6, 25))
    _make_fwd_snapshot(db, book.id, snap_date=date(2026, 6, 26))

    resp = client.get("/api/v2/paper/cost-ledger")
    assert resp.status_code == 200
    data = resp.json()

    # Timing slippage = |103 - 100| × 10 = 30 rupees; statutory = 25 rupees.
    expected_realized = 25.0 + 30.0  # 55 rupees
    # Traded notional = 10 × 103 = 1030
    expected_realized_bps = expected_realized / 1030.0 * 10_000

    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert abs(row["realized_cost_rupees"] - expected_realized) < 0.01, (
        f"realized_cost_rupees should be statutory+timing={expected_realized}, got {row['realized_cost_rupees']}"
    )
    assert abs(row["realized_bps"] - expected_realized_bps) < 0.01
    assert abs(data["realized_bps_total"] - expected_realized_bps) < 0.01


def test_within_band_flips_at_pessimistic_edge_not_base(client, db):
    """within_band=True when realized ≤ pessimistic; False only when realized > pessimistic.

    The gate is the PESSIMISTIC edge (§2.3). Being above base but below pessimistic
    is still WITHIN band — that's the whole point of the [base..pessimistic] range.
    """
    book = _make_book(db)

    # Compute what pessimistic modeled cost would be for a specific fill.
    side, qty, fill_price = "buy", 100.0, 200.0
    cfg_pess = CostConfig.pessimistic()
    pess_cost = (
        fill_cost(side, qty, fill_price, 0.0, cfg_pess)
        + abs(effective_price(side, fill_price, qty, 0.0, cfg_pess) - fill_price) * qty
    )

    # Case A: realized just BELOW pessimistic (within band).
    cost_below = pess_cost * 0.95  # 5% below → within band
    _make_fill(
        db,
        book.id,
        decision_date=date(2026, 6, 25),
        qty=qty,
        fill_price=fill_price,
        decision_price=fill_price,  # no timing slippage
        cost_rupees=cost_below,
        status="filled",
    )
    _make_fwd_snapshot(db, book.id, snap_date=date(2026, 6, 25))

    resp = client.get("/api/v2/paper/cost-ledger")
    assert resp.status_code == 200
    assert resp.json()["within_band"] is True, (
        "realized below pessimistic must be within_band=True"
    )


def test_within_band_false_when_realized_exceeds_pessimistic(client, db):
    """Exceeding the pessimistic band sets within_band=False (the kill-watch signal)."""
    book = _make_book(db)

    side, qty, fill_price = "buy", 100.0, 200.0
    cfg_pess = CostConfig.pessimistic()
    pess_cost = (
        fill_cost(side, qty, fill_price, 0.0, cfg_pess)
        + abs(effective_price(side, fill_price, qty, 0.0, cfg_pess) - fill_price) * qty
    )

    # Realized well above pessimistic (decision_price far from fill_price adds timing slippage).
    # Use a decision_price that creates enough timing slippage to exceed pess_cost.
    huge_timing = pess_cost * 2.0  # 200% of pessimistic = definitely exceeds band
    _make_fill(
        db,
        book.id,
        decision_date=date(2026, 6, 25),
        qty=qty,
        fill_price=fill_price,
        decision_price=fill_price - (huge_timing / qty),  # forces large timing slippage
        cost_rupees=0.0,  # statutory = 0 to isolate timing
        status="filled",
    )
    _make_fwd_snapshot(db, book.id, snap_date=date(2026, 6, 25))

    resp = client.get("/api/v2/paper/cost-ledger")
    assert resp.status_code == 200
    assert resp.json()["within_band"] is False, (
        "realized exceeding pessimistic band must set within_band=False"
    )


def test_pending_fills_excluded_from_realized_cost(client, db):
    """Pending fills must NOT count toward realized cost.

    They haven't executed — including them would inflate the cost with hypothetical
    trades. The gate measures what actually happened, not what was queued.
    """
    book = _make_book(db)
    _make_fwd_snapshot(db, book.id, snap_date=date(2026, 6, 25))

    # One filled fill + one pending fill with enormous cost.
    _make_fill(
        db,
        book.id,
        decision_date=date(2026, 6, 25),
        cost_rupees=50.0,
        fill_price=100.0,
        decision_price=100.0,
        qty=10.0,
        status="filled",
    )
    _make_fill(
        db,
        book.id,
        decision_date=date(2026, 6, 25),
        cost_rupees=9_999_999.0,  # enormous — must NOT appear in realized
        fill_price=100.0,
        decision_price=100.0,
        qty=1000.0,
        status="pending",
    )

    resp = client.get("/api/v2/paper/cost-ledger")
    assert resp.status_code == 200
    data = resp.json()
    # Only the filled fill's cost should appear; pending fill is excluded.
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["realized_cost_rupees"] < 1_000.0, (
        "pending fill cost must not contaminate realized_cost_rupees"
    )


def test_annualization_uses_forward_day_count_not_calendar_days(client, db):
    """Drag %/yr uses n forward days from is_forward snapshots, not calendar elapsed.

    Warm-start replay days are excluded (is_forward=False). If annualisation used
    calendar days or all snapshot rows, the drag rate would be understated during
    the early warm-start period.
    """
    book = _make_book(db)
    _make_fill(
        db,
        book.id,
        decision_date=date(2026, 6, 25),
        cost_rupees=1_000.0,
        fill_price=100.0,
        decision_price=100.0,
        qty=10.0,
        status="filled",
    )

    # Add 10 forward snapshots.
    equity = 1_010_000.0
    for i in range(10):
        snap = PaperV2DailySnapshot(
            portfolio_id=book.id,
            date=date(2026, 6, 24) + datetime.timedelta(days=i + 1),
            equity=equity,
            cash=500_000.0,
            invested_value=510_000.0,
            exposure=0.505,
            n_positions=10,
            index_level=10_000.0,
            is_forward=True,
        )
        db.add(snap)
    # Add a warm-start snapshot (is_forward=False) — must NOT count toward n_forward_days.
    warmstart = PaperV2DailySnapshot(
        portfolio_id=book.id,
        date=date(2026, 6, 23),
        equity=1_000_000.0,
        cash=1_000_000.0,
        invested_value=0.0,
        exposure=0.0,
        n_positions=0,
        index_level=10_000.0,
        is_forward=False,
    )
    db.add(warmstart)
    db.flush()

    resp = client.get("/api/v2/paper/cost-ledger")
    data = resp.json()

    # Expected drag: total_realized / avg_nav × (252/10) × 100
    avg_nav = equity  # all 10 snapshots have same equity
    expected_drag = (1_000.0 / avg_nav) * (252.0 / 10) * 100.0
    assert abs(data["realized_drag_pct_yr"] - expected_drag) < 0.001, (
        f"drag={data['realized_drag_pct_yr']:.4f} should be {expected_drag:.4f} "
        f"(10 forward days; warm-start excluded)"
    )


def test_modeled_cost_matches_costs_py_output(client, db):
    """Modeled cost must come from costs.py fill_cost + effective_price (Rule 5).

    If the endpoint re-derives the formula it will drift when rates change.
    Assert here that the row's modeled_base_bps equals what costs.py returns
    for the same fill, so any future rate-table update propagates automatically.
    """
    book = _make_book(db)
    side, qty, fill_price = "buy", 20.0, 150.0
    _make_fill(
        db,
        book.id,
        decision_date=date(2026, 6, 25),
        side=side,
        qty=qty,
        fill_price=fill_price,
        decision_price=fill_price,  # zero timing slippage
        cost_rupees=0.0,
        status="filled",
    )
    _make_fwd_snapshot(db, book.id, snap_date=date(2026, 6, 25))

    cfg_base = CostConfig.base()
    expected_base = (
        fill_cost(side, qty, fill_price, 0.0, cfg_base)
        + abs(effective_price(side, fill_price, qty, 0.0, cfg_base) - fill_price) * qty
    )
    notional = qty * fill_price
    expected_base_bps = expected_base / notional * 10_000

    resp = client.get("/api/v2/paper/cost-ledger")
    assert resp.status_code == 200
    row = resp.json()["rows"][0]
    assert abs(row["modeled_base_bps"] - expected_base_bps) < 0.01, (
        f"modeled_base_bps {row['modeled_base_bps']:.4f} must match costs.py output "
        f"{expected_base_bps:.4f} — no inline re-derivation allowed (Rule 5)"
    )


def test_empty_response_when_no_active_book(client, db):
    """No active book → 200 with zero values (never a 404 or unhandled error)."""
    resp = client.get("/api/v2/paper/cost-ledger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["realized_bps_total"] == 0.0
    assert data["within_band"] is True
    assert data["rows"] == []


def test_no_filled_fills_returns_empty(client, db):
    """Book exists but no filled fills yet → zeros (probation just armed)."""
    book = _make_book(db)
    _make_fwd_snapshot(db, book.id, snap_date=date(2026, 6, 25))
    _make_fill(db, book.id, decision_date=date(2026, 6, 25), status="pending")

    resp = client.get("/api/v2/paper/cost-ledger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows"] == []
    assert data["realized_bps_total"] == 0.0


def test_rows_grouped_by_decision_date_newest_ascending(client, db):
    """Multiple fills on two decision dates → two rows, ascending by date.

    Row ordering mirrors /rebalances grouping so the ledger is scannable chronologically.
    """
    book = _make_book(db)
    _make_fwd_snapshot(db, book.id, snap_date=date(2026, 6, 25))
    _make_fwd_snapshot(db, book.id, snap_date=date(2026, 6, 28))
    _make_fill(
        db,
        book.id,
        decision_date=date(2026, 6, 28),
        status="filled",
        fill_price=100.0,
        cost_rupees=10.0,
        decision_price=100.0,
        qty=5.0,
    )
    _make_fill(
        db,
        book.id,
        decision_date=date(2026, 6, 25),
        status="filled",
        fill_price=100.0,
        cost_rupees=10.0,
        decision_price=100.0,
        qty=5.0,
    )

    resp = client.get("/api/v2/paper/cost-ledger")
    data = resp.json()
    dates = [r["decision_date"] for r in data["rows"]]
    assert dates == sorted(dates), "rows must be ascending by decision_date"
    assert len(dates) == 2
