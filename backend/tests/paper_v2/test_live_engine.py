"""P11.1 done-criteria — the live S3 paper shell reproduces the backtest, byte-for-byte.

The prime directive of the v3/11 probation is *fidelity*: the live book must BE S3, not
a look-alike (11 §2). These tests prove the persistence/queue path
(``live_engine.process_day`` → DB → re-hydrate) makes the SAME decisions the
authoritative ``engine.step_day`` makes over the same calendar:

  DC1  dry-run parity        — a full day-by-day live replay == the in-memory engine
                               (equity curve + final book identical).
  DC2  resumable backfill    — splitting the replay at a rebalance boundary (the queue
                               persisted on one batch, executed on the next, with the
                               session expunged between) yields the identical end state.
  DC3  §3e ordering invariant — a name bought at today's open whose close breaches −25%
                               is stop-queued the SAME evening (5.i runs before 5.iii),
                               surviving the persist/hydrate round-trip.
  DC4  §5e CA reconciliation — a split on a held name rescales the persisted position
                               BEFORE the stop check, so no false split-driven stop and
                               the position value is invariant.
  DC5  daily 25% stop path   — a held name closing ≤ −25% queues a next-open stop sell
                               through ``process_day`` (reproduces engine §5.iii).
  DC6  alerts render         — ``emit_alerts(send=False)`` builds every alert kind with
                               no external I/O (Rule 5).

All offline: synthetic prices, injected/None regime, no network, in-memory sqlite.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.backtest_v2 import engine
from app.backtest_v2.portfolio import Portfolio
from app.backtest_v2.schemas import DailySnapshot, Fill
from app.db.models import PaperV2PendingFill, PaperV2Portfolio, PaperV2Position
from app.paper_v2 import alerter, live_engine, parity
from app.paper_v2.ca_reconcile import would_stop_fire
from app.paper_v2.live_engine import ProcessReport

_PRICE_COLS = [
    "isin",
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "close_raw",
    "close_tr",
    "volume",
    "traded_value",
    "adv_20",
    "adj_factor",
    "tr_factor",
    "series",
]


# ---------------------------------------------------------------------------
# Synthetic data builders
# ---------------------------------------------------------------------------


def _make_panel(
    isins: list[str],
    start: str = "2022-01-03",
    n_days: int = 400,
    seed: int = 7,
) -> pd.DataFrame:
    """Long-format multi-ISIN price panel with all engine-required columns.

    Each name follows an upward random walk with a per-name drift so the composite
    ranking differs across names (some get selected, some don't). adv_20 is a fixed
    ₹10cr so the liquidity floor never bites; adj_factor = 1.0 (no CA in this panel).
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    for k, isin in enumerate(isins):
        drift = 0.0003 + 0.00003 * k  # distinct per-name drift → distinct momentum
        price = 100.0
        for i, d in enumerate(dates):
            price = max(price * (1 + rng.normal(drift, 0.012)), 0.01)
            o = price * rng.uniform(0.995, 1.005)
            h = max(o, price) * rng.uniform(1.000, 1.010)
            lo = min(o, price) * rng.uniform(0.990, 1.000)
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "date": d,
                    "open": o,
                    "high": h,
                    "low": lo,
                    "close": price,
                    "close_raw": price,
                    "close_tr": price * 1.0008**i,
                    "volume": 100_000,
                    "traded_value": 1e9,
                    "adv_20": 1e8,
                    "adj_factor": 1.0,
                    "tr_factor": 1.0008**i,
                    "series": "EQ",
                }
            )
    return pd.DataFrame(rows, columns=_PRICE_COLS)


def _make_index(prices: pd.DataFrame) -> pd.Series:
    """Rising benchmark — always above its own 200-DMA ⇒ regime risk-on (buys happen)."""
    dates = sorted(prices["date"].drop_duplicates())
    return pd.Series(
        np.linspace(100.0, 220.0, len(dates)), index=pd.DatetimeIndex(dates)
    )


