"""
V3Config — the config object for the v3 multi-factor, turnover-aware engine.

Field set is LOCKED to specs/v3/00_PREREGISTRATION.md §11.
This is a *separate* dataclass from MomentumConfig; v2 stays runnable and frozen.

Also exports the §6 coarse grids and decision predicates as module constants so
no later session moves the measuring stick.

Track-B additions (TBE0, 2026-06-19):
  - PRICE_FACTOR_NAMES / FUNDAMENTAL_FACTOR_NAMES / VALUE_BLOCK / QUALITY_BLOCK
  - TRACK_B_DISCOVERY window constant
  - TRACK_A_BASELINE — pinned T5 candidate for H3 comparison anchor
  - V3Config.__post_init__ validates active_factors against all known names
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
# Factor name sets — price-only (Track-A) and fundamental (Track-B)
# ---------------------------------------------------------------------------

# Track-A price factors (must match factors.py FACTOR_NAMES exactly)
PRICE_FACTOR_NAMES: frozenset[str] = frozenset(
    {"mom_12_1", "mom_6_1", "low_vol", "trend_quality", "reversal"}
)

# Track-B fundamental factor family blocks (03_TRACK_B_PREREG §3/§6)
VALUE_BLOCK: frozenset[str] = frozenset({"earnings_yield", "book_to_price"})
QUALITY_BLOCK: frozenset[str] = frozenset({"roe", "accruals", "leverage"})
FUNDAMENTAL_FACTOR_NAMES: frozenset[str] = VALUE_BLOCK | QUALITY_BLOCK

# All names accepted in V3Config.active_factors
ALL_FACTOR_NAMES: frozenset[str] = PRICE_FACTOR_NAMES | FUNDAMENTAL_FACTOR_NAMES

# ---------------------------------------------------------------------------
# Track-B-only window constant (03_TRACK_B_PREREG §10 rescope, pinned TB8)
# DO NOT edit validation.DISCOVERY or validation.FINAL_OOS — those are Track-A's
# canonical splits and are reused for FINAL_OOS unchanged.
# ---------------------------------------------------------------------------

TRACK_B_DISCOVERY = (date(2020, 1, 31), date(2023, 6, 30))

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
    # Names must be in ALL_FACTOR_NAMES (price factors: Track-A; fundamental: Track-B).
    # Floor = price-momentum only. TBE0 extends the validated name set to the 5
    # fundamental factors; it does NOT change the floor or equal-weight rule.
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

    # --- stable-universe redesign (08 §3/§4) ---------------------------------
    # Default 'floor' == the status-quo per-rebalance ₹5cr-liquidity universe, so
    # the C0 control path is byte-identical to every pre-08 run (no mask applied).
    # 'stable' activates the slow-reviewed, buffered ADV-ranked membership mask
    # (stable_universe.build_stable_universe_mask), AND-ed into entry_gate. The
    # ₹5cr floor (liquidity_floor_cr) is retained as a per-day tradeability safety
    # in BOTH modes (08 §2a). Changing these is a new prereg by 08 §11.
    universe_mode: Literal["floor", "stable"] = "floor"
    universe_size_U: int = 200  # top-U by trailing adv_20 (08 §4)
    universe_buffer_B: float = 1.25  # stay-in until rank > B*U (hysteresis band)
    universe_review_cadence: Literal["semi-annual"] = "semi-annual"
    universe_rank_lookback_td: int = 126  # ~6mo trailing median-adv_20 window

    # --- date range for a run ---
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    def __post_init__(self) -> None:
        unknown = set(self.active_factors) - ALL_FACTOR_NAMES
        if unknown:
            raise ValueError(
                f"V3Config.active_factors contains unknown names: {sorted(unknown)}. "
                f"Known: {sorted(ALL_FACTOR_NAMES)}"
            )
        if not self.active_factors:
            raise ValueError("V3Config.active_factors must contain at least one factor")
        if self.universe_mode not in ("floor", "stable"):
            raise ValueError(
                f"universe_mode must be 'floor' or 'stable'; got {self.universe_mode!r}"
            )
        if self.universe_mode == "stable":
            if self.universe_size_U <= 0:
                raise ValueError(
                    f"universe_size_U must be > 0; got {self.universe_size_U}"
                )
            if self.universe_buffer_B < 1.0:
                raise ValueError(
                    f"universe_buffer_B must be >= 1.0; got {self.universe_buffer_B}"
                )
            if self.universe_rank_lookback_td <= 0:
                raise ValueError(
                    f"universe_rank_lookback_td must be > 0; got {self.universe_rank_lookback_td}"
                )


# ---------------------------------------------------------------------------
# Track-A baseline — pinned from 01_TRACK_A_TASKS.md T4/T5 selection (2026-06-17)
# Used as the H3 comparison anchor in TBE3–TBE6.  Do NOT change these values.
#
# Recovered from the T5 session log:
#   active_factors = [mom_12_1, low_vol, trend_quality, mom_6_1, reversal]
#   cadence = monthly (T4 L1 reject — cadence coarsening collapsed Calmar)
#   sell_rank_buffer M = 70 (T4 L2 plateau-selected — cut turnover 935→800%)
#   rank_smoothing_months = 0 (T4 L3 reject — smoothing cut Calmar, no plateau)
#   target_positions N = 20 (locked V3Config default, unchanged)
#   DISCOVERY Calmar: 0.396 | realized turnover: 956% | ConfigLedger K=10
# ---------------------------------------------------------------------------

TRACK_A_BASELINE = V3Config(
    active_factors=["mom_12_1", "low_vol", "trend_quality", "mom_6_1", "reversal"],
    rebalance_cadence="monthly",
    sell_rank_buffer=70,
    rank_smoothing_months=0,
    target_positions=20,
)
