"""V4.0c returns-blind N_max footprint tests (v4/02 §4).

The footprint is the only V4.0 mechanism that emits a number, and the number is a
**count, never a return** (00 §3.5 / v4/02 §4 — it adds 0 to K). These tests prove the
concurrent-holdings state machine is faithful to the engine's entry→fill / Type-3
close-breach→exit timing AND that the result carries no return/PnL field (the
pre-registration guard: a returns-blind measurement must be structurally returns-blind).

No live API: every series is a hand-built fixture, with SMALL indicator windows so a
tiny series exercises the full rule set (the indicator math is parity-tested in V4.0a).
"""

from __future__ import annotations

from dataclasses import fields

import numpy as np
import pandas as pd

from app.swing_v4.config import SwingConfig
from app.swing_v4.footprint import FootprintResult, measure_footprint
from app.swing_v4.signals import precompute_swing_signals

# Fixture dates sit inside DISCOVERY (2018-02-06 → 2023-06-30) so the default window
# applies without special-casing.
_START = "2021-01-04"


def _small_cfg(**kw) -> SwingConfig:
    base = dict(
        sma_short=2,
        sma_mid=3,
        sma_long=5,
        ema_exit=4,
        atr_period=3,
        macd_fast=2,
        macd_slow=3,
        macd_signal=2,
        atr_mult=3.0,
    )
    base.update(kw)
    return SwingConfig(**base)


def _uptrend_dip(periods: int = 45) -> np.ndarray:
    """Gentle uptrend with one shallow dip → EXACTLY one daily-MACD bullish crossover
    that also clears the 3 trend conditions (reused from the V4.0b battery)."""
    base = np.linspace(100.0, 100.0 + periods, periods)
    dip = np.zeros(periods)
    dip[24:30] = [-3, -6, -7, -5, -2, 0]
    return base + dip


def _entry_then_crash() -> np.ndarray:
    """One entry (via the dip crossover), the anchor ratchets up over the continued
    uptrend, then a sharp multi-day crash that breaches the Type-3 trail."""
    up = _uptrend_dip(45)
    crash = np.linspace(up[-1], up[-1] - 60.0, 15)  # ~4/day drop ≫ 3×ATR
    return np.concatenate([up, crash])


def _frame(close: np.ndarray, isin: str) -> pd.DataFrame:
    idx = pd.bdate_range(_START, periods=len(close))
    return pd.DataFrame(
        {
            "isin": [isin] * len(close),
            "symbol": [isin[-3:]] * len(close),
            "date": idx,
            "open": close * 1.0,
            "high": close * 1.005,
            "low": close * 0.99,
            "close": close.astype(float),
            "adv_20": [1e8] * len(close),
        }
    )


# --------------------------------------------------------------------------- #
# §4 — concurrency rises on entry-fill, falls on Type-3 close-breach exit.     #
# Guards: a footprint that never exits (would inflate the cap to "held forever")#
#         or one off-by-one on the entry-fill / exit-fill day boundary.        #
# --------------------------------------------------------------------------- #
def test_single_name_holds_then_exits_on_type3_breach():
    cfg = _small_cfg()
    df = _frame(_entry_then_crash(), "INE000A01001")

    store = precompute_swing_signals(df, cfg)
    entry_days = [d for d in df["date"] if store.entry_signal(d, "INE000A01001")]
    assert len(entry_days) == 1, f"fixture must have one entry, got {entry_days}"

    res = measure_footprint(df, cfg, signal_store=store)

    assert res.max_concurrent == 1, "a single name can never be held twice over"
    assert res.n_instruments == 1
    # The crash forces a Type-3 exit ⇒ the book is empty by the last day (not held forever).
    assert res.concurrent.iloc[-1] == 0, "Type-3 breach must close the position"
    # Concurrency is 0 → 1 → 0: it rises only after the entry fills, and returns to 0.
    assert res.concurrent.max() == 1
    assert res.concurrent.min() == 0
    held_days = int(res.concurrent.sum())
    assert 1 <= held_days < len(res.concurrent), "held for part, not all, of the window"


# --------------------------------------------------------------------------- #
# §4 — two simultaneously-held names give concurrency 2 (the crowding count).  #
# Guards: per-name state leaking across instruments / failing to aggregate.    #
# --------------------------------------------------------------------------- #
def test_two_overlapping_names_reach_concurrency_two():
    cfg = _small_cfg()
    # Same uptrend (no crash) for two distinct ISINs → both enter the same day and stay
    # held through the tail (monotonic rise ⇒ anchor==close ⇒ Type-3 never breaches).
    close = _uptrend_dip(45)
    df = pd.concat(
        [_frame(close, "INE000A01001"), _frame(close, "INE000A01002")],
        ignore_index=True,
    )

    res = measure_footprint(df, cfg)

    assert res.n_instruments == 2
    assert res.max_concurrent == 2, "both names held at once → concurrency 2"
    # p99 ≤ max and the lock is an integer ≈ p99 (00 §3.5).
    assert res.p99 <= res.max_concurrent
    assert res.n_max_locked == int(round(res.p99))
    assert isinstance(res.n_max_locked, int)


# --------------------------------------------------------------------------- #
# Pre-registration guard: the result is STRUCTURALLY returns-blind.            #
# Guards: a future edit slipping a PnL/Calmar/return field into the footprint  #
#         (which would make the "adds 0 to K" claim false, 00 §3.5).           #
# --------------------------------------------------------------------------- #
def test_footprint_result_carries_no_return_field():
    field_names = {f.name for f in fields(FootprintResult)}
    forbidden = {
        "pnl",
        "return",
        "returns",
        "calmar",
        "sharpe",
        "nav",
        "equity",
        "cost",
        "turnover",
    }
    leaked = {f for f in field_names if any(bad in f.lower() for bad in forbidden)}
    assert not leaked, f"footprint must emit no return/PnL field, found: {leaked}"


# --------------------------------------------------------------------------- #
# Percentiles are taken over EVERY window trading day (incl. zero-hold days).  #
# Guards: percentiles computed only over busy days → an over-stated cap.       #
# --------------------------------------------------------------------------- #
def test_percentiles_span_all_window_days_including_empty():
    cfg = _small_cfg()
    df = _frame(_entry_then_crash(), "INE000A01001")
    res = measure_footprint(df, cfg)

    # The window series must include the pre-entry zero-holding days, so its length
    # equals the number of fixture trading days and its min is 0.
    assert len(res.concurrent) == len(df)
    assert res.concurrent.min() == 0
    assert res.p95 <= res.max_concurrent
