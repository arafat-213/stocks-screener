"""V4.1 cost-screen battery — `00` §5 Stage 1 + §6 selection-quality diagnostic.

These guard the *machinery* V4.1 depends on (the screen's numbers come from the real
DISCOVERY run, not pytest — `00` §5 forbids live data in tests). Each test states the
failure it guards (Rule 9). No live API, no return number asserted.
"""

from __future__ import annotations

import types
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2 import metrics
from app.backtest_v2.schemas import DailySnapshot, Fill
from app.swing_v4 import engine
from app.swing_v4.config import SwingConfig
from app.swing_v4.engine import SwingLoopState, _daily_turnover, _scan_entries
from app.swing_v4.v41_cost_screen import _diagnostic_read


# --------------------------------------------------------------------------- #
# A small multi-name frame that actually trades, so we can exercise the        #
# turnover wiring + compute_metrics end-to-end on a SwingEngineResult.         #
# --------------------------------------------------------------------------- #
def _trending_frame(isin: str, base: float, periods: int = 80) -> pd.DataFrame:
    idx = pd.bdate_range("2021-01-04", periods=periods)
    # A rise then a fall so both the entry (uptrend + MACD cross) and a Type-3/EMA exit
    # can fire within the window.
    up = np.linspace(base, base * 1.6, periods // 2)
    down = np.linspace(base * 1.6, base * 1.1, periods - periods // 2)
    close = np.concatenate([up, down])
    return pd.DataFrame(
        {
            "isin": [isin] * periods,
            "symbol": [isin[-4:]] * periods,
            "date": idx,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "adv_20": [1e8] * periods,
        }
    )


def _multi_name_frame(n: int = 4, periods: int = 80) -> pd.DataFrame:
    return pd.concat(
        [_trending_frame(f"INE000A0100{i}", 100.0 + 10 * i, periods) for i in range(n)],
        ignore_index=True,
    )


# --------------------------------------------------------------------------- #
# per_rebalance_turnover wiring (the V4.1 integration that didn't exist before  #
# this stage). Guards: _daily_turnover mis-aggregating, and compute_metrics     #
# blowing up on a SwingEngineResult (AttributeError on per_rebalance_turnover). #
# --------------------------------------------------------------------------- #
def _snap(d: date, equity: float) -> DailySnapshot:
    return DailySnapshot(
        date=d,
        equity=equity,
        cash=0.0,
        invested_value=equity,
        exposure=1.0,
        n_positions=1,
    )


def _fill(d: date, side: str, qty: float, price: float) -> Fill:
    return Fill(
        isin="X", symbol="X", side=side, qty=qty, price=price, date=d, cost_rupees=0.0
    )


def test_daily_turnover_aggregates_buys_and_sells_over_equity():
    snaps = [_snap(date(2021, 1, 4), 1000.0), _snap(date(2021, 1, 5), 1200.0)]
    fills = [
        _fill(date(2021, 1, 4), "buy", 5, 100.0),  # 500 notional / 1000 = 0.5
        _fill(date(2021, 1, 5), "buy", 2, 100.0),  # (200 + 100) / 1200 = 0.25
        _fill(date(2021, 1, 5), "sell", 1, 100.0),
    ]
    out = dict(_daily_turnover(fills, snaps))
    assert out[date(2021, 1, 4)] == 0.5
    assert abs(out[date(2021, 1, 5)] - 0.25) < 1e-9


def test_swing_result_feeds_compute_metrics():
    """compute_metrics (built for v2 EngineResult) must work on a SwingEngineResult —
    the integration V4.1 relies on (it reads .per_rebalance_turnover / .fills_log)."""
    snaps = [
        _snap(date(2021, 1, 4), 1000.0),
        _snap(date(2021, 1, 5), 1100.0),
        _snap(date(2021, 1, 6), 1050.0),
    ]
    fills = [
        _fill(date(2021, 1, 4), "buy", 5, 100.0),
        _fill(date(2021, 1, 6), "sell", 5, 110.0),
    ]
    res = engine.SwingEngineResult(
        snapshots=snaps,
        fills_log=fills,
        config=SwingConfig(),
        total_cost_paid=0.0,
        per_rebalance_turnover=_daily_turnover(fills, snaps),
    )
    m = metrics.compute_metrics(res)  # must not raise
    assert m.annualized_turnover > 0.0
    assert np.isfinite(m.max_drawdown)
    assert m.n_fills == 2


def test_turnover_empty_on_no_fill_run():
    """No fills ⇒ empty turnover series, not a crash."""
    assert _daily_turnover([], [_snap(date(2021, 1, 4), 1000.0)]) == []


# --------------------------------------------------------------------------- #
# The B_random selector (00 §6). Guards: the random branch not actually        #
# randomizing (would make B_random == B_liquid, voiding the diagnostic), and   #
# non-reproducibility across seeds (a seed must pin the draw).                 #
# --------------------------------------------------------------------------- #
class _FakeStore:
    """Minimal SwingSignalStore stand-in: every name fires entry every day."""

    def __init__(self, advs: dict[str, float]):
        self._advs = advs

    def entry_signal(self, day, iid) -> bool:
        return True

    def row(self, day, iid):
        return {
            "adv_20": self._advs[iid],
            "atr20": 1.0,
            "ema_exit": 1.0,
            "exit_macd_cross_down": False,
        }


def _oversubscribed_ctx(selector: str, seed: int = 0):
    """A context with 5 liquid candidates but target_positions=2 (oversubscribed)."""
    names = [f"INE{i}" for i in range(5)]
    advs = {n: float(10 + i) for i, n in enumerate(names)}  # distinct adv_20
    day = pd.Timestamp("2021-06-01")
    cfg = SwingConfig(
        target_positions=2, universe_mode="floor", selector=selector, selector_seed=seed
    )
    ctx = types.SimpleNamespace(
        config=cfg,
        signal_store=_FakeStore(advs),
        membership={n: {day} for n in names},
        universe_mask=None,
        sym_map={n: n for n in names},
    )
    return ctx, day, {n: advs[n] for n in names}


def _picks(selector: str, seed: int = 0) -> set[str]:
    ctx, day, closes = _oversubscribed_ctx(selector, seed)
    from app.backtest_v2.portfolio import Portfolio

    state = SwingLoopState(portfolio=Portfolio(cash=1_000_000.0), pending_fills=[])
    _scan_entries(ctx, state, day, day.date(), 1.0, closes)
    return {f.isin for f in state.pending_fills if f.side == "buy"}


def test_adv_selector_keeps_top_liquidity():
    """adv selector (the candidate) keeps the two HIGHEST adv_20 names."""
    assert _picks("adv") == {"INE4", "INE3"}, "top-2 by adv_20 (00 §14 C)"


def test_random_selector_varies_and_is_seed_reproducible():
    same_seed = [_picks("random", 7) for _ in range(3)]
    assert all(p == same_seed[0] for p in same_seed), "same seed ⇒ same pick"
    # Across seeds the pick must not be permanently the adv top-2 (else not random).
    seed_picks = {frozenset(_picks("random", s)) for s in range(12)}
    assert len(seed_picks) > 1, "random selector must vary the book across seeds"
    assert frozenset({"INE4", "INE3"}) != next(iter(seed_picks)) or len(seed_picks) > 1


# --------------------------------------------------------------------------- #
# Pre-committed §6 read (00 §6). Guards: the read drifting from the locked      #
# favorable/neutral/edge-discarding boundaries (esp. the BOTH-conditions       #
# requirement for edge-discarding).                                            #
# --------------------------------------------------------------------------- #
def test_diagnostic_read_favorable():
    assert _diagnostic_read(0.60, 0.50, 0.40) == "favorable"


def test_diagnostic_read_neutral_within_tolerance():
    # 0.45 / 0.50 = 0.90 ≥ 0.85 ⇒ neutral (creaming costs ~nothing).
    assert _diagnostic_read(0.45, 0.50, 0.40) == "neutral"


def test_diagnostic_read_edge_discarding_requires_both():
    # Below 85% of random median AND below B_all ⇒ edge-discarding.
    assert _diagnostic_read(0.30, 0.50, 0.55) == "edge-discarding"
    # Below 85% of random median but NOT below B_all ⇒ NOT edge-discarding (neutral).
    assert _diagnostic_read(0.30, 0.50, 0.20) == "neutral"
