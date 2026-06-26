"""overlay.py — the v5/00 Direction-D one-instrument regime-overlay simulator.

Holds **Nifty 50 TRI** at a regime-throttled deploy fraction ``f ∈ {0, 0.5, 1.0}``
(the frozen v4 5-factor score) and parks the rest ``(1 − f)`` in a **real-short-rate
defensive leg** (Nifty 1D Rate Index). It is a *pure* close-to-close NAV simulator —
no DB, no engine, no network — so RO1/RO2 only have to wire real series into it.

Causality (v5/00 §3): the score on completed day ``D`` trades at ``D+1`` open. In the
close-to-close model each day ``t`` rebalances at the open using the **fraction from the
prior close** ``f[t-1]`` (never ``f[t]``), then accrues that day's market move + costs.
Day 0 starts fully in the defensive leg (no signal yet) — no look-ahead.

Costs (v5/00 §3a):
  * **Switch cost** on each rebalance = the project ``costs.fill_cost`` (statutory STT/
    exchange/SEBI/stamp/GST/DP) **plus** ``base_slippage_pct`` on the traded ETF notional
    ``|Δequity|`` (an index ETF has ~0 participation ⇒ only the slippage floor). Charged
    on the equity leg only — debt/overnight funds carry no STT. Base + pessimistic via
    ``CostConfig``.
  * **Holding cost** accrues daily: an ETF expense on the *equity* value and a liquid-fund
    expense on the *defensive* value (we cost our own vehicles, v3/10 §2c).

Comparators (same module, v5/00 §5): the **static exposure-matched mix** (constant
``w*`` rebalanced monthly — the BINDING bar), **buy-and-hold** full TRI, the
**Faber-200DMA** timer, and the **linear-ramp** (``score/5``) diagnostic. All are the
same ``simulate`` call with a different fraction path / rebalance mode.

Nothing here measures DISCOVERY/FINAL_OOS — that is RO1/RO2. This module is the engine
+ its synthetic tests only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.backtest_v2.costs import CostConfig, fill_cost
from app.backtest_v2.metrics import _cagr_from_equity, _compute_max_drawdown
from app.swing_v4.indicators import sma
from app.swing_v4.regime import RegimeScore

_TRADING_DAYS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Config + result containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OverlayConfig:
    """Non-signal mechanics for the overlay (v5/00 §3 / §3a). No free strategy knob."""

    starting_capital: float = 350_000.0  # v5/00 §3 — Arafat's real spare capital
    etf_expense_annual: float = 0.0005  # ~0.05%/yr Nifty 50 ETF expense ratio
    liquid_expense_annual: float = 0.0020  # ~0.20%/yr liquid/overnight fund expense
    trading_days_per_year: int = _TRADING_DAYS_PER_YEAR


@dataclass(frozen=True)
class OverlaySimResult:
    """Output of one ``simulate`` run."""

    nav: pd.Series  # DatetimeIndex → ₹ NAV at each close
    applied_fraction: (
        pd.Series
    )  # DatetimeIndex → deployed equity fraction in force that day
    realized_avg_fraction: (
        float  # w* — mean applied fraction (an OUTPUT; adds 0 to K, §5a)
    )
    n_rebalances: int  # how many days a trade actually fired
    total_switch_cost: float  # ₹ total statutory+slippage paid switching


# ---------------------------------------------------------------------------
# Fraction-path builders (the "signal", reused verbatim — §3/§4)
# ---------------------------------------------------------------------------


def overlay_fraction(regime: RegimeScore, calendar: list[pd.Timestamp]) -> pd.Series:
    """The candidate path: frozen 3-bucket f ∈ {0, 0.5, 1.0} per trading day (§3)."""
    return pd.Series(
        [regime.deployable_fraction(d) for d in calendar],
        index=pd.DatetimeIndex(calendar),
        name="overlay_fraction",
    )


def linear_ramp_fraction(
    regime: RegimeScore, calendar: list[pd.Timestamp]
) -> pd.Series:
    """DIAGNOSTIC path (§6): ``f = score/5`` on the SAME frozen integer score."""
    return pd.Series(
        [regime.score(d) / 5.0 for d in calendar],
        index=pd.DatetimeIndex(calendar),
        name="linear_ramp_fraction",
    )


def faber_fraction(
    price: pd.Series, calendar: list[pd.Timestamp], window: int = 200
) -> pd.Series:
    """DIAGNOSTIC path (§5b): textbook Faber timer — 1.0 if close > N-DMA else 0.0.

    The N-DMA is trailing (``min_periods = window``); during warmup (NaN DMA) the
    comparison is False ⇒ fraction 0.0 (conservative, no look-ahead). Aligned onto the
    overlay calendar as-of (last index value ≤ day), matching ``regime.py`` convention.
    """
    cal = pd.DatetimeIndex(calendar)
    dma = sma(price.sort_index(), window)
    a_price = price.sort_index().reindex(cal, method="ffill")
    a_dma = dma.reindex(cal, method="ffill")
    frac = (a_price > a_dma).fillna(False).astype(float)
    frac.name = "faber_fraction"
    return frac


def static_fraction(w_star: float, calendar: list[pd.Timestamp]) -> pd.Series:
    """Constant ``w*`` path for the static exposure-matched mix (§5a)."""
    return pd.Series(
        float(w_star), index=pd.DatetimeIndex(calendar), name="static_fraction"
    )


# ---------------------------------------------------------------------------
# Switch cost (equity leg only — §3a)
# ---------------------------------------------------------------------------


def _switch_cost(notional: float, side: str, cfg: CostConfig) -> float:
    """₹ cost to trade ``notional`` of the index ETF: statutory + slippage floor.

    ``fill_cost`` gives statutory (STT/exchange/SEBI/stamp/GST/DP). Slippage is the
    ETF's ``base_slippage_pct`` floor (index ETF ⇒ participation ≈ 0, so the
    impact term vanishes). The defensive (overnight) leg carries no STT ⇒ free.
    """
    if notional <= 0.0:
        return 0.0
    statutory = fill_cost(side, notional, 1.0, 0.0, cfg)  # qty*price = notional
    slippage = notional * cfg.base_slippage_pct
    return statutory + slippage


# ---------------------------------------------------------------------------
# The simulator
# ---------------------------------------------------------------------------


def simulate(
    fraction: pd.Series,
    tri: pd.Series,
    defensive: pd.Series,
    cost_cfg: CostConfig,
    overlay_cfg: OverlayConfig = OverlayConfig(),
    rebalance: str = "on_change",
) -> OverlaySimResult:
    """Close-to-close NAV simulation of a throttled index/defensive sleeve.

    Args:
        fraction: DatetimeIndex → target equity fraction known at that day's CLOSE
            (the signal; lagged one day inside the loop for causality).
        tri: equity-leg level series (Nifty 50 TRI).
        defensive: defensive-leg level series (Nifty 1D Rate Index).
        cost_cfg: ``CostConfig.base()`` / ``.pessimistic()`` (switch + slippage).
        overlay_cfg: capital + expense mechanics.
        rebalance: ``"on_change"`` (overlay/Faber/linear/B&H — trade only when the
            target moves) or ``"monthly"`` (static mix — reset to a constant ``w*``
            on the first signal day and at each new calendar month).

    Returns:
        OverlaySimResult (NAV, applied-fraction path, ``w*``, flip count, switch ₹).

    The calendar is the intersection of all three series' dates (sorted). Day 0 sits
    100% in the defensive leg (no prior signal); the first deploy fires on day 1.
    """
    if rebalance not in ("on_change", "monthly"):
        raise ValueError(
            f"rebalance must be 'on_change' or 'monthly', got {rebalance!r}"
        )

    # The equity (TRI) calendar over the fraction's span is AUTHORITATIVE — that is
    # where decisions and trades happen. TRI + fraction must cover every day exactly
    # (fail loud on a hole). The defensive overnight index publishes on a slightly
    # sparser calendar, so it is as-of ffilled onto the trading calendar (a non-publish
    # day simply carries the level forward — 0 accrual that day, like align_benchmark).
    cal = pd.DatetimeIndex(fraction.index).intersection(tri.index).sort_values()
    if len(cal) < 2:
        raise ValueError(
            "simulate: need ≥2 overlapping dates between fraction and TRI."
        )

    tri_v = tri.reindex(cal).astype(float)
    frac_v = fraction.reindex(cal).astype(float)
    def_v = (
        defensive.reindex(pd.DatetimeIndex(cal).union(defensive.index))
        .ffill()
        .reindex(cal)
        .astype(float)
    )
    if tri_v.isna().any() or frac_v.isna().any() or def_v.isna().any():
        raise ValueError(
            "simulate: NaN on the trading calendar after alignment — TRI/fraction hole "
            "or defensive series starts after the window (fail loud, v5/00 RO0)."
        )

    etf_daily = overlay_cfg.etf_expense_annual / overlay_cfg.trading_days_per_year
    liq_daily = overlay_cfg.liquid_expense_annual / overlay_cfg.trading_days_per_year

    equity = 0.0
    cash = float(overlay_cfg.starting_capital)
    applied_w = 0.0
    last_rebal_month: tuple[int, int] | None = None

    navs: list[float] = []
    applied: list[float] = []
    total_switch = 0.0
    n_rebal = 0

    for i, day in enumerate(cal):
        if i == 0:
            navs.append(equity + cash)
            applied.append(applied_w)
            continue

        prev = cal[i - 1]

        # --- 1. rebalance at the open using the PRIOR close's signal (causal) ---
        if rebalance == "on_change":
            target = float(frac_v.loc[prev])
            do = target != applied_w
        else:  # monthly static mix: constant target, reset on first day + month turn
            target = float(frac_v.loc[prev])
            ym = (day.year, day.month)
            do = (last_rebal_month is None) or (ym != last_rebal_month)

        if do:
            nav_open = equity + cash
            delta = target * nav_open - equity  # traded ETF notional (signed)
            if abs(delta) > 0.0:
                side = "buy" if delta > 0 else "sell"
                cost = _switch_cost(abs(delta), side, cost_cfg)
                # Cost is a real outflow ⇒ it reduces NAV; then split to the target
                # fraction (keeps cash ≥ 0 even at a 100% deploy — the cost comes out
                # of the rebalanced sleeve, not a phantom negative-cash overdraft).
                nav_after = nav_open - cost
                equity = target * nav_after
                cash = (1.0 - target) * nav_after
                total_switch += cost
                n_rebal += 1
            applied_w = target
            if rebalance == "monthly":
                last_rebal_month = (day.year, day.month)

        # --- 2. intraday market growth + daily holding cost ---
        equity *= float(tri_v.loc[day]) / float(tri_v.loc[prev]) * (1.0 - etf_daily)
        cash *= float(def_v.loc[day]) / float(def_v.loc[prev]) * (1.0 - liq_daily)

        navs.append(equity + cash)
        applied.append(applied_w)

    nav_s = pd.Series(navs, index=cal, name="nav")
    applied_s = pd.Series(applied, index=cal, name="applied_fraction")
    # w* = realised average daily deployed fraction (an OUTPUT; adds 0 to K, §5a/§7).
    w_star = float(applied_s.mean())
    return OverlaySimResult(
        nav=nav_s,
        applied_fraction=applied_s,
        realized_avg_fraction=w_star,
        n_rebalances=n_rebal,
        total_switch_cost=total_switch,
    )


# ---------------------------------------------------------------------------
# NAV → headline metrics (reuse the project's drawdown/CAGR helpers)
# ---------------------------------------------------------------------------


def metrics_from_nav(nav: pd.Series) -> dict[str, float]:
    """Calmar / maxDD / CAGR / annualised Sharpe from a NAV series (v5/00 §5c)."""
    nav = nav.dropna()
    cagr = _cagr_from_equity(nav)
    max_dd, dd_days = _compute_max_drawdown(
        nav.to_numpy(dtype=float), [ts.date() for ts in nav.index]
    )
    calmar = cagr / max_dd if max_dd > 0 else float("nan")
    rets = nav.pct_change().dropna()
    if len(rets) > 1 and float(rets.std(ddof=1)) > 0:
        sharpe = float(rets.mean() / rets.std(ddof=1)) * np.sqrt(_TRADING_DAYS_PER_YEAR)
    else:
        sharpe = float("nan")
    return {
        "cagr": cagr,
        "max_dd": max_dd,
        "max_dd_days": float(dd_days),
        "calmar": calmar,
        "sharpe": sharpe,
    }
