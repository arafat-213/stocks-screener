"""
portfolio.py — Portfolio state, mark-to-market, and fill application (T5).

build_rebalance_plan with hysteresis (T6) is stubbed below; it will be
implemented in the T6 session.

Key invariants (02 §6):
  - MTM uses close_tr prices (total return); signals/ranking never touch this module.
  - Fills execute at next-session's open; the engine owns the D/D+1 queue discipline.
  - Suspended ISINs (no price print) carry last known price and are flagged, not zeroed.
  - Cash conservation: equity == cash + Σ shares * last_price at all times (02 §10.2).
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from app.backtest_v2.costs import CostConfig, CostFn
from app.backtest_v2.costs import fill_cost as _default_fill_cost
from app.backtest_v2.types import DailySnapshot, Fill, Position, RebalancePlan

if TYPE_CHECKING:
    from app.backtest_v2.config import MomentumConfig

log = logging.getLogger(__name__)

# Treat residual share counts ≤ this as zero (floating-point rounding).
_SHARE_EPS = 1e-9


def _to_date(d: date | pd.Timestamp) -> date:
    return d.date() if isinstance(d, pd.Timestamp) else d


def _is_missing(v: object) -> bool:
    """True if value is None or NaN."""
    if v is None:
        return True
    try:
        return math.isnan(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


class Portfolio:
    """
    Mutable portfolio state for one backtest run.

    Driven by the engine's daily loop (T7):
      1. mark_to_market(day, prices)          — MTM using close_tr prices
      2. apply_fills(fills, cost_fn, cfg)     — execute next-open fills

    Internal state:
      cash          — undeployed ₹
      positions     — dict[isin → Position] (replaced on each update; Position is frozen)
      snapshots     — chronological DailySnapshot list (equity + exposure curves)
      fills_log     — all executed fills with actual cost_rupees
      suspension_log — {isin: [dates]} where price was missing; for audit
      _total_cost_paid — running Σ of fill_cost results (02 §10.2 audit)
    """

    def __init__(self, cash: float) -> None:
        if cash < 0:
            raise ValueError(f"Starting cash must be ≥ 0; got {cash!r}")
        self.cash: float = cash
        self.positions: dict[str, Position] = {}
        self.snapshots: list[DailySnapshot] = []
        self.fills_log: list[Fill] = []
        self.suspension_log: dict[str, list[date]] = {}
        self._total_cost_paid: float = 0.0

    # ------------------------------------------------------------------
    # Mark to market  (02 §6)
    # ------------------------------------------------------------------

    def mark_to_market(
        self,
        day: date | pd.Timestamp,
        prices: dict[str, float],
    ) -> DailySnapshot:
        """
        Revalue all positions using close_tr prices for `day`.

        `prices` must be a mapping {isin → close_tr} for the day being valued.
        Positions absent from `prices` (suspension or holiday gap) carry their
        `last_price` and are logged to `self.suspension_log`.

        Returns the DailySnapshot for this day (also appended to self.snapshots).
        """
        _day = _to_date(day)
        invested_value: float = 0.0
        updated: dict[str, Position] = {}

        for isin, pos in self.positions.items():
            raw = prices.get(isin)
            if not _is_missing(raw):
                current_price = float(raw)  # type: ignore[arg-type]
            else:
                current_price = pos.last_price
                self._flag_suspension(isin, _day)
                log.warning(
                    "MTM %s: no close_tr for %s; carrying last=%.4f",
                    _day,
                    isin,
                    current_price,
                )

            invested_value += pos.shares * current_price
            updated[isin] = Position(
                isin=pos.isin,
                symbol=pos.symbol,
                shares=pos.shares,
                cost_basis=pos.cost_basis,
                entry_date=pos.entry_date,
                last_price=current_price,
            )

        self.positions = updated
        equity = self.cash + invested_value
        exposure = (invested_value / equity) if equity > _SHARE_EPS else 0.0

        snap = DailySnapshot(
            date=_day,
            equity=equity,
            cash=self.cash,
            invested_value=invested_value,
            exposure=exposure,
            n_positions=len(self.positions),
        )
        self.snapshots.append(snap)
        return snap

    # ------------------------------------------------------------------
    # Apply fills  (02 §6)
    # ------------------------------------------------------------------

    def apply_fills(
        self,
        fills: list[Fill],
        cost_fn: CostFn = _default_fill_cost,
        cost_cfg: CostConfig | None = None,
        adv_lookup: dict[str, float] | None = None,
    ) -> None:
        """
        Execute queued fills against portfolio state.

        `cost_fn` is injected so spec 03 swaps in the real statutory+slippage
        model as a one-line change.  The `cost_rupees` field on incoming Fill
        objects is *ignored*; this method computes and records the actual cost
        so `fills_log` is the single authoritative source (02 §10.2).

        Cash accounting:
          buy  → cash -= qty * price + cost
          sell → cash += qty * price − cost
          trim → cash += qty * price − cost   (same mechanics as sell)

        Zero-qty fills are silently skipped.
        """
        if cost_cfg is None:
            cost_cfg = CostConfig()
        _adv = adv_lookup or {}

        for fill in fills:
            if fill.qty <= 0:
                continue

            # Guard: skip sell/trim fills for positions that don't exist.
            if fill.side in ("sell", "trim") and fill.isin not in self.positions:
                log.warning(
                    "Sell/trim of %s with no open position; fill skipped.", fill.isin
                )
                continue

            adv_20 = _adv.get(fill.isin, 0.0)
            cost = cost_fn(fill.side, fill.qty, fill.price, adv_20, cost_cfg)
            notional = fill.qty * fill.price

            self.fills_log.append(
                Fill(
                    isin=fill.isin,
                    symbol=fill.symbol,
                    side=fill.side,
                    qty=fill.qty,
                    price=fill.price,
                    date=fill.date,
                    cost_rupees=cost,
                )
            )
            self._total_cost_paid += cost

            if fill.side == "buy":
                self._do_buy(
                    fill.isin, fill.symbol, fill.qty, fill.price, cost, fill.date
                )
                self.cash -= notional + cost

            elif fill.side in ("sell", "trim"):
                self._do_reduce(fill.isin, fill.qty)
                self.cash += notional - cost

            else:
                raise ValueError(f"Unknown fill side: {fill.side!r}")

            if self.cash < -_SHARE_EPS:
                log.warning(
                    "Portfolio cash went negative (%.2f) after %s %s — "
                    "engine should size fills to available capital.",
                    self.cash,
                    fill.side,
                    fill.isin,
                )

    # ------------------------------------------------------------------
    # Convenience property
    # ------------------------------------------------------------------

    @property
    def equity(self) -> float:
        """
        Current equity from last-known prices.

        Between MTM calls this may be slightly stale (new-position last_price
        is the fill price, not a fresh market price).  The engine always calls
        mark_to_market before reading equity for decisions.
        """
        return self.cash + sum(p.shares * p.last_price for p in self.positions.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _do_buy(
        self,
        isin: str,
        symbol: str,
        qty: float,
        price: float,
        cost: float,
        entry_date: date,
    ) -> None:
        """Create or augment a Position.  Cost basis is weighted-avg inclusive of fees."""
        if isin in self.positions:
            pos = self.positions[isin]
            new_shares = pos.shares + qty
            # Roll transaction cost into weighted-average cost basis.
            new_basis = (pos.shares * pos.cost_basis + qty * price + cost) / new_shares
            self.positions[isin] = Position(
                isin=isin,
                symbol=symbol,
                shares=new_shares,
                cost_basis=new_basis,
                entry_date=pos.entry_date,  # preserve original entry date
                last_price=price,
            )
        else:
            per_share_basis = (qty * price + cost) / qty
            self.positions[isin] = Position(
                isin=isin,
                symbol=symbol,
                shares=qty,
                cost_basis=per_share_basis,
                entry_date=entry_date,
                last_price=price,
            )

    def _do_reduce(self, isin: str, qty: float) -> None:
        """Reduce (or fully exit) a position by `qty` shares."""
        if isin not in self.positions:
            log.warning("Sell/trim of %s with no open position; fill ignored.", isin)
            return
        pos = self.positions[isin]
        remaining = pos.shares - qty
        if remaining <= _SHARE_EPS:
            del self.positions[isin]
        else:
            self.positions[isin] = Position(
                isin=isin,
                symbol=pos.symbol,
                shares=remaining,
                cost_basis=pos.cost_basis,
                entry_date=pos.entry_date,
                last_price=pos.last_price,
            )

    def _flag_suspension(self, isin: str, day: date) -> None:
        self.suspension_log.setdefault(isin, []).append(day)


# ---------------------------------------------------------------------------
# T6 — build_rebalance_plan  (implement in T6 session)
# ---------------------------------------------------------------------------


def build_rebalance_plan(
    portfolio: Portfolio,
    ranked: list[tuple[str, float]],  # [(isin, score), ...] descending by score
    deployable_fraction: float,
    config: "MomentumConfig",
    entry_gate_map: dict[str, bool] | None = None,  # isin → bool; None = all eligible
) -> RebalancePlan:
    """
    Build sells/buys/trims for the next rebalance.

    Hysteresis (02 §5):
      - Sell if rank > sell_rank_buffer (M) OR name fails entry gate.
      - Hold otherwise (let winners run).
      - Buy top names (rank ≤ target_positions N) until slots filled.
      - Equal-weight reset: target ₹ = deployable_fraction * equity / target_positions.
      - Remainder stays in cash — never force-deploy.

    NOT YET IMPLEMENTED — implement in T6.
    """
    raise NotImplementedError("build_rebalance_plan — implement in T6")
