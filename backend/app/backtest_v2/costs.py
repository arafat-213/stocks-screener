"""
PLACEHOLDER — real statutory+slippage cost model is spec 03
(03_COST_AND_BENCHMARK.md).

This module exists only to make the engine runnable and to satisfy
02 §10.2 (Σ per-fill costs == total cost paid).  Spec 03 swaps in the
real implementation as a one-line drop-in at the call sites.

Real cost breakdown (spec 03, for context only — do NOT implement here):
  STT 0.1% on sell leg + DP/charge flat + exchange/SEBI fees + slippage
  modelled as a function of order_value / adv_20.  Realistic round-trip
  on mid/smallcaps: 60–100 bps.

Placeholder contract:
  - Flat half-round-trip bps per fill leg (buy or sell).
  - adv_20 is accepted in the signature for interface parity but IGNORED
    (zero slippage assumption in this placeholder).
  - 30 bps round-trip default is a deliberate *low* placeholder.
    DO NOT tune it here — tuning lives in spec 04.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

SideLiteral = Literal["buy", "sell", "trim"]


@dataclass
class CostConfig:
    """Flat-bps placeholder.  Real model with statutory breakdown is spec 03."""

    round_trip_bps: float = 30.0  # 0.30% placeholder; realistic ≈ 60–100 bps (spec 03)


# Injectable cost-function type.  Every call site accepts a CostFn so spec 03
# is a one-line swap: pass the real function instead of fill_cost.
CostFn = Callable[[SideLiteral, float, float, float, CostConfig], float]


def fill_cost(
    side: SideLiteral,
    qty: float,
    price: float,
    adv_20: float,  # accepted for spec-03 parity; ignored here (zero slippage)
    cfg: CostConfig,
) -> float:
    """Return total ₹ transaction cost for one fill.

    Placeholder: (round_trip_bps / 2) applied to the fill notional.
    Both legs (buy and sell) incur the same flat cost; trim is treated as sell.
    """
    notional = qty * price
    half_bps = cfg.round_trip_bps / 2.0
    return notional * half_bps / 10_000.0
