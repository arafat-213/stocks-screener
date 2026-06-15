"""
Core dataclasses for v2 simulation.  All frozen where the object is logically
a value; mutable where the engine updates state over time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class Position:
    isin: str
    symbol: str
    shares: float
    cost_basis: float  # average cost per share (inclusive of fees) at entry
    entry_date: date
    last_price: float  # updated each MTM pass; close_tr of last known print


@dataclass(frozen=True)
class Fill:
    isin: str
    symbol: str
    side: Literal["buy", "sell", "trim"]
    qty: float  # shares (positive)
    price: float  # execution price (next-open after decision)
    date: date
    cost_rupees: float  # total ₹ transaction cost (fees + slippage) for this fill


@dataclass(frozen=True)
class RebalancePlan:
    sells: list[Fill] = field(default_factory=list)
    buys: list[Fill] = field(default_factory=list)
    trims: list[Fill] = field(default_factory=list)


@dataclass(frozen=True)
class DailySnapshot:
    date: date
    equity: float  # cash + Σ shares_i * close_tr[i]
    cash: float
    invested_value: float  # Σ shares_i * close_tr[i]
    exposure: float  # invested_value / equity  (0–1)
    n_positions: int
