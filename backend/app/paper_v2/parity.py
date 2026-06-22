"""Monthly shadow-backtest parity — the fidelity test (11 §2/§7.1).

At each monthly rebalance we re-derive the S3 book *from scratch* with the backtest
brain (``engine.build_context`` + ``engine.step_day`` over the full live history through
the rebalance date) and assert the **live** book's holdings equal the engine's target
holdings, per-name weight deviation within tolerance ``T`` (default 25 bps of book
weight, §10.9). A break is an engine bug, never a signal (11 §8): it halts the run and
resets the 6-month clock (§7.1).

Because the shadow re-derivation calls the SAME ``step_day`` the live shell calls, any
deviation is attributable only to the live persistence/queue path — exactly what the
parity check is meant to catch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.backtest_v2 import engine
from app.backtest_v2.costs import CostLevel
from app.db.models import PaperV2Position
from app.paper_v2.live_engine import build_live_context

log = logging.getLogger(__name__)

# Tolerance T (11 §10.9): per-name weight deviation attributable to fill-price timing.
PARITY_TOL_BPS = 25.0


@dataclass
class ParityReport:
    as_of: date
    passed: bool
    max_dev_bps: float
    breaches: list[tuple[str, float]] = field(default_factory=list)  # (isin, dev_bps)
    engine_weights: dict[str, float] = field(default_factory=dict)
    live_weights: dict[str, float] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        verdict = "PASS" if self.passed else "BREAK"
        return (
            f"[parity {self.as_of}] {verdict} max_dev={self.max_dev_bps:.1f}bps "
            f"breaches={len(self.breaches)}"
        )


def _weights(positions: dict[str, "engine.Position"]) -> dict[str, float]:
    equity = sum(p.shares * p.last_price for p in positions.values())
    if equity <= 0:
        return {}
    return {isin: (p.shares * p.last_price) / equity for isin, p in positions.items()}


def _live_weights(session, portfolio_id: int) -> dict[str, float]:
    rows = (
        session.query(PaperV2Position)
        .filter(PaperV2Position.portfolio_id == portfolio_id)
        .all()
    )
    equity = sum(r.shares * (r.last_price or r.cost_basis) for r in rows)
    if equity <= 0:
        return {}
    return {r.isin: (r.shares * (r.last_price or r.cost_basis)) / equity for r in rows}


def shadow_parity(
    session,
    portfolio_id: int,
    prices: pd.DataFrame,
    index_prices: pd.Series | None,
    as_of_date: date,
    *,
    cost_level: CostLevel = "base",
    tol_bps: float = PARITY_TOL_BPS,
) -> ParityReport:
    """Re-derive the engine book through ``as_of_date`` and compare to the live book."""
    ctx, calendar = build_live_context(prices, index_prices, cost_level=cost_level)
    as_of_ts = pd.Timestamp(as_of_date)

    state = engine.LoopState(
        portfolio=engine.Portfolio(cash=ctx.config.starting_capital),
        pending_fills=[],
        rebalance_dates_used=[],
        per_rebalance_turnover=[],
    )
    for day in calendar:
        if day > as_of_ts:
            break
        engine.step_day(ctx, state, day)

    engine_w = _weights(state.portfolio.positions)
    live_w = _live_weights(session, portfolio_id)

    all_isins = set(engine_w) | set(live_w)
    breaches: list[tuple[str, float]] = []
    max_dev = 0.0
    tol = tol_bps / 1e4
    for isin in all_isins:
        dev = abs(live_w.get(isin, 0.0) - engine_w.get(isin, 0.0))
        max_dev = max(max_dev, dev)
        if dev > tol:
            breaches.append((isin, dev * 1e4))

    return ParityReport(
        as_of=as_of_date,
        passed=not breaches,
        max_dev_bps=max_dev * 1e4,
        breaches=sorted(breaches, key=lambda kv: kv[1], reverse=True),
        engine_weights=engine_w,
        live_weights=live_w,
    )
