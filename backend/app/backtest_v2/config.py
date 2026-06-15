"""
MomentumConfig — the one config object for the v2 engine.

Field set is LOCKED to spec 02 §7.  Do not add scoring weights, holding_days,
target_pct, RR, partial-exit, pullback, tier, or MTF fields — adding layers
made v1 worse (00_OVERVIEW §2.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class MomentumConfig:
    # universe / selection
    target_positions: int = 10  # N: buy when rank <= N
    sell_rank_buffer: int = 50  # M: sell when rank > M  (M > N)
    liquidity_floor_cr: float = 5.0  # adv_20 >= this (₹ crore), decision-date

    # ranking
    momentum_lookback_days: int = 252
    momentum_skip_days: int = 21  # the "1" in 12-1 momentum
    vol_lookback_days: int = 126

    # trend gate
    trend_ma: str = "EMA_200"  # or "SMA_200" — see 02 verified contracts

    # weighting / sizing
    max_position_pct: float = 20.0  # single-name cap (%)
    starting_capital: float = 1_000_000.0

    # risk overlay
    use_regime_overlay: bool = True
    catastrophic_stop_pct: float = 25.0  # wide circuit-breaker (% from cost basis)

    # rebalance cadence — the one structural knob we may sweep later
    rebalance: str = "monthly"

    # date range for a backtest run
    date_from: Optional[date] = None
    date_to: Optional[date] = None
