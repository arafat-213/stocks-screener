"""test_v3t07_2_force_exit.py — 07 T07.2 regression suite (offline, synthetic data).

Encodes WHY force-exit-at-termination matters (Rule 9), not just that it runs:

  - WHY: a held instrument that is merged-away / cancelled / delisted (07 §1) stops
    printing with no `instrument_id` successor. It has no forward price, so a queued
    sell is dropped (engine._stamp_fills) and the position is carried FOREVER as an
    MTM-frozen ghost — freezing capital and occupying a book slot (the T06.5 blocker).
  - THE FIX (07 §6, Approach A): after K trading days of price-silence, liquidate the
    position to cash at its last price. Behind a flag (`terminate_after_silent_days`,
    default 0 = OFF) so engine.run is byte-for-byte unchanged when disabled.

The terminated-name tests inject the holding and begin stepping AFTER its last print, so
the strategy only ever sees it as a no-open ghost (a queued rebalance sell would be
dropped) — the ONLY thing that can remove it is the force-exit. That isolates the
mechanism from ordinary rebalance churn, and keeps MTM from overwriting its last price.

Coverage:
  * the §1 ghost reproduced RED (feature OFF → carried) and GREEN (ON → exited clean);
  * the exit fires EXACTLY at the K-trading-day threshold (not before);
  * a stitched succession (instrument_id keeps printing) is never silent → never exits
    — proves the "no successor" gate is what distinguishes a termination from a re-issue;
  * `_silent_trading_days` counts true trading-day silence;
  * no-termination parity: a continuous panel runs byte-identical at K=0 vs K=15.

All offline: synthetic prices, no network, regime overlay off.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.engine import (
    LoopState,
    _force_exit_terminated,
    _silent_trading_days,
    build_context,
    run,
    step_day,
)
from app.backtest_v2.portfolio import Portfolio
from app.backtest_v2.schemas import Position

# A clearly-terminated holding loses ~3 trading weeks of prints; K below that → carried.
K = 15
DEAD_LAST_ORD = (
    59  # DEAD's last print is calendar ordinal 59 (see _panel_with_termination)
)
DEAD_LAST_PRICE = 105.9  # the price it is carried at, and must exit at (07 §6.2)


# ---------------------------------------------------------------------------
# Synthetic panel builders
# ---------------------------------------------------------------------------


def _rows(isin: str, dates: pd.DatetimeIndex, instrument_id: str | None = None) -> list:
    """Long-format rows for one ISIN over `dates` (all required engine columns)."""
    iid = instrument_id or isin
    out = []
    for i, d in enumerate(dates):
        p = 100.0 * (1.0 + i * 0.001)  # gentle uptrend; deterministic
        out.append(
            {
                "isin": isin,
                "symbol": isin,
                "instrument_id": iid,
                "date": d,
                "open": p,
                "high": p * 1.01,
                "low": p * 0.99,
                "close": p,
                "close_raw": p,
                "close_tr": p,
                "volume": 100_000,
                "traded_value": 1e9,
                "adv_20": 1e8,  # ₹10 crore — always liquid
                "adj_factor": 1.0,
                "tr_factor": 1.0,
                "series": "EQ",
            }
        )
    return out


def _panel_with_termination() -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """LIVE trades the whole calendar; DEAD terminates after a prefix (no successor)."""
    cal = pd.bdate_range("2022-01-03", periods=120)
    dead_dates = cal[: DEAD_LAST_ORD + 1]  # last print at ordinal DEAD_LAST_ORD
    rows = _rows("LIVE", cal) + _rows("DEAD", dead_dates)
    return pd.DataFrame(rows), list(cal)


def _cfg(**kw) -> MomentumConfig:
    base = dict(
        target_positions=2,
        sell_rank_buffer=4,
        liquidity_floor_cr=1.0,
        momentum_lookback_days=20,
        momentum_skip_days=1,
        vol_lookback_days=10,
        max_position_pct=60.0,
        starting_capital=1_000_000.0,
        use_regime_overlay=False,
        catastrophic_stop_pct=25.0,
        rebalance="monthly",
    )
    base.update(kw)
    return MomentumConfig(**base)


def _held_dead_state() -> LoopState:
    """A LoopState already holding DEAD, carried at its last-traded price."""
    pf = Portfolio(cash=500_000.0)
    pf.positions["DEAD"] = Position(
        isin="DEAD",
        symbol="DEAD",
        shares=1000.0,
        cost_basis=100.0,
        entry_date=date(2022, 1, 3),
        last_price=DEAD_LAST_PRICE,
    )
    return LoopState(
        portfolio=pf,
        pending_fills=[],
        rebalance_dates_used=[],
        per_rebalance_turnover=[],
    )


def _step_range(ctx, state, calendar, start_ord: int, end_ord: int) -> None:
    """Step the engine through calendar[start_ord : end_ord + 1] (inclusive)."""
    for day in calendar[start_ord : end_ord + 1]:
        step_day(ctx, state, day)


# ---------------------------------------------------------------------------
# RED — feature OFF: the terminated holding is carried as a frozen ghost
# ---------------------------------------------------------------------------


def test_termination_ghost_carried_when_feature_off():
    """K=0 (default): DEAD never trades again yet stays held forever (the §1 bug)."""
    prices, cal = _panel_with_termination()
    ctx, calendar = build_context(prices, _cfg(), terminate_after_silent_days=0)
    state = _held_dead_state()

    # Step the whole post-termination window — the strategy can only drop sells for it.
    _step_range(ctx, state, calendar, DEAD_LAST_ORD + 1, len(calendar) - 1)

    assert "DEAD" in state.portfolio.positions  # capital frozen, slot occupied
    assert state.portfolio.positions["DEAD"].shares == 1000.0
    assert not any(f.isin == "DEAD" for f in state.portfolio.fills_log)


# ---------------------------------------------------------------------------
# GREEN — feature ON: the terminated holding is liquidated to cash
# ---------------------------------------------------------------------------


def test_termination_force_exited_to_cash_when_on():
    """K=15: after 15 silent trading days DEAD is sold at its last price; slot freed."""
    prices, cal = _panel_with_termination()
    ctx, calendar = build_context(prices, _cfg(), terminate_after_silent_days=K)
    state = _held_dead_state()

    _step_range(ctx, state, calendar, DEAD_LAST_ORD + 1, len(calendar) - 1)

    assert "DEAD" not in state.portfolio.positions
    sells = [
        f for f in state.portfolio.fills_log if f.isin == "DEAD" and f.side == "sell"
    ]
    assert len(sells) == 1
    assert sells[0].qty == 1000.0
    assert (
        sells[0].price == DEAD_LAST_PRICE
    )  # flat last-traded price, no haircut (§6.2)
    # Liquidation credits cash (proceeds net of a thin statutory cost).
    assert state.portfolio.cash > 500_000.0 + 1000.0 * DEAD_LAST_PRICE * 0.99


def test_force_exit_fires_exactly_at_K_trading_days():
    """The exit triggers on the K-th silent day, not the (K-1)-th (boundary, Rule 9)."""
    prices, cal = _panel_with_termination()
    ctx, calendar = build_context(prices, _cfg(), terminate_after_silent_days=K)

    # Step to silent == K-1 (one short): still held.
    state = _held_dead_state()
    _step_range(ctx, state, calendar, DEAD_LAST_ORD + 1, DEAD_LAST_ORD + (K - 1))
    assert "DEAD" in state.portfolio.positions, (
        "exited too early (before K silent days)"
    )

    # One more day → silent == K → exited.
    step_day(ctx, state, calendar[DEAD_LAST_ORD + K])
    assert "DEAD" not in state.portfolio.positions, (
        "did not exit at the K-th silent day"
    )


# ---------------------------------------------------------------------------
# Helper-level: silence counting + the "no successor" gate
# ---------------------------------------------------------------------------


def test_silent_trading_days_counts_true_trading_days():
    """0 while trading; then increments by one per trading day of silence; None if unknown."""
    prices, cal = _panel_with_termination()
    ctx, calendar = build_context(prices, _cfg(), terminate_after_silent_days=K)

    assert (
        _silent_trading_days(ctx, "DEAD", calendar[DEAD_LAST_ORD]) == 0
    )  # printed today
    assert _silent_trading_days(ctx, "DEAD", calendar[DEAD_LAST_ORD + 1]) == 1
    assert _silent_trading_days(ctx, "DEAD", calendar[DEAD_LAST_ORD + K]) == K
    assert _silent_trading_days(ctx, "LIVE", calendar[-1]) == 0  # trades every day
    assert _silent_trading_days(ctx, "UNKNOWN", calendar[-1]) is None


def test_succession_is_never_silent_so_never_force_exited():
    """Old leg stops, but its `instrument_id` keeps printing via the new leg → silence 0.

    This is the line 06 draws around 07: a face-value re-issue (same instrument_id, the
    new ISIN prints the day the old one stops) is a continuation, not a termination, so
    it is never silent and force-exit never touches it.
    """
    cal = pd.bdate_range("2022-01-03", periods=120)
    old = _rows("ISIN_OLD", cal[:60], instrument_id="ISIN_OLD")
    new = _rows("ISIN_NEW", cal[60:], instrument_id="ISIN_OLD")  # same chain id
    prices = pd.DataFrame(old + new)
    ctx, calendar = build_context(prices, _cfg(), terminate_after_silent_days=K)

    # After collapse the chain is keyed by the root id and prints continuously.
    assert _silent_trading_days(ctx, "ISIN_OLD", calendar[-1]) == 0

    pf = Portfolio(cash=0.0)
    pf.positions["ISIN_OLD"] = Position(
        isin="ISIN_OLD",
        symbol="ISIN_OLD",
        shares=1000.0,
        cost_basis=100.0,
        entry_date=date(2022, 1, 3),
        last_price=110.0,
    )
    _force_exit_terminated(ctx, pf, calendar[-1], calendar[-1].date())
    assert "ISIN_OLD" in pf.positions  # continuation, never silent → untouched


# ---------------------------------------------------------------------------
# Parity — no terminations ⇒ K=0 and K=15 are byte-identical
# ---------------------------------------------------------------------------


def _continuous_panel(
    n_isin: int = 5, n_days: int = 320, seed: int = 7
) -> pd.DataFrame:
    """A panel where every name trades every day (no terminations possible)."""
    rng = np.random.default_rng(seed)
    cal = pd.bdate_range("2021-01-04", periods=n_days)
    rows = []
    for k in range(n_isin):
        isin = f"ISIN{k}"
        price = 100.0
        drift = 0.0003 + 0.0002 * k  # distinct trends → real rotation
        for i, d in enumerate(cal):
            price = max(price * (1 + rng.normal(drift, 0.012)), 0.01)
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "instrument_id": isin,
                    "date": d,
                    "open": price,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "close_raw": price,
                    "close_tr": price * 1.0005**i,
                    "volume": 100_000,
                    "traded_value": 1e9,
                    "adv_20": 1e8,
                    "adj_factor": 1.0,
                    "tr_factor": 1.0005**i,
                    "series": "EQ",
                }
            )
    return pd.DataFrame(rows)


def test_no_termination_parity_off_vs_on():
    """With nothing to terminate, the flag is a no-op: identical equity, fills, positions."""
    prices = _continuous_panel()
    cfg = _cfg(momentum_lookback_days=60, vol_lookback_days=30)

    off = run(prices, cfg, terminate_after_silent_days=0)
    on = run(prices, cfg, terminate_after_silent_days=K)

    assert [s.equity for s in off.snapshots] == [s.equity for s in on.snapshots]
    assert len(off.fills_log) == len(on.fills_log)
    for a, b in zip(off.fills_log, on.fills_log):
        assert (a.isin, a.side, a.qty, a.price, a.date) == (
            b.isin,
            b.side,
            b.qty,
            b.price,
            b.date,
        )
