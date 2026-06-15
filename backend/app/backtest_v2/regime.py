"""
regime.py — market-level risk-on/off overlay → deployable_fraction(day).

The index price series is INJECTED — not fetched here. The real benchmark
loader (spec 03 benchmark.py §2.3) wires the actual index series at runtime.
This module only consumes a pandas.Series of daily closes.

Design (02 §8 — keep it dumb):
  - Risk-on (1.0)  when index close > rolling 200-period SMA.
  - Risk-off (→ risk_off_floor) when below, after debounce_days confirmation.
  - Debounce: N consecutive days on the new side of the DMA required before
    the state flips.  Prevents single-day whipsaw at the line.
  - Pre-DMA warmup (first dma_period-1 days): treated as risk-on (no data to
    de-risk on; conservative — avoids zeroing the portfolio at startup).
  - No multi-state hysteresis, breadth, RSI, or ADX overrides (00 §2.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass
class RegimeConfig:
    """Configuration for the market-level regime overlay."""

    risk_off_floor: float = 1.0  # deployable fraction in risk-off (0.0 = full cash)
    debounce_days: int = 3  # consecutive days required to confirm a regime change
    dma_period: int = 200  # rolling SMA window for the market-regime signal


class RegimeOverlay:
    """
    Precomputes deployable_fraction for every date in the injected index series.

    Usage::

        overlay = RegimeOverlay(index_prices=benchmark_close_series)
        frac = overlay.deployable_fraction(date(2024, 3, 29))  # 1.0 or floor

    No-lookahead guarantee: fraction for day D uses only index data ≤ D.
    Spec 03 wires the real benchmark series; this module is purely functional.
    """

    def __init__(
        self,
        index_prices: pd.Series,
        cfg: RegimeConfig | None = None,
    ) -> None:
        """
        Args:
            index_prices: DatetimeIndex → daily close of the market index.
                          UTC-naive dates, sorted ascending.
            cfg: RegimeConfig — defaults to RegimeConfig() if None.
        """
        if cfg is None:
            cfg = RegimeConfig()
        self._cfg = cfg
        self._fractions: pd.Series = _precompute_fractions(
            index_prices.sort_index(), cfg
        )

    def deployable_fraction(self, day: date | pd.Timestamp) -> float:
        """
        Return the deployable fraction for `day`.

        Returns 1.0 (risk-on) or cfg.risk_off_floor (risk-off).
        Dates not in the injected series fall back to 1.0 (conservative default
        — avoids accidentally zeroing the portfolio on calendar mismatches).
        """
        ts = pd.Timestamp(day)
        if ts not in self._fractions.index:
            return 1.0
        return float(self._fractions[ts])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _precompute_fractions(prices: pd.Series, cfg: RegimeConfig) -> pd.Series:
    """
    Vectorised precompute + forward state-machine walk.

    Returns a float Series (1.0 or cfg.risk_off_floor) with the same index as
    `prices`.  All rolling windows look backward only — no lookahead.
    """
    dma = prices.rolling(cfg.dma_period, min_periods=cfg.dma_period).mean()

    # During DMA warmup (dma is NaN) treat as "above" so the state machine
    # cannot trigger risk-off before we have enough data to compute the DMA.
    above: pd.Series = (prices > dma).where(dma.notna(), other=True)

    d = cfg.debounce_days
    # all_above[t] = True iff the last d days were ALL above the DMA.
    # all_below[t] = True iff the last d days were ALL below the DMA.
    # NaN rows (insufficient window) → False via fillna(0) → no spurious flip.
    all_above = above.rolling(d, min_periods=d).min().fillna(0).astype(bool)
    all_below = (~above).rolling(d, min_periods=d).min().fillna(0).astype(bool)

    risk_off = cfg.risk_off_floor
    fractions = pd.Series(dtype=float, index=prices.index)
    current = 1.0  # initial state: risk-on

    for i in range(len(prices)):
        if current == 1.0 and all_below.iloc[i]:
            current = risk_off
        elif current == risk_off and all_above.iloc[i]:
            current = 1.0
        fractions.iloc[i] = current

    return fractions
