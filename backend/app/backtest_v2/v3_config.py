"""
V3Config — the config object for the v3 multi-factor, turnover-aware engine.

Field set is LOCKED to specs/v3/00_PREREGISTRATION.md §11.
This is a *separate* dataclass from MomentumConfig; v2 stays runnable and frozen.

Also exports the §6 coarse grids and decision predicates as module constants so
no later session moves the measuring stick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# Re-export frozen splits from validation.py — do NOT redefine them here
# ---------------------------------------------------------------------------
from app.backtest_v2.validation import DISCOVERY, FINAL_OOS  # noqa: F401

# ---------------------------------------------------------------------------
# §6 coarse grids — frozen at T0 per prereg §6 / §11
# ---------------------------------------------------------------------------

# Layer 1 — reconstitution cadence
CADENCE_GRID: list[str] = ["monthly", "quarterly", "semi-annual"]

# Layer 2 — sell buffer M  (N=20 fixed throughout v3)
BUFFER_M_GRID: list[int] = [35, 50, 70]

# Layer 3 — rank smoothing (months; 0 = no smoothing)
SMOOTHING_GRID: list[int] = [0, 2, 3]

# Layers 4–7 — factor addition (one layer each; binary add/keep)
FACTOR_LAYERS: list[str] = ["low_vol", "trend_quality", "mom_6_1", "reversal"]

# ---------------------------------------------------------------------------
# Decision predicates (prereg §9) — frozen as callables, not strings
# ---------------------------------------------------------------------------


def passes_calmar_vs_benchmark(calmar_strat: float, calmar_bench: float) -> bool:
    """H1/H2 gate: strategy Calmar strictly beats benchmark Calmar."""
    return calmar_strat > calmar_bench


def passes_max_dd_vs_benchmark(max_dd_strat: float, max_dd_bench: float) -> bool:
    """Strategy max DD ≤ 70 % of benchmark max DD (both positive magnitudes)."""
    return max_dd_strat <= 0.70 * max_dd_bench


def passes_top10_retention(retention_frac: float) -> bool:
    """§6.2: at least 70 % of top-10 names survive a 10-name drop."""
    return retention_frac >= 0.70


def passes_concentration_hard(period_calmars: list[float]) -> bool:
    """§6.4 hardened: no single positive subperiod > 5× the mean of other positive periods."""
    positives = [c for c in period_calmars if c > 0]
    if len(positives) < 2:
        return True  # can't test with fewer than 2 positive periods
    for i, c in enumerate(positives):
        others = [x for j, x in enumerate(positives) if j != i]
        if c > 5.0 * (sum(others) / len(others)):
            return False
    return True


# ---------------------------------------------------------------------------
# V3Config dataclass
# ---------------------------------------------------------------------------


@dataclass
class V3Config:
    """
    Config for the v3 multi-factor, turnover-aware momentum strategy.

    v3 floor defaults (momentum-12-1 only, monthly, M=35) are designed to
    reproduce v2's candidate ranker so parity with v2 can be confirmed first.
    """

    # --- universe / selection (same as v2 floor) ---
    target_positions: int = 20  # N: buy when composite rank <= N
    sell_rank_buffer: int = 35  # M: sell when composite rank > M  (M > N)
    liquidity_floor_cr: float = 5.0  # adv_20 >= this (₹ crore), decision-date

    # --- active factor set ---
    # Each name must be in {"mom_12_1", "mom_6_1", "low_vol", "trend_quality", "reversal"}
    active_factors: list[str] = field(
        default_factory=lambda: ["mom_12_1"]  # floor = momentum-only
    )

    # --- composite weighting: equal-weight (prereg §5, §11 item 3) ---
    # Changing weights requires a separate pre-registration. Do not touch.
    factor_weights: Optional[dict[str, float]] = None  # None → equal-weight

    # --- turnover levers (T4 layers 1-3) ---
    rebalance_cadence: Literal["monthly", "quarterly", "semi-annual"] = "monthly"
    rank_smoothing_months: int = 0  # 0 = no smoothing; else N-month avg rank

    # --- momentum lookback (v2-compatible defaults) ---
    momentum_lookback_days: int = 252  # 12-1: 12-month window
    momentum_skip_days: int = 21  # skip last 1 month
    mom6_lookback_days: int = 126  # 6-1: 6-month window
    mom6_skip_days: int = 21

    # --- low-vol factor ---
    vol_lookback_days: int = 126  # annualised std dev window

    # --- trend-quality factor ---
    trend_quality_lookback_days: int = 126

    # --- reversal factor ---
    reversal_lookback_days: int = 21  # ~1 month

    # --- trend / entry gate (unchanged from v2) ---
    trend_ma: str = "EMA_200"

    # --- weighting / sizing (unchanged from v2) ---
    max_position_pct: float = 10.0
    starting_capital: float = 1_000_000.0

    # --- risk overlay (retained as-is, prereg §3.3) ---
    use_regime_overlay: bool = True
    catastrophic_stop_pct: float = 25.0

    # --- date range for a run ---
    date_from: Optional[date] = None
    date_to: Optional[date] = None