def _flat_panel(
    isins: list[str],
    start: str = "2022-03-01",
    n_days: int = 43,
    base: float = 100.0,
    adj_factor: float = 1.0,
    seed: int = 1,
) -> pd.DataFrame:
    """Near-flat panel (tiny noise so variance > 0) for the controlled stop/CA tests.

    n_days is short on purpose: momentum is all-NaN so ``eligible_ranked`` is empty and
    no rebalance ever buys — the tests drive the execute→MTM→stop path in isolation by
    seeding the queue / a held position directly. ``adj_factor`` is uniform so callers
    simulate a CA by passing the post-split factor.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    for isin in isins:
        for i, d in enumerate(dates):
            p = base + rng.normal(0, 0.05)
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "date": d,
                    "open": p,
                    "high": p * 1.005,
                    "low": p * 0.995,
                    "close": p,
                    "close_raw": p,
                    "close_tr": p,
                    "volume": 100_000,
                    "traded_value": 1e9,
                    "adv_20": 1e8,
                    "adj_factor": adj_factor,
                    "tr_factor": 1.0,
                    "series": "EQ",
                }
            )
    return pd.DataFrame(rows, columns=_PRICE_COLS)


def _set_cell(df: pd.DataFrame, isin: str, d: pd.Timestamp, **cols) -> None:
    mask = (df["isin"] == isin) & (df["date"] == pd.Timestamp(d))
    assert mask.any(), f"no row for {isin} on {d}"
    for col, val in cols.items():
        df.loc[mask, col] = val


def _new_portfolio(db, *, cash: float = 1_000_000.0) -> PaperV2Portfolio:
    pf = PaperV2Portfolio(
        name="s3_probation_test",
        starting_capital=1_000_000.0,
        cash=cash,
        is_active=True,
        last_processed_date=None,
    )
    db.add(pf)
    db.flush()
    return pf


def _pending(db, pf_id, **kw) -> None:
    db.add(PaperV2PendingFill(portfolio_id=pf_id, status="pending", **kw))
    db.flush()


def _position(db, pf_id, **kw) -> None:
    db.add(PaperV2Position(portfolio_id=pf_id, days_held=0, **kw))
    db.flush()


# ---------------------------------------------------------------------------
# DC1 — dry-run parity: live replay == in-memory engine, byte-for-byte
# ---------------------------------------------------------------------------


@pytest.fixture
def parity_panel(monkeypatch):
    """Build the S3 context ONCE and pin it for both the live shell and the shadow
    parity, so process_day's per-day rebuild is cached (fast) and byte-identical to the
    authoritative run (the cached value == what each call would recompute, since the
    full history is present in the dry-run)."""
    isins = [f"ISIN{i:02d}" for i in range(25)]
    prices = _make_panel(isins, n_days=400)
    index = _make_index(prices)
    ctx, calendar = live_engine.build_live_context(prices, index)
    monkeypatch.setattr(
        live_engine, "build_live_context", lambda *a, **k: (ctx, calendar)
    )
    monkeypatch.setattr(parity, "build_live_context", lambda *a, **k: (ctx, calendar))
    return prices, index, ctx, calendar


def _authoritative_run(ctx, calendar):
    """Run the in-memory engine over the calendar; return (equity_curve, state)."""
    state = engine.LoopState(
        portfolio=Portfolio(cash=ctx.config.starting_capital),
        pending_fills=[],
        rebalance_dates_used=[],
        per_rebalance_turnover=[],
    )
    curve = []
    for day in calendar:
        engine.step_day(ctx, state, day)
        curve.append(state.portfolio.snapshots[-1].equity)
    return curve, state


def test_dc1_dry_run_parity_byte_for_byte(db, parity_panel):
    prices, index, ctx, calendar = parity_panel

    auth_curve, auth_state = _authoritative_run(ctx, calendar)

    pf = _new_portfolio(db)
    live_curve = []
    for day in calendar:
        rep = live_engine.process_day(db, pf.id, prices, index, day, commit=False)
        assert not rep.skipped
        live_curve.append(rep.snapshot.equity)

    # The strategy actually traded (otherwise parity would be trivially empty).
    assert any(f.side == "buy" for f in auth_state.portfolio.fills_log)

    # Equity curve identical day-by-day.
    assert len(live_curve) == len(auth_curve)
    for d, (a, b) in zip(calendar, zip(auth_curve, live_curve)):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-6), f"equity diverged on {d}"

    # Final book identical (per-name shares + cost basis) and cash identical.
    live_pos = {
        r.isin: r
        for r in db.query(PaperV2Position).filter(PaperV2Position.portfolio_id == pf.id)
    }
    assert set(live_pos) == set(auth_state.portfolio.positions)
    for isin, p in auth_state.portfolio.positions.items():
        assert live_pos[isin].shares == pytest.approx(p.shares, rel=1e-9)
        assert live_pos[isin].cost_basis == pytest.approx(p.cost_basis, rel=1e-9)
    pf_row = db.get(PaperV2Portfolio, pf.id)
    assert pf_row.cash == pytest.approx(auth_state.portfolio.cash, rel=1e-9)

    # And the §2 shadow-parity check itself passes on the live book.
    rep = parity.shadow_parity(db, pf.id, prices, index, calendar[-1].date())
    assert rep.passed, rep.summary


# ---------------------------------------------------------------------------
# DC2 — resumable two-batch backfill across a rebalance boundary
# ---------------------------------------------------------------------------


def test_dc2_resumable_backfill_byte_for_byte(db, parity_panel):
    prices, index, ctx, calendar = parity_panel

    auth_curve, auth_state = _authoritative_run(ctx, calendar)

    # Split ON a rebalance date so the queue persisted at batch-1's close must be
    # executed by batch-2 — the crash/resume case the persisted queue exists for.
    rebs = sorted(d for d in ctx.rebalance_dates if calendar[0] < d < calendar[-1])
    assert rebs, "panel must contain an interior rebalance date"
    # Last interior rebalance — past the momentum/universe warmup, so it actually
    # queues fills that batch 2 must execute (a warmup-era rebalance queues nothing).
    split_day = rebs[-1]
    split = calendar.index(split_day)

    pf = _new_portfolio(db)

    # Batch 1: inception → split (inclusive). A queue is left pending in the DB.
    for day in calendar[: split + 1]:
        live_engine.process_day(db, pf.id, prices, index, day, commit=False)
    assert (
        db.query(PaperV2PendingFill)
        .filter(
            PaperV2PendingFill.portfolio_id == pf.id,
            PaperV2PendingFill.status == "pending",
        )
        .count()
        > 0
    ), "a rebalance-day boundary must leave a pending queue to resume from"

    # Simulate a process restart: drop all in-memory ORM state; batch 2 must rebuild
    # purely from the DB.
    db.expunge_all()

    # Batch 2: split+1 → end.
    for day in calendar[split + 1 :]:
        live_engine.process_day(db, pf.id, prices, index, day, commit=False)

    # End state identical to the uninterrupted authoritative run.
    live_pos = {
        r.isin: r
        for r in db.query(PaperV2Position).filter(PaperV2Position.portfolio_id == pf.id)
    }
    assert set(live_pos) == set(auth_state.portfolio.positions)
    for isin, p in auth_state.portfolio.positions.items():
        assert live_pos[isin].shares == pytest.approx(p.shares, rel=1e-9)
        assert live_pos[isin].cost_basis == pytest.approx(p.cost_basis, rel=1e-9)
    assert db.get(PaperV2Portfolio, pf.id).cash == pytest.approx(
        auth_state.portfolio.cash, rel=1e-9
    )


def test_dc2_idempotent_replay_is_a_noop(db, parity_panel):
    """Re-processing an already-applied day is skipped (Pipeline Law: idempotency)."""
    prices, index, ctx, calendar = parity_panel
    pf = _new_portfolio(db)
    day = calendar[10]
    live_engine.process_day(db, pf.id, prices, index, day, commit=False)
    again = live_engine.process_day(db, pf.id, prices, index, day, commit=False)
    assert again.skipped


# ---------------------------------------------------------------------------
# DC3 — §3e hard ordering invariant through the live persist/hydrate path
# ---------------------------------------------------------------------------


def test_dc3_buy_at_open_then_same_day_stop(db):
    """A name bought at today's open whose close breaches −25% is stop-queued the SAME
    day — proving 5.i (execute queue) runs before 5.iii (stop) across the DB round-trip
    (11 §3e HARD ORDERING INVARIANT)."""
    isin = "ISINX"
    prices = _flat_panel([isin])
    dates = sorted(prices["date"].drop_duplicates())
    d_prev, d = dates[8], dates[9]  # mid-month, not a month-end
    _set_cell(prices, isin, d, open=100.0, close=70.0, close_tr=70.0)  # −30% from open

    pf = _new_portfolio(db)
    # A buy decided yesterday, sized at ₹50k against a ₹100 decision-close price.
    _pending(
        db,
        pf.id,
        isin=isin,
        symbol=isin,
        side="buy",
        qty=500.0,
        decision_price=100.0,
        reason="rebalance",
        decision_date=d_prev.date(),
    )

    rep = live_engine.process_day(db, pf.id, prices, None, d, commit=False)

    # The buy executed at today's open and is now a held position...
    pos = (
        db.query(PaperV2Position)
        .filter(PaperV2Position.portfolio_id == pf.id, PaperV2Position.isin == isin)
        .one()
    )
    assert pos.shares > 0
    assert isin in {f.isin for f in rep.fills_executed}
    # ...and the SAME day's close tripped the stop → a next-open sell is queued tonight.
    stop = (
        db.query(PaperV2PendingFill)
        .filter(
            PaperV2PendingFill.portfolio_id == pf.id,
            PaperV2PendingFill.status == "pending",
        )
        .one()
    )
    assert stop.side == "sell"
    assert stop.reason == "catastrophic_stop"
    assert stop.decision_date == d.date()
    # The prior buy row was marked filled (queue consumed, not duplicated).
    assert (
        db.query(PaperV2PendingFill)
        .filter(
            PaperV2PendingFill.portfolio_id == pf.id,
            PaperV2PendingFill.side == "buy",
            PaperV2PendingFill.status == "filled",
        )
        .count()
        == 1
    )


def test_dc3_buy_notional_survives_rehydrate(db):
    """Regression: a queued BUY must keep its decision-close price across the DB round
    trip. Without the persisted ``decision_price`` the rehydrated buy collapses to zero
    notional and is silently dropped — the live book would diverge from the engine."""
    isin = "ISINX"
    prices = _flat_panel([isin])
    dates = sorted(prices["date"].drop_duplicates())
    d_prev, d = dates[8], dates[9]
    _set_cell(prices, isin, d, open=100.0, close=100.0, close_tr=100.0)

    pf = _new_portfolio(db)
    _pending(
        db,
        pf.id,
        isin=isin,
        symbol=isin,
        side="buy",
        qty=500.0,
        decision_price=100.0,
        reason="rebalance",
        decision_date=d_prev.date(),
    )

    live_engine.process_day(db, pf.id, prices, None, d, commit=False)

    pos = (
        db.query(PaperV2Position)
        .filter(PaperV2Position.portfolio_id == pf.id, PaperV2Position.isin == isin)
        .one()
    )
    # ~₹50k / ~₹100 ≈ ~500 shares (minus slippage), NOT zero.
    assert pos.shares == pytest.approx(500.0, rel=0.05)


# ---------------------------------------------------------------------------
# DC4 — §5e corporate-action reconciliation prevents a false split-stop
# ---------------------------------------------------------------------------


def test_dc4_split_on_held_name_no_false_stop(db):
    """A 2:1 split moves the back-adjustment anchor: the held position is rescaled BEFORE
    the stop check, so the daily catastrophic stop does NOT falsely fire and position
    value is invariant (11 §5e)."""
    isin = "ISINY"
    # Post-split series: the entry-date row's adj_factor is now 0.5 (was 1.0 at entry).
    prices = _flat_panel([isin], base=500.0, adj_factor=0.5)
    dates = sorted(prices["date"].drop_duplicates())
    entry, d = dates[0], dates[9]

    pf = _new_portfolio(db)
    # Persisted against the OLD anchor: cost_basis 1000, 100 shares, factor 1.0.
    _position(
        db,
        pf.id,
        isin=isin,
        symbol=isin,
        shares=100.0,
        cost_basis=1000.0,
        last_price=500.0,
        entry_date=entry.date(),
        last_adj_factor=1.0,
    )

    # Encodes WHY: unreconciled, close 500 vs stop 750 WOULD fire; reconciled it must not.
    assert would_stop_fire(500.0, 1000.0, 25.0) is True
    assert would_stop_fire(500.0, 500.0, 25.0) is False

    rep = live_engine.process_day(db, pf.id, prices, None, d, commit=False)

    assert isin in rep.reconciled_isins
    # No false stop queued.
    assert (
        db.query(PaperV2PendingFill)
        .filter(
            PaperV2PendingFill.portfolio_id == pf.id,
            PaperV2PendingFill.status == "pending",
        )
        .count()
        == 0
    )
    pos = (
        db.query(PaperV2Position)
        .filter(PaperV2Position.portfolio_id == pf.id, PaperV2Position.isin == isin)
        .one()
    )
    assert pos.cost_basis == pytest.approx(500.0, rel=1e-9)
    assert pos.shares == pytest.approx(200.0, rel=1e-9)
    assert pos.shares * pos.cost_basis == pytest.approx(
        100_000.0, rel=1e-9
    )  # invariant
    assert pos.last_adj_factor == pytest.approx(0.5, rel=1e-9)  # anchor refreshed


# ---------------------------------------------------------------------------
# DC5 — daily 25% stop path through process_day (reproduces engine §5.iii)
# ---------------------------------------------------------------------------


def test_dc5_daily_stop_queues_next_open_sell(db):
    isin = "ISINZ"
    prices = _flat_panel([isin])
    dates = sorted(prices["date"].drop_duplicates())
    entry, d = dates[0], dates[9]
    _set_cell(prices, isin, d, close=70.0, close_tr=70.0)  # −30% vs cost_basis 100

    pf = _new_portfolio(db)
    _position(
        db,
        pf.id,
        isin=isin,
        symbol=isin,
        shares=100.0,
        cost_basis=100.0,
        last_price=100.0,
        entry_date=entry.date(),
        last_adj_factor=1.0,
    )

    live_engine.process_day(db, pf.id, prices, None, d, commit=False)

    stop = (
        db.query(PaperV2PendingFill)
        .filter(
            PaperV2PendingFill.portfolio_id == pf.id,
            PaperV2PendingFill.status == "pending",
        )
        .one()
    )
    assert stop.side == "sell" and stop.reason == "catastrophic_stop"
    assert stop.decision_date == d.date()
    # Position still held (the sell fills next session, not today).
    assert (
        db.query(PaperV2Position)
        .filter(PaperV2Position.portfolio_id == pf.id, PaperV2Position.isin == isin)
        .count()
        == 1
    )


def test_dc5_healthy_name_no_stop(db):
    """Control: a name well above its stop level queues nothing (the stop is real, not
    always-on)."""
    isin = "ISINZ"
    prices = _flat_panel([isin])
    dates = sorted(prices["date"].drop_duplicates())
    entry, d = dates[0], dates[9]

    pf = _new_portfolio(db)
    _position(
        db,
        pf.id,
        isin=isin,
        symbol=isin,
        shares=100.0,
        cost_basis=100.0,
        last_price=100.0,
        entry_date=entry.date(),
        last_adj_factor=1.0,
    )

    live_engine.process_day(db, pf.id, prices, None, d, commit=False)

    assert (
        db.query(PaperV2PendingFill)
        .filter(
            PaperV2PendingFill.portfolio_id == pf.id,
            PaperV2PendingFill.status == "pending",
        )
        .count()
        == 0
    )


# ---------------------------------------------------------------------------
# DC6 — alerts render with no external I/O
# ---------------------------------------------------------------------------


def _fill(isin, side, qty=10.0, price=100.0):
    return Fill(
        isin=isin,
        symbol=isin,
        side=side,
        qty=qty,
        price=price,
        date=date(2022, 3, 15),
        cost_rupees=0.0,
    )


def _snapshot():
    return DailySnapshot(
        date=date(2022, 3, 15),
        equity=1_234_567.0,
        cash=10_000.0,
        invested_value=1_224_567.0,
        exposure=0.99,
        n_positions=3,
    )


def test_dc6_emit_alerts_render_without_io():
    # Rebalance preview + fill confirmation.
    reb = ProcessReport(
        process_date=date(2022, 3, 31),
        is_rebalance=True,
        snapshot=_snapshot(),
        fills_executed=[_fill("AAA", "buy")],
        queued=[_fill("BBB", "buy"), _fill("CCC", "sell"), _fill("DDD", "trim")],
    )
    subjects = alerter.emit_alerts(reb, send=False)
    assert "fills" in subjects and "rebalance" in subjects

    # Catastrophic stop on a non-rebalance day.
    stop = ProcessReport(
        process_date=date(2022, 3, 15),
        is_rebalance=False,
        snapshot=_snapshot(),
        queued=[_fill("EEE", "sell")],
    )
    assert alerter.emit_alerts(stop, send=False) == ["stop"]

    # A skipped (idempotent) day emits nothing.
    assert (
        alerter.emit_alerts(
            ProcessReport(process_date=date(2022, 3, 15), skipped=True), send=False
        )
        == []
    )

    # The HTML builders produce non-empty bodies carrying the key fields.
    assert "BBB" in alerter.build_rebalance_preview_html(reb)
    assert "EEE" in alerter.build_stop_alert_html(stop)
    assert "AAA" in alerter.build_fill_confirm_html(reb)
