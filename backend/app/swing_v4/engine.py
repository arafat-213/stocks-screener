"""engine.py — the v4 daily event-driven swing engine core (v4/02 §1, §1.1).

The v2 engine proved a single per-day core can drive both the historical backtest
and a future live paper shell byte-for-byte (the `11` probation). v4 reuses that
shape — `build_context()` builds immutable per-run lookups once; `step_day()` is the
one shared per-day core; `run()` loops it over the calendar — so a future v4 forward
probation is faithful by construction (v4/02 §1).

Where v2 is a *monthly* ``for name in top-N`` snapshot, v4 is a *daily* ``while
(trend intact)`` loop **per name** (Rule 13). So v4 cannot be a config of the v2
loop — it needs its own ``step_day``. But the parts that decide *how a queued order
becomes cash and shares* (next-open fill, slippage, whole-share rounding, never spend
cash you don't have) are strategy-agnostic plumbing: v4 **reuses, never edits** the v2
``costs`` model, the ``Portfolio``/``Fill`` accounting, and the ``_stamp_fills`` /
``_clamp_buys_to_cash`` fill mechanics (v4/02 §1, §3, §8 — Arafat-confirmed). Divergence
there is exactly the v1-class fidelity bug we refuse to reintroduce.

`step_day` ordering (v4/02 §1.1 — the hard invariant, mirrors v2 §3 / `11` §3e):
  1. apply prior-session queued fills at today's open (sells/trims before buys)
  2. MTM the book at today's adjusted close
  3. update each open position's trail anchor = max(anchor, adjusted_close[D])
  4. exit checks (catastrophic floor first, then configured exit) → queue SELL D+1 open
  5. compute the regime score for D → deployable fraction f
  6. entry scan (capacity + adv_20 tiebreak) → queue BUY D+1 open
  7. snapshot the day (the MTM snapshot from step 2)

V4.0b builds + unit-tests the engine + fill discipline. It computes **no return
number** — the engine is exercised only on hand-built fixtures (v4/02 §6).
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

# Reuse, never edit, the v2 fill plumbing & accounting (v4/02 §1, §8).
from app.backtest_v2.costs import CostConfig, CostFn, CostLevel
from app.backtest_v2.costs import fill_cost as _default_fill_cost
from app.backtest_v2.engine import (
    _cfg_for_level,
    _clamp_buys_to_cash,
    _stamp_fills,
)
from app.backtest_v2.identity import collapse_to_instrument_id
from app.backtest_v2.portfolio import Portfolio
from app.backtest_v2.schemas import DailySnapshot, Fill
from app.backtest_v2.stable_universe import (
    StableUniverseMask,
    build_stable_universe_mask,
)
from app.swing_v4.config import SwingConfig
from app.swing_v4.regime import RegimeScore
from app.swing_v4.signals import SwingSignalStore, precompute_swing_signals

log = logging.getLogger(__name__)


@dataclass
class SwingEngineResult:
    """All outputs from a completed swing backtest run (V4.0b — no return metric)."""

    snapshots: list[DailySnapshot]
    fills_log: list[Fill]
    config: SwingConfig
    total_cost_paid: float
    # (date, Σ|notional|/equity) per fill-day — the daily-swing analogue of v2's
    # per-rebalance Σ|Δweight|, so metrics.compute_metrics can annualize turnover for
    # the V4.1 cost screen (00 §13). Populated by run(); empty on a no-fill run.
    per_rebalance_turnover: list[tuple[date, float]] = field(default_factory=list)
    # (exit_date D, instrument_id, reason) for every exit queued by step_day — a
    # DIAGNOSTIC side-channel for the V4.1 forensic (00 §6 species: read-only, adds 0 to
    # K, changes NO fill). `reason` ∈ {"catastrophic_floor","atr_trail","macd_cross_down",
    # "ema50_close"}. Recorded on D (decision close); the SELL fills next open. Empty on a
    # no-exit run; never consulted by the locked screen.
    exit_log: list[tuple[date, str, str]] = field(default_factory=list)


@dataclass
class SwingEngineContext:
    """Immutable per-run lookups + collaborators, built once by build_context() and
    consumed by step_day(). Mirrors the v2 EngineContext so a future live shell can
    share the per-day core (v4/02 §1).

    All price lookups are on the **adjusted** series (the swing strategy is defined on
    adjusted O/H/L/C, `00` §3.2). `close` drives both MTM and the close-based exits;
    `open` is the next-session fill price; `adv_20` feeds the cost/slippage model and
    the oversubscription tiebreak.
    """

    config: SwingConfig
    cost_fn: CostFn
    cost_cfg: CostConfig
    close: dict[pd.Timestamp, dict[str, float]]
    open: dict[pd.Timestamp, dict[str, float]]
    adv_20: dict[pd.Timestamp, dict[str, float]]
    sym_map: dict[str, str]
    membership: dict[str, set[pd.Timestamp]]
    signal_store: SwingSignalStore
    regime: RegimeScore
    whole_shares: bool = False
    # Amendment 1 §14 D: the stable_universe membership oracle, AND-ed into the entry
    # scan beneath the retained ₹5cr floor. None when config.universe_mode == "floor"
    # (the legacy ₹5cr-only universe — test/diagnostic escape hatch).
    universe_mask: StableUniverseMask | None = None
    # `04` §3: per-day Nifty 50 trailing `selector_lookback`-td return, the benchmark term
    # the "rs" selector subtracts. Built only when `nifty50_price` is supplied. None for the
    # "adv"/"mom"/"random" selectors (which never read it); "rs" fails loud if it is None.
    nifty_mom: dict[pd.Timestamp, float] | None = None


@dataclass
class SwingLoopState:
    """Mutable loop state carried across days — and persistable the way v2's LoopState
    is, so a future live shell can hydrate it (v4/02 §1).

    The per-name open-position state described in v4/02 §1 (entry date, cost basis,
    trail anchor) is **single-sourced**: entry date + cost basis already live in the
    reused v2 ``Portfolio.positions[id]`` (a frozen ``Position``). The trail anchor —
    ``max adjusted close since entry`` — is the *only* genuinely-new per-name state, so
    it lives here as ``anchors[instrument_id] → float``. Duplicating entry-date/cost-
    basis into a separate ``SwingPosition`` would be a second source of truth that can
    desync from the Portfolio — exactly the fidelity hazard §1 warns against — so we
    keep one source each (surfaced per Rule 12; the §1 ``SwingPosition`` is realised as
    Portfolio.Position + the anchor map).
    """

    portfolio: Portfolio
    pending_fills: list[Fill]
    anchors: dict[str, float] = field(default_factory=dict)
    # DIAGNOSTIC exit-reason side-channel (see SwingEngineResult.exit_log). Appended by
    # step_day when an exit is queued; carried on state so a future live shell records it
    # too. Default-empty ⇒ no behavioural change to any run.
    exit_log: list[tuple[date, str, str]] = field(default_factory=list)


def run(
    prices: pd.DataFrame,
    config: SwingConfig,
    *,
    nifty50_price: pd.Series | None = None,
    market_internals: pd.DataFrame | None = None,
    regime: RegimeScore | None = None,
    cost_fn: CostFn = _default_fill_cost,
    cost_cfg: CostConfig | None = None,
    cost_level: CostLevel | None = None,
    signal_store: SwingSignalStore | None = None,
    whole_shares: bool = False,
) -> SwingEngineResult:
    """Execute the v4 swing loop over `prices` and return a SwingEngineResult.

    Parameters
    ----------
    prices : pd.DataFrame
        Long-format multi-ISIN adjusted frame from store.read_prices_adjusted.
        Required columns: isin, date, open, high, low, close, adv_20 (and, post-06,
        instrument_id). `close` is the adjusted close (MTM + exit anchor).
    config : SwingConfig
        Frozen `00` strategy params + grid knobs. `config.target_positions` is the
        binding concentration cap (00 §14); the engine fails loud on ≤ 0 (Rule 12).
    nifty50_price, market_internals : injected regime inputs (fixtures in tests). Used
        only when `regime` is not pre-built. No live API in pytest (`00` §4 / v4/02 §3).
    regime : pre-built RegimeScore; if None, built from nifty50_price + market_internals.
    signal_store : pre-built SwingSignalStore; if None, precompute_swing_signals is run.
    whole_shares : NSE integer-share fidelity (default False ⇒ fractional). A future
        live shell sets it True (mirrors v2 `11` §13).
    """
    ctx, calendar = build_context(
        prices,
        config,
        nifty50_price=nifty50_price,
        market_internals=market_internals,
        regime=regime,
        cost_fn=cost_fn,
        cost_cfg=cost_cfg,
        cost_level=cost_level,
        signal_store=signal_store,
        whole_shares=whole_shares,
    )

    state = SwingLoopState(
        portfolio=Portfolio(cash=config.starting_capital),
        pending_fills=[],
        anchors={},
    )

    for day in calendar:
        step_day(ctx, state, day)

    return SwingEngineResult(
        snapshots=state.portfolio.snapshots,
        fills_log=state.portfolio.fills_log,
        config=config,
        total_cost_paid=state.portfolio._total_cost_paid,
        per_rebalance_turnover=_daily_turnover(
            state.portfolio.fills_log, state.portfolio.snapshots
        ),
        exit_log=state.exit_log,
    )


def _daily_turnover(
    fills: list[Fill], snapshots: list[DailySnapshot]
) -> list[tuple[date, float]]:
    """Per-fill-day turnover = Σ|qty×price| / that-day equity (the daily-swing analogue
    of v2's per-rebalance Σ|Δweight|; 00 §13 "record turnover"). Buys and sells both
    count as |Δweight|; metrics._compute_annualized_turnover sums then annualizes. Equity
    is the day's MTM snapshot equity (post-fill, the standard weight base)."""
    if not fills or not snapshots:
        return []
    equity_by_day: dict[date, float] = {s.date: s.equity for s in snapshots}
    notional_by_day: dict[date, float] = {}
    for f in fills:
        notional_by_day[f.date] = notional_by_day.get(f.date, 0.0) + abs(
            f.qty * f.price
        )
    out: list[tuple[date, float]] = []
    for d in sorted(notional_by_day):
        eq = equity_by_day.get(d, 0.0)
        if eq > 0:
            out.append((d, notional_by_day[d] / eq))
    return out


def build_context(
    prices: pd.DataFrame,
    config: SwingConfig,
    *,
    nifty50_price: pd.Series | None = None,
    market_internals: pd.DataFrame | None = None,
    regime: RegimeScore | None = None,
    cost_fn: CostFn = _default_fill_cost,
    cost_cfg: CostConfig | None = None,
    cost_level: CostLevel | None = None,
    signal_store: SwingSignalStore | None = None,
    whole_shares: bool = False,
) -> tuple[SwingEngineContext, list[pd.Timestamp]]:
    """Build the immutable per-run lookups + trading calendar shared by run() and a
    future live shell (v4/02 §1). Extracted so the live shell drives the SAME step_day
    over the SAME context — fidelity by construction, not re-implementation.
    """
    if config.target_positions <= 0:
        raise ValueError(
            f"SwingConfig.target_positions must be > 0 (the binding concentration cap "
            f"= slot cap AND sizing divisor, 00 §14 A/B); got {config.target_positions}."
        )

    if cost_level is not None:
        cost_cfg = _cfg_for_level(cost_level)
    elif cost_cfg is None:
        cost_cfg = CostConfig()

    # Resolve identity to the chain-constant instrument_id (06) FIRST so price lookups,
    # universe membership, and held positions all key on instrument_id: a position held
    # across a succession resolves to the same key (no ghost), and per-date lookups
    # resolve to whichever leg is live (v4/02 §5 item 10). No-op for non-succession
    # frames. The signal store collapses internally too (idempotent).
    prices = collapse_to_instrument_id(prices)
    prices = prices.copy()
    prices["date"] = pd.to_datetime(prices["date"])

    _close = _pivot(prices, "close")
    _open = _pivot(prices, "open")
    _adv_20 = _pivot(prices, "adv_20")

    _sym_col = "symbol" if "symbol" in prices.columns else "isin"
    _sym_map: dict[str, str] = (
        prices.sort_values("date")
        .drop_duplicates("isin", keep="last")
        .set_index("isin")[_sym_col]
        .to_dict()
    )

    calendar: list[pd.Timestamp] = sorted(_close.keys())
    if not calendar:
        raise ValueError("prices DataFrame has no valid dates.")
    start_ts = pd.Timestamp(config.date_from) if config.date_from else calendar[0]
    end_ts = pd.Timestamp(config.date_to) if config.date_to else calendar[-1]
    calendar = [d for d in calendar if start_ts <= d <= end_ts]
    if not calendar:
        raise ValueError(f"No trading dates in [{config.date_from}, {config.date_to}].")

    if signal_store is None:
        signal_store = precompute_swing_signals(prices, config)

    if regime is None:
        if nifty50_price is None or market_internals is None:
            raise ValueError(
                "build_context needs either a pre-built `regime` or both "
                "`nifty50_price` and `market_internals` to build one (v4/02 §3)."
            )
        regime = RegimeScore(nifty50_price, market_internals, config)

    _membership: dict[str, set[pd.Timestamp]] = {}
    for isin, group in prices.groupby("isin"):
        _membership[str(isin)] = set(pd.to_datetime(group["date"]))

    # Amendment 1 §14 D: build the stable_universe mask (top-U by 126-td median adv_20,
    # semi-annual review + hysteresis, no-lookahead) and AND it into the entry scan.
    # "floor" mode keeps the legacy ₹5cr-only universe (escape hatch for tiny fixtures /
    # diagnostics). Reuses v3 08's build_stable_universe_mask UNMODIFIED (additive, §8).
    universe_mask: StableUniverseMask | None = None
    if config.universe_mode == "stable":
        universe_mask = build_stable_universe_mask(
            prices,
            config.universe_size_U,
            config.universe_buffer_B,
            config.universe_rank_lookback_td,
            config.universe_review_cadence,
        )

    # `04` §3: the "rs" selector needs the Nifty 50 trailing return per day. Build it
    # only when the caller supplies `nifty50_price` (the cost screen passes it for "rs"
    # runs); leave None otherwise — "adv"/"mom"/"random" never read it.
    nifty_mom: dict[pd.Timestamp, float] | None = None
    if nifty50_price is not None:
        nifty_mom = _nifty_trailing_return(
            nifty50_price, calendar, config.selector_lookback
        )

    ctx = SwingEngineContext(
        config=config,
        cost_fn=cost_fn,
        cost_cfg=cost_cfg,
        close=_close,
        open=_open,
        adv_20=_adv_20,
        sym_map=_sym_map,
        membership=_membership,
        signal_store=signal_store,
        regime=regime,
        whole_shares=whole_shares,
        universe_mask=universe_mask,
        nifty_mom=nifty_mom,
    )
    return ctx, calendar


def _nifty_trailing_return(
    nifty50_price: pd.Series, calendar: list[pd.Timestamp], lookback: int
) -> dict[pd.Timestamp, float]:
    """Per-day Nifty 50 trailing `lookback`-td total return for the "rs" selector (04 §3).

    Computed on the index's FULL history (so the lookback can reach back across the window
    edge), then as-of (ffill) mapped onto the run calendar — causal, no in-progress bar.
    Returned as {date → return}, NaN days dropped (the selector guards a missing entry to 0,
    which — since the term is constant across the cross-section — leaves the rank unchanged).
    """
    full = nifty50_price.sort_index()
    r_full = full / full.shift(lookback) - 1.0
    r_cal = r_full.reindex(pd.DatetimeIndex(calendar), method="ffill")
    return {ts: float(v) for ts, v in r_cal.items() if pd.notna(v)}


def step_day(ctx: SwingEngineContext, state: SwingLoopState, day: pd.Timestamp) -> None:
    """Execute ONE trading day of the v4 swing loop (v4/02 §1.1) against mutable
    `state` using immutable `ctx`. This is the one per-day core a future live shell
    will call (the same `11` §3e fidelity contract).

    HARD ORDERING INVARIANT: apply prior queued fills (step 1) ALWAYS runs BEFORE the
    exit checks (step 4), so a name bought at today's open — its cost basis set in
    step 1 — is exit-eligible on TODAY's close (no skipped first-day stop; §5 item 9).
    """
    pf = state.portfolio
    day_date = day.date()
    close_today: dict[str, float] = ctx.close.get(day, {})

    # ---- step 1: apply prior-session queued fills at today's open ----------
    if state.pending_fills:
        open_today = ctx.open.get(day, {})
        adv_today = ctx.adv_20.get(day, {})
        # Sells/trims before buys so exits replenish cash before new buys.
        _side_order = {"sell": 0, "trim": 1, "buy": 2}
        state.pending_fills.sort(key=lambda f: _side_order.get(f.side, 9))
        stamped = _stamp_fills(
            state.pending_fills, open_today, day_date, adv_today, ctx.cost_cfg
        )
        stamped = _clamp_buys_to_cash(
            stamped, pf.cash, ctx.cost_fn, ctx.cost_cfg, whole_shares=ctx.whole_shares
        )
        pf.apply_fills(
            stamped,
            cost_fn=ctx.cost_fn,
            cost_cfg=ctx.cost_cfg,
            adv_lookup=adv_today,
            whole_shares=ctx.whole_shares,
        )
        state.pending_fills = []
        # Drop the trail anchor of any position fully exited at this open.
        for iid in list(state.anchors):
            if iid not in pf.positions:
                del state.anchors[iid]

    # ---- step 2: MTM the book at today's adjusted close --------------------
    pf.mark_to_market(day_date, close_today)

    # ---- step 3: update each open position's trail anchor ------------------
    # anchor = max adjusted close since entry. A newly opened position has no anchor
    # yet ⇒ it is seeded with today's close (the first close observed since entry), so
    # the anchor is a high-water mark of CLOSES only (never the entry open / intraday
    # high — the v1 trailing-stop-uses-bar-high sin is excluded, v4/02 §2/§5 item 3).
    for iid in pf.positions:
        c = close_today.get(iid)
        if c is None:
            continue
        prev = state.anchors.get(iid)
        state.anchors[iid] = c if prev is None else max(prev, c)

    # ---- step 4: exit checks (floor first, then configured) → queue SELL ----
    for iid, pos in list(pf.positions.items()):
        c = close_today.get(iid)
        if c is None:
            continue  # no close today (gap/halt) — carry the position
        reason = _exit_reason(ctx, state, iid, pos, c, day)
        if reason:
            state.exit_log.append((day_date, iid, reason))  # diagnostic side-channel
            state.pending_fills.append(
                Fill(
                    isin=iid,
                    symbol=pos.symbol,
                    side="sell",
                    qty=pos.shares,
                    price=pos.last_price,  # placeholder; stamped to next open
                    date=day_date,
                    cost_rupees=0.0,
                )
            )

    # ---- step 5: regime deployable fraction for today ----------------------
    f = ctx.regime.deployable_fraction(day)

    # ---- step 6: entry scan (D close → queue BUY D+1 open) -----------------
    _scan_entries(ctx, state, day, day_date, f, close_today)

    # ---- step 7: snapshot --------------------------------------------------
    # The MTM call in step 2 already appended the day's DailySnapshot (NAV / cash /
    # positions / exposure); the per-name anchors live in `state` (persistable).


def _exit_breach(
    ctx: SwingEngineContext,
    state: SwingLoopState,
    iid: str,
    pos,
    close_today: float,
    day: pd.Timestamp,
) -> bool:
    """True iff `pos` should exit on D's close (catastrophic floor first, then the
    configured exit). Close-based only — fills next open (v4/02 §1.1 step 4).

    Thin bool wrapper over `_exit_reason` (the predicate the engine and tests use); the
    reason string it discards is what the V4.1 forensic exit_log records."""
    return _exit_reason(ctx, state, iid, pos, close_today, day) is not None


def _exit_reason(
    ctx: SwingEngineContext,
    state: SwingLoopState,
    iid: str,
    pos,
    close_today: float,
    day: pd.Timestamp,
) -> str | None:
    """The exit decision AND which rule fired, or None to hold. Same logic as the old
    `_exit_breach` predicate — only the return is enriched from bool→reason so the
    forensic can attribute exits (00 §6 diagnostic). Behaviour is byte-identical: every
    branch that returned True now returns a reason string (truthy), every False→None."""
    cfg = ctx.config

    # Catastrophic floor (close-breach circuit breaker beneath the configured exit).
    # Guarded by pct > 0 (mirrors v2 engine): pct == 0 DISABLES the floor — without
    # this guard a 0% floor would degenerate to "exit on any close below cost basis".
    if cfg.catastrophic_stop_pct > 0:
        floor_level = pos.cost_basis * (1.0 - cfg.catastrophic_stop_pct / 100.0)
        if close_today < floor_level:
            log.info(
                "v4 catastrophic floor: %s close=%.4f < floor=%.4f on %s",
                iid,
                close_today,
                floor_level,
                day.date(),
            )
            return "catastrophic_floor"

    if cfg.exit_type == 3:
        # Type 3 (candidate): close < anchor − atr_mult × ATR20[D] (stateful trail).
        anchor = state.anchors.get(iid)
        row = ctx.signal_store.row(day, iid)
        if anchor is None or row is None:
            return None
        atr = row["atr20"]
        if atr is None or (isinstance(atr, float) and math.isnan(atr)):
            return None
        return "atr_trail" if close_today < anchor - cfg.atr_mult * float(atr) else None

    if cfg.exit_type == 1:
        # Type 1 (comparator): opposite daily MACD crossover on D.
        row = ctx.signal_store.row(day, iid)
        if row is not None and bool(row["exit_macd_cross_down"]):
            return "macd_cross_down"
        return None

    if cfg.exit_type == 2:
        # Type 2 (comparator): close < EMA50.
        row = ctx.signal_store.row(day, iid)
        if row is None:
            return None
        ema = row["ema_exit"]
        if ema is None or (isinstance(ema, float) and math.isnan(ema)):
            return None
        return "ema50_close" if close_today < float(ema) else None

    raise ValueError(f"unknown exit_type: {cfg.exit_type!r} (known: 1, 2, 3)")


def _scan_entries(
    ctx: SwingEngineContext,
    state: SwingLoopState,
    day: pd.Timestamp,
    day_date: date,
    f: float,
    close_today: dict[str, float],
) -> None:
    """Queue BUY orders for D+1 open while capacity allows (v4/02 §1.1 step 6).

    Capacity: open positions + already-queued buys < `target_positions` AND projected
    gross < f × equity. Per-name target notional = f × equity / `target_positions`
    (equal-weight). `target_positions` is the binding concentration cap (00 §14 A/B).

    Selector: when more candidates fire than there are free slots, `_order_candidates`
    ranks them by `config.selector` and we fill best-first until the slot/gross cap binds.
    "adv" (00 §14 C, the V4.1 candidate) keeps the most-liquid; "mom"/"rs" (`04`) keep the
    strongest-trend; "random" is the `00` §6 diagnostic book.
    """
    cfg = ctx.config
    target_positions = cfg.target_positions
    if f <= 0.0:
        return  # bear regime — no new deployment (throttle blocks entries; no forced
        #          liquidation of existing names, v4/02 §0 / §1.1 step 4)

    pf = state.portfolio
    held = set(pf.positions)
    queued_buys = {fl.isin for fl in state.pending_fills if fl.side == "buy"}
    slots = target_positions - len(held) - len(queued_buys)
    if slots <= 0:
        return

    # "capital" = current equity (the standard compounding portfolio interpretation,
    # matching v2 build_rebalance_plan's `current_equity = portfolio.equity`). Surfaced
    # per Rule 12: `00` §3.5 writes "f × capital"; equity is the operative reading.
    equity = pf.equity
    target_gross = f * equity
    per_name = target_gross / target_positions if target_positions > 0 else 0.0
    if per_name <= 0.0:
        return

    projected_gross = sum(p.shares * p.last_price for p in pf.positions.values()) + sum(
        fl.qty * fl.price for fl in state.pending_fills if fl.side == "buy"
    )

    # Candidate entrants: 4 frozen conditions true on D, liquid (₹5cr floor, inside
    # entry_signal), in the stable_universe (00 §14 D), traded D, not held, not already
    # queued. Gather (iid, adv_20, mom) then order by the configured selector below.
    candidates: list[tuple[str, float, float | None]] = []
    for iid, dates in ctx.membership.items():
        if day not in dates or iid in held or iid in queued_buys:
            continue
        if ctx.universe_mask is not None and not ctx.universe_mask.is_member(day, iid):
            continue
        if not ctx.signal_store.entry_signal(day, iid):
            continue
        row = ctx.signal_store.row(day, iid)
        adv = float(row["adv_20"]) if row is not None else 0.0
        mom = None
        if row is not None and "mom" in row:
            mv = row["mom"]
            mom = float(mv) if not (isinstance(mv, float) and math.isnan(mv)) else None
        candidates.append((iid, adv, mom))
    _order_candidates(ctx, candidates, day)

    _EPS = 1e-9
    for iid, _adv, _mom in candidates:
        if slots <= 0:
            break
        if projected_gross >= target_gross - _EPS:
            break  # gross cap reached (gross ≤ f × capital, `00` §3.5)
        price = close_today.get(iid)
        if price is None or price <= 0.0:
            continue
        qty = per_name / price  # decision-close sizing; restamped to open in step 1
        if qty <= 0.0:
            continue
        state.pending_fills.append(
            Fill(
                isin=iid,
                symbol=ctx.sym_map.get(iid, iid),
                side="buy",
                qty=qty,
                price=price,
                date=day_date,
                cost_rupees=0.0,
            )
        )
        projected_gross += per_name
        slots -= 1


def _order_candidates(
    ctx: SwingEngineContext,
    candidates: list[tuple[str, float, float | None]],
    day: pd.Timestamp,
) -> None:
    """Order the firing candidates IN PLACE by the configured selector (best first).

    - "adv"    (V4.1 candidate, 00 §14 C): adv_20 desc (most liquid first).
    - "random" (00 §6 B_random diagnostic): seeded per-day shuffle — independent each day
      yet reproducible across seeds (median/p5-over-seeds).
    - "mom"    (04 candidate): trailing-return rank desc; a name without a full lookback
      (mom is None) sorts LAST; ties break on adv_20 desc (the frozen neutral tiebreak).
    - "rs"     (04 comparator): mom MINUS the per-day Nifty 50 trailing return. That term is
      one constant across the whole cross-section, so it cannot change the order — "rs" is
      identical to "mom" as a selector (04 §3). Implemented faithfully (subtraction +
      fail-loud on a missing nifty_mom) so the screen *demonstrates* the identity.
    """
    cfg = ctx.config
    sel = cfg.selector
    if sel == "adv":
        candidates.sort(key=lambda t: t[1], reverse=True)
        return
    if sel == "random":
        rng = random.Random(cfg.selector_seed * 1_000_003 + day.toordinal())
        rng.shuffle(candidates)
        return
    if sel in ("mom", "rs"):
        shift = 0.0
        if sel == "rs":
            if ctx.nifty_mom is None:
                raise ValueError(
                    "selector='rs' needs the Nifty 50 trailing return — pass "
                    "`nifty50_price` to build_context/run (04 §3)."
                )
            s = ctx.nifty_mom.get(day)
            shift = s if (s is not None and not math.isnan(s)) else 0.0

        def _key(t: tuple[str, float, float | None]):
            _iid, adv, mom = t
            has = mom is not None
            rank = (mom - shift) if has else float("-inf")
            return (has, rank, adv)  # has-mom first; rank desc; adv_20 desc tiebreak

        candidates.sort(key=_key, reverse=True)
        return
    raise ValueError(f"unknown selector: {sel!r} (known: adv, random, mom, rs)")


def _pivot(prices: pd.DataFrame, col: str) -> dict[pd.Timestamp, dict[str, float]]:
    """Build {date → {isin → value}} from the long-format prices frame (NaN dropped).

    Identical shape to v2 engine._pivot; kept local so swing_v4 does not depend on a
    v2 private helper that could change for v2's own reasons (v4/02 §8 additive-only).
    """
    result: dict[pd.Timestamp, dict[str, float]] = {}
    sub = prices[["date", "isin", col]].dropna(subset=[col])
    for row in sub.itertuples(index=False):
        ts = pd.Timestamp(row.date)
        result.setdefault(ts, {})[str(row.isin)] = float(getattr(row, col))
    return result
