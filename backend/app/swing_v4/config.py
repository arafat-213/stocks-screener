"""config.py — SwingConfig: the one config object for the v4 swing engine.

Every default is a value **frozen by `00_SWING_PREREG.md`** (citations inline).
This doc (v4/02) decides no strategy parameter; on any conflict `00` wins (§0).
The fields that are not yet locked at construction time — `n_max` — are the
returns-blind locks executed later (V4.0c) and default to ``None`` until then.

The grid knobs (`exit_type`, `atr_mult`, `n_max`, `regime_factors`) exist so the
`00` §5 grid can sweep them in V4.2; V4.0 only ever runs the frozen defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class SwingConfig:
    # --- universe / liquidity (00 §3.1) ---
    liquidity_floor_cr: float = 5.0  # adv_20 >= ₹5cr, decision-date

    # --- indicators (00 §3.2 — textbook-frozen) ---
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    sma_short: int = 20
    sma_mid: int = 50
    sma_long: int = 200
    ema_exit: int = 50  # EMA50 (Type 2 exit comparator)
    atr_period: int = 20  # Wilder ATR(20)

    # --- exit (00 §3.4 — candidate = Type 3; 1/2 are grid comparators) ---
    exit_type: int = 3  # knob: 1 (MACD cross-down) / 2 (close<EMA50) / 3 (ATR trail)
    atr_mult: float = 3.0  # §6.3 plateau neighborhood {2.5, 3.0, 3.5}
    catastrophic_stop_pct: float = 25.0  # close-breach circuit breaker beneath Type 3

    # --- sizing / regime throttle (00 §3.5) ---
    n_max: Optional[int] = (
        None  # returns-blind lock recorded in V4.0c — None until then
    )
    starting_capital: float = 1_000_000.0

    # --- regime score (00 §4) ---
    regime_factors: int = 5  # 5-factor frozen; 3 = reported ablation only (V4.2)
    regime_breadth_min: float = 60.0  # cond 3: liq_breadth_pct > 60
    regime_ad_min: float = 1.0  # cond 4: liq_ad_ratio > 1
    regime_vix_max: float = 20.0  # cond 5: india_vix < 20
    regime_dma_long: int = 200  # conds 1 & 2: Nifty 50 200-DMA
    regime_dma_short: int = 50  # cond 2: Nifty 50 50-DMA

    # --- run window ---
    date_from: Optional[date] = None
    date_to: Optional[date] = None
