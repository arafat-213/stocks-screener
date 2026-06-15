"""
engine.py — time-driven daily loop orchestrator (T7).

Authoritative control flow per 02 §3:

  for day in calendar:
    1. mark_to_market(day, close_tr prices)  →  DailySnapshot
    2. catastrophic stop check (close-based, fill at next open)
    3. deployable_fraction = regime.deployable_fraction(day)
    4. on rebalance_dates: build_rebalance_plan → queue fills at next open
    5. apply_fills(fills queued on prior day)

Invariants (02 §3):
  - All decisions use data ≤ decision date.
  - All fills execute at the NEXT session's open.
  - No same-bar decide-and-fill.
  - No intrabar high/low peeking.
  - Catastrophic stop triggers on close breach, fills next open.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.costs import CostConfig, CostFn
from app.backtest_v2.costs import fill_cost as _default_fill_cost
from app.backtest_v2.portfolio import Portfolio, build_rebalance_plan
from app.backtest_v2.regime import RegimeConfig, RegimeOverlay
from app.backtest_v2.schemas import DailySnapshot, Fill, RebalancePlan
from app.backtest_v2.signals import SignalStore, precompute_signals

log = logging.getLogger(__name__)

# Minimum ₹ notional for a fill to be worth executing (avoid hairline rounding fills).
_MIN_FILL_NOTIONAL = 1.0


@dataclass
class EngineResult:
    """All outputs from a completed backtest run."""

    snapshots: list[DailySnapshot]
    fills_log: list[Fill]
    suspension_log: dict[str, list[date]]
    rebalance_dates_used: list[date]
    per_rebalance_turnover: list[tuple[date, float]]  # (date, Σ|Δweight|)
    config: MomentumConfig
    total_cost_paid: float


def run(
    prices: pd.DataFrame,
    config: MomentumConfig,
    *,
    index_prices: pd.Series | None = None,
    regime_config: RegimeConfig | None = None,
    cost_fn: CostFn = _default_fill_cost,
    cost_cfg: CostConfig | None = None,
    signal_store: SignalStore | None = None,
) -> EngineResult:
    """
    Execute the v2 daily loop over `prices` and return an EngineResult.

    Parameters
    ----------
    prices : pd.DataFrame
        Long-format multi-ISIN frame from store.read_prices_adjusted.
        Required columns: isin, date, open, close, close_tr, adv_20.
        `date` column must be datetime64 or date-like.
    config : MomentumConfig
        Strategy configuration.
    index_prices : pd.Series | None
        DatetimeIndex → daily close of the market index (injected for regime
        overlay).  If None and use_regime_overlay=True, regime defaults to
        risk-on (deployable_fraction=1.0) every day with a warning.
    regime_config : RegimeConfig | None
        Passed to RegimeOverlay; defaults to RegimeConfig() if None.
    cost_fn : CostFn
        Injectable cost function; defaults to the placeholder fill_cost.
    cost_cfg : CostConfig | None
        Cost parameters; defaults to CostConfig() if None.
    signal_store : SignalStore | None
        Pre-built SignalStore; if None, precompute_signals is called here.
        Pass a pre-built store to avoid recomputing in tests or sweeps.
    """
    if cost_cfg is None:
        cost_cfg = CostConfig()

    # ------------------------------------------------------------------ #
    # 1. Normalise the prices DataFrame
    # ------------------------------------------------------------------ #
    prices = prices.copy()
    prices["date"] = pd.to_datetime(prices["date"])

    # Build fast lookup dicts: {date → {isin → value}}
    # close_tr for MTM/P&L, close for stop check, open for fills, adv_20 for costs.
    _close_tr = _pivot(prices, "close_tr")
    _close = _pivot(prices, "close")
    _open = _pivot(prices, "open")
    _adv_20 = _pivot(prices, "adv_20")

    # isin → symbol (latest known)
    _sym_map: dict[str, str] = (
        prices.sort_values("date")
        .drop_duplicates("isin", keep="last")
        .set_index("isin")["symbol"]
        .to_dict()
    )

    # ------------------------------------------------------------------ #
    # 2. Trading calendar (sorted distinct dates in prices)
    # ------------------------------------------------------------------ #
    calendar: list[pd.Timestamp] = sorted(_close_tr.keys())
    if not calendar:
        raise ValueError("prices DataFrame has no valid dates.")

    start_ts = pd.Timestamp(config.date_from) if config.date_from else calendar[0]
    end_ts = pd.Timestamp(config.date_to) if config.date_to else calendar[-1]
    calendar = [d for d in calendar if start_ts <= d <= end_ts]
    if not calendar:
        raise ValueError(f"No trading dates in [{config.date_from}, {config.date_to}].")

    # ------------------------------------------------------------------ #
    # 3. Rebalance dates (last trading day of each month within the run)
    # ------------------------------------------------------------------ #
    rebalance_dates: set[pd.Timestamp] = _month_end_dates(calendar)

    # ------------------------------------------------------------------ #
    # 4. Signals (precomputed once)
    # ------------------------------------------------------------------ #
    if signal_store is None:
        signal_store = precompute_signals(prices, config)

    # ------------------------------------------------------------------ #
    # 5. Regime overlay
    # ------------------------------------------------------------------ #
    if config.use_regime_overlay and index_prices is not None:
        overlay = RegimeOverlay(index_prices, cfg=regime_config)
    else:
        if config.use_regime_overlay and index_prices is None:
            log.warning(
                "use_regime_overlay=True but no index_prices injected; "
                "defaulting to risk-on (deployable_fraction=1.0) every day."
            )
        overlay = None

    # ------------------------------------------------------------------ #
    # 6. Universe (all ISINs present in prices — point-in-time filter is
    #    done per day via universe_membership from the prices frame itself)
    # ------------------------------------------------------------------ #
    # isin → set of dates it traded (for point-in-time membership)
    _membership: dict[str, set[pd.Timestamp]] = {}
    for isin, group in prices.groupby("isin"):
        _membership[str(isin)] = set(pd.to_datetime(group["date"]))

    # ------------------------------------------------------------------ #
    # 7. Main loop
    # ------------------------------------------------------------------ #
    portfolio = Portfolio(cash=config.starting_capital)
    pending_fills: list[Fill] = []  # fills queued on day D, applied on D+1

    rebalance_dates_used: list[date] = []
    per_rebalance_turnover: list[tuple[date, float]] = []

    for i, day in enumerate(calendar):
        day_date = day.date()

        # ---- 5.i: apply fills queued on the prior day (at today's open) -----
        if pending_fills:
            open_prices_today = _open.get(day, {})
            # Sort: sells/trims before buys so exits replenish cash before new purchases.
            _side_order = {"sell": 0, "trim": 1, "buy": 2}
            pending_fills.sort(key=lambda f: _side_order.get(f.side, 9))
            stamped_fills = _stamp_fills(pending_fills, open_prices_today, day_date)
            # Clamp buys to projected cash (sell proceeds + current cash, net of all
            # costs) to prevent implicit leverage when buys were sized against equity
            # that includes positions sold on the same rebalance day.
            stamped_fills = _clamp_buys_to_cash(
                stamped_fills, portfolio.cash, cost_fn, cost_cfg
            )
            adv_today = _adv_20.get(day, {})
            portfolio.apply_fills(
                stamped_fills,
                cost_fn=cost_fn,
                cost_cfg=cost_cfg,
                adv_lookup=adv_today,
            )
            pending_fills = []

        # ---- 5.ii: MTM at today's close_tr --------------------------------
        close_tr_today: dict[str, float] = _close_tr.get(day, {})
        portfolio.mark_to_market(day_date, close_tr_today)

        # ---- 5.iii: catastrophic stop check (close-based, next open fill) --
        close_today: dict[str, float] = _close.get(day, {})
        if config.catastrophic_stop_pct > 0:
            for isin, pos in list(portfolio.positions.items()):
                c = close_today.get(isin)
                if c is None:
                    continue
                stop_level = pos.cost_basis * (
                    1.0 - config.catastrophic_stop_pct / 100.0
                )
                if c <= stop_level:
                    log.info(
                        "Catastrophic stop triggered: %s close=%.4f ≤ stop=%.4f on %s",
                        isin,
                        c,
                        stop_level,
                        day_date,
                    )
                    pending_fills.append(
                        Fill(
                            isin=isin,
                            symbol=pos.symbol,
                            side="sell",
                            qty=pos.shares,
                            price=pos.last_price,  # placeholder; stamped to next open
                            date=day_date,
                            cost_rupees=0.0,
                        )
                    )

        # ---- 5.iv: regime deployable fraction for today -------------------
        deployable_fraction = overlay.deployable_fraction(day) if overlay else 1.0

        # ---- 5.v: rebalance (decision at close, fills queued for next open) -
        if day in rebalance_dates:
            # Point-in-time universe: ISINs that have a price print today
            universe_today = [
                isin for isin, dates in _membership.items() if day in dates
            ]
            # Entry gate and ranking
            ranked = signal_store.eligible_ranked(day, universe_today)
            # Entry gate map for build_rebalance_plan
            entry_gate_map = {
                isin: signal_store.entry_gate(day, isin) for isin in universe_today
            }
            prev_weights = _current_weights(portfolio)

            plan: RebalancePlan = build_rebalance_plan(
                portfolio=portfolio,
                ranked=ranked,
                deployable_fraction=deployable_fraction,
                config=config,
                entry_gate_map=entry_gate_map,
                prices=close_today,
                symbols=_sym_map,
                decision_date=day_date,
            )

            rebalance_fills = plan.sells + plan.buys + plan.trims

            # Record turnover before queuing (using decision-date weights).
            equity_now = portfolio.equity
            turnover = _compute_turnover(
                plan, prev_weights, config.target_positions, equity_now
            )
            per_rebalance_turnover.append((day_date, turnover))
            rebalance_dates_used.append(day_date)

            # De-duplicate: if a catastrophic stop already queued a sell for
            # the same ISIN, drop it from the rebalance sells to avoid double-exit.
            stop_isins = {f.isin for f in pending_fills if f.side == "sell"}
            for f in rebalance_fills:
                if f.isin in stop_isins and f.side == "sell":
                    continue  # already queued via stop
                pending_fills.append(f)

    return EngineResult(
        snapshots=portfolio.snapshots,
        fills_log=portfolio.fills_log,
        suspension_log=portfolio.suspension_log,
        rebalance_dates_used=rebalance_dates_used,
        per_rebalance_turnover=per_rebalance_turnover,
        config=config,
        total_cost_paid=portfolio._total_cost_paid,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pivot(prices: pd.DataFrame, col: str) -> dict[pd.Timestamp, dict[str, float]]:
    """
    Build {date → {isin → value}} mapping from the long-format prices frame.

    Only rows where `col` is not NaN are included.
    """
    result: dict[pd.Timestamp, dict[str, float]] = {}
    sub = prices[["date", "isin", col]].dropna(subset=[col])
    for row in sub.itertuples(index=False):
        ts = pd.Timestamp(row.date)
        result.setdefault(ts, {})[str(row.isin)] = float(getattr(row, col))
    return result


def _month_end_dates(calendar: list[pd.Timestamp]) -> set[pd.Timestamp]:
    """
    Return the last trading day of each calendar month present in `calendar`.

    Uses the month/year grouping of sorted timestamps; the maximum timestamp
    per (year, month) group is the last trading day of that month.
    """
    groups: dict[tuple[int, int], pd.Timestamp] = {}
    for ts in calendar:
        key = (ts.year, ts.month)
        if key not in groups or ts > groups[key]:
            groups[key] = ts
    return set(groups.values())


def _stamp_fills(
    fills: list[Fill],
    open_prices: dict[str, float],
    exec_date: date,
) -> list[Fill]:
    """
    Replace placeholder prices on fills with the actual next-session open.

    For buy fills, qty is recalculated as target_notional / open_price so that
    the intended ₹ allocation is preserved at the actual execution price,
    avoiding cash overruns when open > decision-close.  (target_notional is
    recovered from the placeholder fill as qty * placeholder_price.)

    Fills for ISINs with no open price (halted/unlisted) are dropped with a
    warning — the position remains held at its last MTM price.
    """
    stamped: list[Fill] = []
    for f in fills:
        p = open_prices.get(f.isin)
        if p is None or p <= 0.0:
            log.warning(
                "No open price for %s on %s; fill dropped (position carried).",
                f.isin,
                exec_date,
            )
            continue

        if f.side == "buy":
            # Recalculate qty so the ₹ notional at open == original target notional.
            target_notional = f.qty * f.price  # target ₹ at decision-close price
            qty = target_notional / p
        else:
            qty = f.qty  # sell/trim: share count is fixed by position size

        if qty * p < _MIN_FILL_NOTIONAL:
            continue  # hairline rounding fill — skip

        stamped.append(
            Fill(
                isin=f.isin,
                symbol=f.symbol,
                side=f.side,
                qty=qty,
                price=p,
                date=exec_date,
                cost_rupees=0.0,  # recomputed by apply_fills
            )
        )
    return stamped


def _current_weights(portfolio: Portfolio) -> dict[str, float]:
    """Return {isin → weight} using last-known prices (pre-rebalance snapshot)."""
    equity = portfolio.equity
    if equity <= 0:
        return {}
    return {
        isin: (pos.shares * pos.last_price) / equity
        for isin, pos in portfolio.positions.items()
    }


def _clamp_buys_to_cash(
    fills: list[Fill],
    available_cash: float,
    cost_fn: CostFn,
    cost_cfg: CostConfig,
) -> list[Fill]:
    """
    Scale all buy fills proportionally so total cash outflow (notional + costs)
    fits within projected cash: current cash + sell/trim proceeds net of their costs.

    WHY: build_rebalance_plan sizes targets against portfolio.equity, which includes
    positions being sold on the same rebalance day.  Without this clamp, buys can
    exceed actual post-sell cash, producing implicit leverage (exposure > 100%).

    adv_20 is passed as 0.0 to the cost_fn for the projection (placeholder; the real
    cost model in spec 03 uses adv for slippage but the per-fill cost ratio is the same).
    Cost linearity in qty guarantees the scaled outflow equals projected_cash exactly.
    """
    projected_cash = available_cash
    total_buy_outflow = 0.0

    for f in fills:
        if f.side in ("sell", "trim"):
            cost = cost_fn(f.side, f.qty, f.price, 0.0, cost_cfg)
            projected_cash += f.qty * f.price - cost
        else:
            cost = cost_fn("buy", f.qty, f.price, 0.0, cost_cfg)
            total_buy_outflow += f.qty * f.price + cost

    if total_buy_outflow <= 0.0 or total_buy_outflow <= projected_cash:
        return fills

    scale = projected_cash / total_buy_outflow
    log.info(
        "Buy outflow %.2f > projected cash %.2f; scaling buys by %.6f to prevent leverage.",
        total_buy_outflow,
        projected_cash,
        scale,
    )
    result: list[Fill] = []
    for f in fills:
        if f.side == "buy":
            result.append(
                Fill(
                    isin=f.isin,
                    symbol=f.symbol,
                    side=f.side,
                    qty=f.qty * scale,
                    price=f.price,
                    date=f.date,
                    cost_rupees=0.0,
                )
            )
        else:
            result.append(f)
    return result


def _compute_turnover(
    plan: RebalancePlan,
    prev_weights: dict[str, float],
    target_positions: int,
    equity: float,
) -> float:
    """
    Turnover = Σ |target_weight − current_weight| for all touched names.

    Returns a fraction [0, ∞); typically ≤ 2.0 for a full portfolio rotation.
    """
    if equity <= 0 or target_positions <= 0:
        return 0.0

    target_weights: dict[str, float] = {}
    for f in plan.buys + plan.trims:
        delta = (f.qty * f.price) / equity
        if f.side == "buy":
            target_weights[f.isin] = prev_weights.get(f.isin, 0.0) + delta
        else:  # trim
            target_weights[f.isin] = max(0.0, prev_weights.get(f.isin, 0.0) - delta)
    for f in plan.sells:
        target_weights[f.isin] = 0.0

    all_isins = set(prev_weights) | set(target_weights)
    return sum(
        abs(target_weights.get(i, prev_weights.get(i, 0.0)) - prev_weights.get(i, 0.0))
        for i in all_isins
    )
