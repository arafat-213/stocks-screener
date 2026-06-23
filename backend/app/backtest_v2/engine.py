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

import bisect
import logging
import math
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.costs import CostConfig, CostFn, CostLevel
from app.backtest_v2.costs import effective_price as _effective_price
from app.backtest_v2.costs import fill_cost as _default_fill_cost
from app.backtest_v2.identity import collapse_to_instrument_id
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


@dataclass
class EngineContext:
    """Immutable per-run lookups + collaborators shared by run() and the live paper
    shell (11 §2/§3e). Built once by build_context(); consumed by step_day()."""

    config: MomentumConfig
    cost_fn: CostFn
    cost_cfg: CostConfig
    close_tr: dict[pd.Timestamp, dict[str, float]]
    close: dict[pd.Timestamp, dict[str, float]]
    open: dict[pd.Timestamp, dict[str, float]]
    adv_20: dict[pd.Timestamp, dict[str, float]]
    sym_map: dict[str, str]
    membership: dict[str, set[pd.Timestamp]]
    rebalance_dates: set[pd.Timestamp]
    signal_store: SignalStore
    overlay: RegimeOverlay | None

    # --- 07 (Merger/Cancellation identity continuity) — force-exit at termination ---
    # K = trading days of price-silence after which a held instrument with no
    # `instrument_id` successor (06) is declared TERMINATED and force-liquidated to cash
    # at its last price (07 §6, Approach A). 0 ⇒ feature OFF ⇒ run() byte-for-byte
    # unchanged (parity suite). The two lookups below are built only when K > 0.
    terminate_after_silent_days: int = 0

    # --- Whole-share sizing (NSE reality: equity delivery trades only in integer
    # shares; lot size 1). When True, every buy/trim fill is floored to whole shares
    # at apply time (the single Portfolio.apply_fills chokepoint). Default False ⇒
    # run() byte-for-byte unchanged (parity suite + the closed v2/v3 research record
    # both reproduce). The S3 paper shell sets this True so the forward probation is a
    # faithful integer-share rehearsal of real-capital execution (11 §13 deviation,
    # signed 2026-06-23). Cash-safe: _clamp_buys_to_cash runs before apply_fills, so
    # floored qty <= clamped qty <= affordable; the equity == cash + Σshares·price
    # identity is unaffected (only the absolute equity level shifts ~0.5%).
    whole_shares: bool = False
    cal_ord: dict[pd.Timestamp, int] = field(default_factory=dict)
    inst_trade_ords: dict[str, list[int]] = field(default_factory=dict)


@dataclass
class LoopState:
    """Mutable loop state carried across days. In a backtest this lives in memory for
    the whole run; in the live shell (11 §3e) it is hydrated from / persisted to the
    paper_v2 tables each day, so the persisted pending_fills queue reproduces the
    engine's D→D+1 fill discipline across process restarts."""

    portfolio: Portfolio
    pending_fills: list[Fill]
    rebalance_dates_used: list[date]
    per_rebalance_turnover: list[tuple[date, float]]


