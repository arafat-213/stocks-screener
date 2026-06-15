"""
signals.py — indicator precompute (vectorized, once) + binary entry gate + ranker.

Two concerns kept strictly separate (02 §4 — do NOT merge into a score):
  - entry_gate: binary eligibility (close > EMA_200, momentum_12_1 > 0, adv_20 floor).
  - ranker: continuous score for ordering eligible names (vol-adjusted momentum).

All indicator math consumes `close` (split+bonus-adjusted, ex-dividend).
Never touches `close_tr` — that column is MTM/P&L territory (portfolio.py only).
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2.config import MomentumConfig
from app.core.strategy import TechnicalStrategy

# Column-case adapter required by TechnicalStrategy.calculate_indicators.
# v2 parquet uses lowercase; calculate_indicators expects title-case (02 verified contracts).
_RENAME_UP = {
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
}

_strategy = TechnicalStrategy()


def _momentum_12_1(
    close_vals: np.ndarray,
    skip: int,
    lookback: int,
) -> np.ndarray:
    """
    Calendar-aware 12-1 momentum using integer positions.

    mom[i] = close[i - skip] / close[i - lookback] - 1
    where lookback = momentum_lookback_days + skip (default: 252 + 21 = 273).

    Indexing is on integer positions in the per-ISIN sorted array — NOT on
    calendar dates — so trading gaps (suspensions, holidays) cannot cause
    incorrect lookbacks the way naive .shift(N) on a DatetimeIndex would.

    Returns np.nan for positions < lookback (insufficient history).
    """
    n = len(close_vals)
    result = np.full(n, np.nan)
    if n <= lookback:
        return result
    # Vectorized: for i in [lookback, n)
    #   numerator   = close[i - skip]    → slice [lookback-skip : n-skip]
    #   denominator = close[i - lookback] → slice [0 : n-lookback]
    num = close_vals[lookback - skip : n - skip]
    den = close_vals[: n - lookback]
    with np.errstate(divide="ignore", invalid="ignore"):
        result[lookback:] = np.where(den != 0.0, num / den - 1.0, np.nan)
    return result


class SignalStore:
    """
    Precomputed indicator cache for one backtest run.

    Built once by precompute_signals(); queried O(1) per (day, isin) by the
    engine loop.

    Internal layout: {isin → DataFrame} where each DataFrame has a
    DatetimeIndex (trading dates for that ISIN) and columns:
      close, adv_20, EMA_200, momentum_12_1, annualized_vol.
    """

    def __init__(
        self,
        data: dict[str, pd.DataFrame],
        cfg: MomentumConfig,
    ) -> None:
        self._data = data
        self._cfg = cfg
        # liquidity_floor_cr is in ₹ crore; convert once to ₹
        self._liq_floor_rupees: float = cfg.liquidity_floor_cr * 1e7

    # ------------------------------------------------------------------
    # Public query interface
    # ------------------------------------------------------------------

    def entry_gate(self, day: pd.Timestamp | date, isin: str) -> bool:
        """
        True iff the name is eligible to be held on `day`.

        All three conditions must hold simultaneously (02 §4):
          1. close > EMA_200          (long-term uptrend)
          2. momentum_12_1 > 0        (absolute momentum filter)
          3. adv_20 >= liquidity_floor (decision-date, no lookahead)

        Returns False for missing data, NaN in any field, or a day with no
        print (suspension).
        """
        row = self._get_row(day, isin)
        if row is None:
            return False
        close = row["close"]
        ema200 = row["EMA_200"]
        mom = row["momentum_12_1"]
        adv = row["adv_20"]
        # Any NaN → ineligible
        if any(math.isnan(v) for v in (close, ema200, mom, adv)):
            return False
        return bool(
            (close > ema200) and (mom > 0.0) and (adv >= self._liq_floor_rupees)
        )

    def ranker(self, day: pd.Timestamp | date, isin: str) -> float:
        """
        Volatility-adjusted momentum: momentum_12_1 / annualized_vol.

        Returns NaN if either component is missing or vol is zero.
        Higher score → better rank (sort descending).

        Interface is pluggable (02 §4): swapping the ranker is a one-line change
        in the engine — pass a different callable with the same (day, isin) → float
        signature.
        """
        row = self._get_row(day, isin)
        if row is None:
            return float("nan")
        mom = row["momentum_12_1"]
        vol = row["annualized_vol"]
        if math.isnan(mom) or math.isnan(vol) or vol == 0.0:
            return float("nan")
        return mom / vol

    def eligible_ranked(
        self,
        day: pd.Timestamp | date,
        isins: list[str],
    ) -> list[tuple[str, float]]:
        """
        Filter `isins` through entry_gate, then sort by ranker score descending.

        Returns [(isin, score), ...] — the engine uses this to build the
        top-N target membership and rebalance plan (T6).
        """
        scored = [
            (isin, self.ranker(day, isin))
            for isin in isins
            if self.entry_gate(day, isin)
        ]
        return sorted(scored, key=lambda x: x[1], reverse=True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_row(self, day: pd.Timestamp | date, isin: str) -> pd.Series | None:
        df = self._data.get(isin)
        if df is None:
            return None
        ts = pd.Timestamp(day)
        if ts not in df.index:
            return None
        return df.loc[ts]


# RankerFn type alias for pluggable ranker injection (see 02 §4).
RankerFn = type(SignalStore.ranker)  # callable (day, isin) -> float


def precompute_signals(
    prices: pd.DataFrame,
    cfg: MomentumConfig,
) -> SignalStore:
    """
    Precompute per-ISIN indicators for all dates in `prices` and return a
    SignalStore ready for O(1) per-(day, isin) queries.

    `prices` is the multi-ISIN long-format DataFrame from
    store.read_prices_adjusted.  Required columns:
      isin, date, open, high, low, close, volume, adv_20.

    Indicator math uses `close` (split+bonus-adjusted, ex-dividend) throughout.
    `close_tr` is not used here — it belongs exclusively to portfolio MTM.

    Computation is vectorized per ISIN:
      - EMA_200 via TechnicalStrategy.calculate_indicators (live/backtest parity)
      - momentum_12_1 via integer-position indexing (calendar-gap safe)
      - annualized_vol via rolling stdev of daily returns × √252
    """
    skip: int = cfg.momentum_skip_days  # 21
    lookback: int = cfg.momentum_lookback_days + skip  # 273
    min_vol_periods = max(cfg.vol_lookback_days // 2, 1)

    data: dict[str, pd.DataFrame] = {}

    for isin, group in prices.groupby("isin"):
        # Sort by date and extract only the columns needed for signals.
        # Deliberately excludes close_tr so no indicator can silently use it.
        df = (
            group.sort_values("date")
            .set_index("date")[["open", "high", "low", "close", "volume", "adv_20"]]
            .copy()
        )
        df.index = pd.to_datetime(df.index)

        # --- EMA_200 (title-case adapter required by calculate_indicators) ---
        df_ta = df.rename(columns=_RENAME_UP)
        df_ta = _strategy.calculate_indicators(df_ta)
        # pandas_ta appends no EMA_200 column when the series has < 200 rows
        # (short-lived/delisted names). Such names can never pass the entry gate
        # anyway (momentum_12_1 needs 273 rows → NaN), so fill EMA_200 with NaN
        # rather than crashing — ineligibility falls out of the NaN check.
        if "EMA_200" in df_ta.columns:
            df["EMA_200"] = df_ta["EMA_200"].values
        else:
            df["EMA_200"] = np.nan

        # --- 12-1 momentum (calendar-aware integer positions, no naive shifts) ---
        close_arr = df["close"].to_numpy(dtype=float)
        df["momentum_12_1"] = _momentum_12_1(close_arr, skip, lookback)

        # --- annualized volatility (daily pct_change stdev × √252) ---
        df["annualized_vol"] = (
            df["close"]
            .pct_change()
            .rolling(cfg.vol_lookback_days, min_periods=min_vol_periods)
            .std()
            .mul(math.sqrt(252))
        )

        data[str(isin)] = df

    return SignalStore(data, cfg)
