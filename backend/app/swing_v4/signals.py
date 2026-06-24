"""signals.py — SwingSignalStore: precompute per-instrument swing primitives once.

Mirrors the v2 `SignalStore` shape (precompute once, O(1) per-(day, id) query) so
the engine loop stays cheap. Identity is resolved to the chain-constant
`instrument_id` (06 T06.3) before grouping, so each per-instrument indicator
series is the gap-free concatenation of both legs of a succession.

All indicator math consumes the **adjusted** O/H/L/C only (never `close_raw`).
This module computes the *stateless* primitives:
  - the 4 frozen entry conditions (00 §3.3) → a single ``entry`` flag,
  - the exit comparators that need no carried state: Type 1 (MACD cross-down),
    Type 2 (close < EMA50),
  - the raw series the stateful Type-3 ATR trail needs from the engine
    (``close``, ``atr20``), plus ``adv_20`` for the liquidity gate and tiebreak.

The Type-3 trail anchor (max adjusted close since entry) is *position state* and
lives in the engine (v4/02 §1) — not here.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

from app.backtest_v2.identity import collapse_to_instrument_id
from app.swing_v4 import indicators as ind
from app.swing_v4.config import SwingConfig


class SwingSignalStore:
    """Precomputed per-instrument swing primitives for one run.

    Internal layout: ``{instrument_id → DataFrame}`` indexed by trading date with
    columns: ``open, high, low, close, adv_20, sma_short, sma_mid, sma_long,
    ema_exit, atr20, macd, macd_signal, w_macd, entry, exit_macd_cross_down``.
    """

    def __init__(self, data: dict[str, pd.DataFrame], cfg: SwingConfig) -> None:
        self._data = data
        self._cfg = cfg
        self._liq_floor_rupees: float = cfg.liquidity_floor_cr * 1e7

    # ------------------------------------------------------------------ #
    # Query interface                                                     #
    # ------------------------------------------------------------------ #
    def row(self, day: date | pd.Timestamp, instrument_id: str) -> pd.Series | None:
        """The precomputed row for (day, instrument_id), or None if absent."""
        df = self._data.get(instrument_id)
        if df is None:
            return None
        ts = pd.Timestamp(day)
        if ts not in df.index:
            return None
        return df.loc[ts]

    def entry_signal(self, day: date | pd.Timestamp, instrument_id: str) -> bool:
        """True iff all 4 frozen entry conditions hold on D **and** the name is
        liquid (``adv_20 ≥ ₹5cr``) and traded D. NaN in any field → False."""
        row = self.row(day, instrument_id)
        if row is None:
            return False
        adv = row["adv_20"]
        if math.isnan(adv) or adv < self._liq_floor_rupees:
            return False
        entry = row["entry"]
        # `entry` is stored as float (1.0/0.0/NaN) so a NaN window reads as False.
        return bool(entry == 1.0)

    def liquid(self, day: date | pd.Timestamp, instrument_id: str) -> bool:
        """True iff the name traded D with ``adv_20 ≥ ₹5cr`` (the §3.5 tiebreak gate)."""
        row = self.row(day, instrument_id)
        if row is None:
            return False
        adv = row["adv_20"]
        return not math.isnan(adv) and adv >= self._liq_floor_rupees


def precompute_swing_signals(
    prices: pd.DataFrame,
    cfg: SwingConfig | None = None,
) -> SwingSignalStore:
    """Precompute per-instrument swing primitives and return a SwingSignalStore.

    `prices` is the multi-instrument long frame from ``read_prices_adjusted``
    (columns: ``isin, date, open, high, low, close, volume, adv_20`` and, post-06,
    ``instrument_id``). Indicator math uses ``close`` (adjusted) throughout.
    """
    cfg = cfg or SwingConfig()
    # Resolve identity to the chain-constant instrument_id (06 T06.3); no-op for
    # frames with no succession.
    prices = collapse_to_instrument_id(prices)

    data: dict[str, pd.DataFrame] = {}
    for iid, group in prices.groupby("isin"):
        df = (
            group.sort_values("date")
            .set_index("date")[["open", "high", "low", "close", "adv_20"]]
            .copy()
        )
        df.index = pd.to_datetime(df.index)
        close = df["close"]

        df["sma_short"] = ind.sma(close, cfg.sma_short)
        df["sma_mid"] = ind.sma(close, cfg.sma_mid)
        df["sma_long"] = ind.sma(close, cfg.sma_long)
        df["ema_exit"] = ind.ema(close, cfg.ema_exit)
        df["atr20"] = ind.atr_wilder(df["high"], df["low"], close, cfg.atr_period)

        macd_line, signal_line = ind.macd(
            close, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal
        )
        df["macd"] = macd_line
        df["macd_signal"] = signal_line
        df["w_macd"] = ind.weekly_macd_line(
            close, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal
        )

        # --- entry conditions (00 §3.3 — all four true on D close) ---
        cross_up = (macd_line > signal_line) & (
            macd_line.shift(1) <= signal_line.shift(1)
        )
        cond1 = df["w_macd"] > 0.0  # weekly MACD line > 0 (last completed week)
        cond2 = close > df["sma_long"]  # close > SMA200
        cond3 = df["sma_short"] > df["sma_mid"]  # SMA20 > SMA50
        cond4 = cross_up  # daily MACD bullish crossover on D
        entry = cond1 & cond2 & cond3 & cond4
        # Store as float so a NaN-window row (insufficient history) is not True.
        df["entry"] = entry.astype(float).where(
            df[["w_macd", "sma_long", "sma_mid", "macd"]].notna().all(axis=1)
        )

        # --- stateless exit comparator: Type 1 (opposite daily MACD crossover) ---
        df["exit_macd_cross_down"] = (macd_line < signal_line) & (
            macd_line.shift(1) >= signal_line.shift(1)
        )

        data[str(iid)] = df

    return SwingSignalStore(data, cfg)