def run(
    prices: pd.DataFrame,
    config: MomentumConfig,
    *,
    index_prices: pd.Series | None = None,
    regime_config: RegimeConfig | None = None,
    cost_fn: CostFn = _default_fill_cost,
    cost_cfg: CostConfig | None = None,
    cost_level: CostLevel | None = None,
    signal_store: SignalStore | None = None,
    terminate_after_silent_days: int = 0,
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
        Ignored when cost_level is set.
    cost_level : CostLevel | None
        "optimistic" | "base" | "pessimistic" preset (spec 03 T4).
        When set, derives cost_cfg from the preset and overrides any explicit
        cost_cfg.  Enables single-parameter sensitivity runs.
    signal_store : SignalStore | None
        Pre-built SignalStore; if None, precompute_signals is called here.
        Pass a pre-built store to avoid recomputing in tests or sweeps.
    terminate_after_silent_days : int
        07 force-exit-at-termination control (Approach A). 0 (default) disables it,
        so run() is byte-for-byte identical to its pre-07 behaviour. When > 0, a held
        instrument with no `instrument_id` successor that has been price-silent for at
        least this many trading days is force-liquidated to cash at its last price.
    """
    ctx, calendar = build_context(
        prices,
        config,
        index_prices=index_prices,
        regime_config=regime_config,
        cost_fn=cost_fn,
        cost_cfg=cost_cfg,
        cost_level=cost_level,
        signal_store=signal_store,
        terminate_after_silent_days=terminate_after_silent_days,
    )

    state = LoopState(
        portfolio=Portfolio(cash=config.starting_capital),
        pending_fills=[],  # fills queued on day D, applied on D+1
        rebalance_dates_used=[],
        per_rebalance_turnover=[],
    )

    for day in calendar:
        step_day(ctx, state, day)

    return EngineResult(
        snapshots=state.portfolio.snapshots,
        fills_log=state.portfolio.fills_log,
        suspension_log=state.portfolio.suspension_log,
        rebalance_dates_used=state.rebalance_dates_used,
        per_rebalance_turnover=state.per_rebalance_turnover,
        config=config,
        total_cost_paid=state.portfolio._total_cost_paid,
    )


def build_context(
    prices: pd.DataFrame,
    config: MomentumConfig,
    *,
    index_prices: pd.Series | None = None,
    regime_config: RegimeConfig | None = None,
    cost_fn: CostFn = _default_fill_cost,
    cost_cfg: CostConfig | None = None,
    cost_level: CostLevel | None = None,
    signal_store: SignalStore | None = None,
    terminate_after_silent_days: int = 0,
    whole_shares: bool = False,
) -> tuple[EngineContext, list[pd.Timestamp]]:
    """
    Build the immutable per-run lookups + trading calendar shared by run() and the
    live paper shell (11 §2/§3e).

    Extracted verbatim from run()'s former setup block (steps 1–6) so the live shell
    drives the SAME per-day logic (step_day) over the SAME context — fidelity by
    construction, not re-implementation (11 §2). run() is byte-for-byte unchanged
    (proven by the parity suite).
    """
    if cost_level is not None:
        cost_cfg = _cfg_for_level(cost_level)
    elif cost_cfg is None:
        cost_cfg = CostConfig()

    # 1. Normalise the prices DataFrame
    # Resolve identity to the chain-constant instrument_id (06 T06.3) FIRST, so the
    # price lookups, universe membership, and positions all key on instrument_id:
    # a held position carried across a succession resolves to the same key (no ghost),
    # and per-date price lookups resolve to whichever leg is live. No-op for
    # non-succession frames ⇒ run() stays byte-for-byte identical (parity suite).
    prices = collapse_to_instrument_id(prices)
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

    # 2. Trading calendar (sorted distinct dates in prices)
    calendar: list[pd.Timestamp] = sorted(_close_tr.keys())
    if not calendar:
        raise ValueError("prices DataFrame has no valid dates.")

    start_ts = pd.Timestamp(config.date_from) if config.date_from else calendar[0]
    end_ts = pd.Timestamp(config.date_to) if config.date_to else calendar[-1]
    calendar = [d for d in calendar if start_ts <= d <= end_ts]
    if not calendar:
        raise ValueError(f"No trading dates in [{config.date_from}, {config.date_to}].")

    # 3. Rebalance dates (last trading day per cadence period within the run)
    rebalance_dates: set[pd.Timestamp] = _rebalance_dates(calendar, config.rebalance)

    # 4. Signals (precomputed once)
    if signal_store is None:
        signal_store = precompute_signals(prices, config)

    # 5. Regime overlay
    if config.use_regime_overlay and index_prices is not None:
        overlay = RegimeOverlay(index_prices, cfg=regime_config)
    else:
        if config.use_regime_overlay and index_prices is None:
            log.warning(
                "use_regime_overlay=True but no index_prices injected; "
                "defaulting to risk-on (deployable_fraction=1.0) every day."
            )
        overlay = None

    # 6. Universe membership (point-in-time, from the prices frame itself)
    _membership: dict[str, set[pd.Timestamp]] = {}
    for isin, group in prices.groupby("isin"):
        _membership[str(isin)] = set(pd.to_datetime(group["date"]))

    # 7. Termination lookups (07 §6 force-exit) — built only when the feature is on,
    # so the default (K=0) run pays nothing and stays byte-for-byte identical.
    # cal_ord maps every trading date to its ordinal in the FULL price calendar (not
    # the windowed run calendar), so price-silence is counted in true trading days;
    # inst_trade_ords is each instrument's sorted print ordinals (for an O(log n)
    # "most-recent print ≤ day" lookup in step_day).
    _cal_ord: dict[pd.Timestamp, int] = {}
    _inst_trade_ords: dict[str, list[int]] = {}
    if terminate_after_silent_days > 0:
        full_cal = sorted(pd.to_datetime(prices["date"]).unique())
        _cal_ord = {pd.Timestamp(ts): i for i, ts in enumerate(full_cal)}
        for isin, dates in _membership.items():
            ords = sorted(_cal_ord[d] for d in dates if d in _cal_ord)
            _inst_trade_ords[isin] = ords

    ctx = EngineContext(
        config=config,
        cost_fn=cost_fn,
        cost_cfg=cost_cfg,
        close_tr=_close_tr,
        close=_close,
        open=_open,
        adv_20=_adv_20,
        sym_map=_sym_map,
        membership=_membership,
        rebalance_dates=rebalance_dates,
        signal_store=signal_store,
        overlay=overlay,
        terminate_after_silent_days=terminate_after_silent_days,
        whole_shares=whole_shares,
        cal_ord=_cal_ord,
        inst_trade_ords=_inst_trade_ords,
    )
    return ctx, calendar


def step_day(ctx: EngineContext, state: LoopState, day: pd.Timestamp) -> None:
    """
    Execute ONE trading day of the v2 loop (02 §3) against mutable `state` using the
    immutable `ctx`. This is the exact former body of run()'s per-day loop, extracted
    so the live paper shell (11 §3e) drives identical logic across process restarts
    via a persisted pending-fills queue.

    HARD ORDERING INVARIANT (11 §3e): execute the prior session's queued fills (5.i)
    ALWAYS runs BEFORE the catastrophic-stop check (5.iii), so a name bought at today's
    open with its cost_basis set in 5.i is stop-eligible on the same day's close.
    """
    config = ctx.config
    portfolio = state.portfolio
    day_date = day.date()

    # ---- 5.i: apply fills queued on the prior day (at today's open) -----
    if state.pending_fills:
        open_prices_today = ctx.open.get(day, {})
        adv_today = ctx.adv_20.get(day, {})
        # Sort: sells/trims before buys so exits replenish cash before new purchases.
        _side_order = {"sell": 0, "trim": 1, "buy": 2}
        state.pending_fills.sort(key=lambda f: _side_order.get(f.side, 9))
        # Stamp fills with next-open price and apply slippage as an effective
        # price adjustment (spec 03 §1.3 option a — slippage moves cost basis).
        stamped_fills = _stamp_fills(
            state.pending_fills, open_prices_today, day_date, adv_today, ctx.cost_cfg
        )
        # Clamp buys to projected cash to prevent implicit leverage.
        stamped_fills = _clamp_buys_to_cash(
            stamped_fills,
            portfolio.cash,
            ctx.cost_fn,
            ctx.cost_cfg,
            whole_shares=ctx.whole_shares,
        )
        portfolio.apply_fills(
            stamped_fills,
            cost_fn=ctx.cost_fn,
            cost_cfg=ctx.cost_cfg,
            adv_lookup=adv_today,
            whole_shares=ctx.whole_shares,
        )
        state.pending_fills = []

    # ---- 5.ii: MTM at today's close_tr --------------------------------
    close_tr_today: dict[str, float] = ctx.close_tr.get(day, {})
    portfolio.mark_to_market(day_date, close_tr_today)

    # ---- 5.ii-b: 07 force-exit at termination (Approach A) ------------
    # A held instrument with no `instrument_id` successor that has been price-silent
    # for >= K trading days is TERMINATED (merged-away / cancelled / delisted, 07 §1):
    # it has no forward price, so a queued sell would be dropped (_stamp_fills) and the
    # position carried forever as an MTM-frozen ghost. Liquidate it to cash at its last
    # price NOW — after MTM (so last_price is current) and BEFORE the stop/rebalance
    # steps (so no doomed sell is queued for it). Re-entry needs no explicit bar: a dead
    # ISIN never prints again, so it can never re-enter universe_today (07 §6.3).
    if ctx.terminate_after_silent_days > 0:
        _force_exit_terminated(ctx, portfolio, day, day_date)

    # ---- 5.iii: catastrophic stop check (close-based, next open fill) --
    close_today: dict[str, float] = ctx.close.get(day, {})
    if config.catastrophic_stop_pct > 0:
        for isin, pos in list(portfolio.positions.items()):
            c = close_today.get(isin)
            if c is None:
                continue
            stop_level = pos.cost_basis * (1.0 - config.catastrophic_stop_pct / 100.0)
            if c <= stop_level:
                log.info(
                    "Catastrophic stop triggered: %s close=%.4f ≤ stop=%.4f on %s",
                    isin,
                    c,
                    stop_level,
                    day_date,
                )
                state.pending_fills.append(
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
    deployable_fraction = ctx.overlay.deployable_fraction(day) if ctx.overlay else 1.0

    # ---- 5.v: rebalance (decision at close, fills queued for next open) -
    if day in ctx.rebalance_dates:
        # Point-in-time universe: ISINs that have a price print today
        universe_today = [
            isin for isin, dates in ctx.membership.items() if day in dates
        ]
        # Entry gate and ranking
        ranked = ctx.signal_store.eligible_ranked(day, universe_today)
        entry_gate_map = {
            isin: ctx.signal_store.entry_gate(day, isin) for isin in universe_today
        }
        prev_weights = _current_weights(portfolio)

        plan: RebalancePlan = build_rebalance_plan(
            portfolio=portfolio,
            ranked=ranked,
            deployable_fraction=deployable_fraction,
            config=config,
            entry_gate_map=entry_gate_map,
            prices=close_today,
            symbols=ctx.sym_map,
            decision_date=day_date,
        )

        rebalance_fills = plan.sells + plan.buys + plan.trims

        # Record turnover before queuing (using decision-date weights).
        equity_now = portfolio.equity
        turnover = _compute_turnover(
            plan, prev_weights, config.target_positions, equity_now
        )
        state.per_rebalance_turnover.append((day_date, turnover))
        state.rebalance_dates_used.append(day_date)

        # De-duplicate: if a catastrophic stop already queued a sell for the same
        # ISIN, drop it from the rebalance sells to avoid double-exit.
        stop_isins = {f.isin for f in state.pending_fills if f.side == "sell"}
        for f in rebalance_fills:
            if f.isin in stop_isins and f.side == "sell":
                continue  # already queued via stop
            state.pending_fills.append(f)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _silent_trading_days(
    ctx: EngineContext, isin: str, day: pd.Timestamp
) -> int | None:
    """Trading days of price-silence for `isin` as of `day` (07 §6 force-exit).

    Returns `day_ord − (ordinal of the most recent print on or before `day`)` using the
    full-calendar ordinals precomputed in build_context. Live-safe: it only observes the
    ABSENCE of prints up to `day` (no future knowledge), so the backtest and the live
    shell — both stepping the same ctx — declare termination on the identical day.

    Returns None when it cannot be determined (day not in the calendar, instrument has no
    print history, or no print on/before `day`); callers then leave the position untouched.
    """
    day_ord = ctx.cal_ord.get(day)
    ords = ctx.inst_trade_ords.get(isin)
    if day_ord is None or not ords:
        return None
    i = bisect.bisect_right(ords, day_ord) - 1
    if i < 0:
        return None  # no print on or before `day`
    return day_ord - ords[i]


def _force_exit_terminated(
    ctx: EngineContext,
    portfolio: Portfolio,
    day: pd.Timestamp,
    day_date: date,
) -> None:
    """Liquidate every held position that has terminated as of `day` (07 §6, Approach A).

    A position is terminated when its instrument has been price-silent for at least
    `ctx.terminate_after_silent_days` trading days (no `instrument_id` successor — a real
    succession keeps printing under the same id, so it is never silent). Exit is at the
    position's last MTM price (flat last-traded close_tr; no haircut — 07 §6.2), executed
    immediately through the normal `apply_fills` path so the exit is recorded in fills_log
    and pays standard statutory cost (zero ADV ⇒ base-slippage floor only, no divide).
    """
    K = ctx.terminate_after_silent_days
    adv_today = ctx.adv_20.get(day, {})
    exits: list[Fill] = []
    for isin, pos in list(portfolio.positions.items()):
        silent = _silent_trading_days(ctx, isin, day)
        if silent is None or silent < K:
            continue
        log.info(
            "07 force-exit: %s (%s) price-silent %d trading days ≥ K=%d on %s — "
            "liquidating %.4f shares at last price %.4f.",
            isin,
            pos.symbol,
            silent,
            K,
            day_date,
            pos.shares,
            pos.last_price,
        )
        exits.append(
            Fill(
                isin=isin,
                symbol=pos.symbol,
                side="sell",
                qty=pos.shares,
                price=pos.last_price,
                date=day_date,
                cost_rupees=0.0,
            )
        )
    if exits:
        portfolio.apply_fills(
            exits, cost_fn=ctx.cost_fn, cost_cfg=ctx.cost_cfg, adv_lookup=adv_today
        )


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


# Calendar months whose month-end is a rebalance day, per cadence.
# `None` = every month-end (the v2 default — byte-for-byte unchanged behavior).
# quarterly = calendar quarter-ends; semi-annual = half-year-ends.
_CADENCE_MONTHS: dict[str, frozenset[int] | None] = {
    "monthly": None,
    "quarterly": frozenset({3, 6, 9, 12}),
    "semi-annual": frozenset({6, 12}),
}


def _rebalance_dates(
    calendar: list[pd.Timestamp], cadence: str = "monthly"
) -> set[pd.Timestamp]:
    """
    Last trading day of each cadence period present in `calendar`.

    The membership-turnover lever (v3 T3): trading less often. Built as a thin
    filter on `_month_end_dates` so the monthly path is *identical* to v2's
    original behavior — `monthly` returns exactly `_month_end_dates(calendar)`,
    keeping v2's MomentumConfig run byte-for-byte unchanged (default cadence).

    `quarterly`/`semi-annual` keep only the month-ends landing on calendar
    quarter-ends ({3,6,9,12}) / half-year-ends ({6,12}). Fails loud on an
    unknown cadence (Rule 12).
    """
    try:
        months = _CADENCE_MONTHS[cadence]
    except KeyError:
        raise ValueError(
            f"unknown rebalance cadence: {cadence!r} (known: {sorted(_CADENCE_MONTHS)})"
        ) from None
    month_ends = _month_end_dates(calendar)
    if months is None:
        return month_ends
    return {ts for ts in month_ends if ts.month in months}


def _stamp_fills(
    fills: list[Fill],
    open_prices: dict[str, float],
    exec_date: date,
    adv_lookup: dict[str, float] | None = None,
    cost_cfg: CostConfig | None = None,
) -> list[Fill]:
    """
    Replace placeholder prices on fills with the actual next-session open,
    then apply slippage as an effective price adjustment (spec 03 §1.3).

    For buy fills, qty is recalculated as target_notional / effective_price so
    the intended ₹ allocation is preserved — fewer shares at the slipped price.

    Slippage moves the fill price (buys higher, sells lower), so cost basis and
    realized P&L reflect market impact rather than treating it as a fee-only term.
    When cost_cfg is None or uses the legacy round_trip_bps path, no slippage
    adjustment is applied (backwards-compat).

    Fills for ISINs with no open price (halted/unlisted) are dropped with a
    warning — the position remains held at its last MTM price.
    """
    _adv = adv_lookup or {}
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

        adv_20 = _adv.get(f.isin, 0.0)

        if f.side == "buy":
            # Recalculate qty so the ₹ notional at open == original target notional,
            # then apply slippage: fewer shares acquired at the higher effective price.
            target_notional = f.qty * f.price  # target ₹ at decision-close price
            raw_qty = target_notional / p
            if cost_cfg is not None:
                eff_p = _effective_price("buy", p, raw_qty, adv_20, cost_cfg)
            else:
                eff_p = p
            qty = target_notional / eff_p
        else:
            qty = f.qty  # sell/trim: share count is fixed by position size
            if cost_cfg is not None:
                eff_p = _effective_price(f.side, p, qty, adv_20, cost_cfg)
            else:
                eff_p = p

        if qty * eff_p < _MIN_FILL_NOTIONAL:
            continue  # hairline rounding fill — skip

        stamped.append(
            Fill(
                isin=f.isin,
                symbol=f.symbol,
                side=f.side,
                qty=qty,
                price=eff_p,
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
    whole_shares: bool = False,
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

    whole_shares: when True, the projection uses the FLOORED sell/trim inflow (because
    apply_fills will only realise whole-share sells/trims, so fewer ₹ arrive than the
    fractional intent) and every buy is floored to whole shares within that budget.
    This makes the proportional allocation across buys whole-share-correct; the exact
    non-negative-cash GUARANTEE is enforced downstream in apply_fills (which caps each
    whole-share buy to the cash actually on hand after sells/trims settle, robust to
    cost non-linearity). Default False ⇒ legacy path, byte-for-byte unchanged.
    """

    def _eff_qty(q: float) -> float:
        return float(math.floor(q)) if whole_shares else q

    projected_cash = available_cash
    total_buy_outflow = 0.0

    for f in fills:
        if f.side in ("sell", "trim"):
            q = _eff_qty(f.qty)  # floored inflow matches what apply_fills realises
            cost = cost_fn(f.side, q, f.price, 0.0, cost_cfg)
            projected_cash += q * f.price - cost
        else:
            q = _eff_qty(f.qty)
            cost = cost_fn("buy", q, f.price, 0.0, cost_cfg)
            total_buy_outflow += q * f.price + cost

    over_budget = total_buy_outflow > 0.0 and total_buy_outflow > projected_cash
    # Fractional fast path: nothing to do unless over budget (preserves parity).
    if not whole_shares and not over_budget:
        return fills

    scale = (projected_cash / total_buy_outflow) if over_budget else 1.0
    if over_budget:
        log.info(
            "Buy outflow %.2f > projected cash %.2f; scaling buys by %.6f to prevent leverage.",
            total_buy_outflow,
            projected_cash,
            scale,
        )
    result: list[Fill] = []
    for f in fills:
        if f.side == "buy":
            qty = f.qty * scale
            if whole_shares:
                qty = float(math.floor(qty))
                if qty <= 0:
                    continue  # sub-1-share after clamp — cannot transact, drop
            result.append(
                Fill(
                    isin=f.isin,
                    symbol=f.symbol,
                    side=f.side,
                    qty=qty,
                    price=f.price,
                    date=f.date,
                    cost_rupees=0.0,
                )
            )
        else:
            result.append(f)
    return result


def _cfg_for_level(level: CostLevel) -> CostConfig:
    """Resolve a CostLevel string to the corresponding CostConfig preset."""
    if level == "optimistic":
        return CostConfig.optimistic()
    if level == "pessimistic":
        return CostConfig.pessimistic()
    return CostConfig.base()


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
