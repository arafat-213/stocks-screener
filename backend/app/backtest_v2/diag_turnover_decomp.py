"""
diag_turnover_decomp.py — READ-ONLY turnover decomposition for the T3 candidate.

Question (Arafat, 2026-06-16): the candidate runs ~934% annualized turnover on
DISCOVERY. How much of that is the monthly equal-weight RESET vs membership churn
vs the regime overlay toggling the whole book in/out?

This changes NO parameter and spends NO OOS budget. It is a measurement only,
to inform v3 turnover design. It does not re-run T4 and does not touch FINAL_OOS.

Method
------
Turnover is reported by the engine as Σ|Δweight| per monthly rebalance, summed
and annualized (metrics._compute_annualized_turnover). The regime overlay acts
ONLY at month-end rebalances (it sets deployable_fraction, which build_rebalance_plan
sizes against), so all three turnover sources land in the same Σ|Δw| number:

  1. REGIME      — book scaled in/out as deployable_fraction changes month-to-month.
  2. CHURN       — names entering / exiting the top-N (membership rotation).
  3. WEIGHT-RESET— trims / top-ups on RETAINED names to restore equal weight.

Isolation:
  * REGIME bucket via counterfactual: T_candidate (regime ON) − T_noregime
    (same config, use_regime_overlay=False). The difference is what the regime adds.
  * CHURN vs WEIGHT-RESET: classify the no-regime run's executed fills
    (entry/exit = churn; trim/top-up on a held name = reset), weighted by Δweight,
    then apply those proportions to the authoritative T_noregime magnitude.

Run:
    backend/venv/bin/python -m app.backtest_v2.diag_turnover_decomp
"""

from __future__ import annotations

import dataclasses
import logging
import sys
from datetime import date
from itertools import groupby

import pandas as pd

from app.backtest_v2 import benchmark, engine, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.regime import RegimeConfig, RegimeOverlay
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.validation import DISCOVERY
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

# Same candidate + bench cache keys as robustness.py (offline run).
CANDIDATE_REGIME = RegimeConfig(debounce_days=1, risk_off_floor=0.25)
_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)
_EPS = 1e-9


def _decompose_fills(result: engine.EngineResult) -> dict[str, float]:
    """
    Classify executed fills of a run into entry / exit / reweight buckets,
    weighted by Δweight = (qty × price) / equity_on_fill_date.

    entry   = buy of a name not held at the start of that day  (churn, in)
    exit    = full-position sell                                 (churn, out)
    reweight= trim, or buy top-up of a name already held         (weight-reset)

    Returns {"entry", "exit", "reweight", "total"} in Σ|Δw| units (two-way).
    """
    equity_by_date = {s.date: s.equity for s in result.snapshots}
    fills = sorted(result.fills_log, key=lambda f: f.date)
    holdings: dict[str, float] = {}
    buckets = {"entry": 0.0, "exit": 0.0, "reweight": 0.0}

    for d, day_group in groupby(fills, key=lambda f: f.date):
        day_fills = list(day_group)
        held_at_start = {isin for isin, sh in holdings.items() if sh > _EPS}
        eq = equity_by_date.get(d)
        if eq is None or eq <= 0:
            continue  # no equity reference; skip (should not happen on rebalance days)
        for f in day_fills:
            dw = (f.qty * f.price) / eq
            if f.side == "sell":
                buckets["exit"] += dw
                holdings[f.isin] = 0.0
            elif f.side == "trim":
                buckets["reweight"] += dw
                holdings[f.isin] = max(0.0, holdings.get(f.isin, 0.0) - f.qty)
            else:  # buy
                if f.isin in held_at_start:
                    buckets["reweight"] += dw
                else:
                    buckets["entry"] += dw
                holdings[f.isin] = holdings.get(f.isin, 0.0) + f.qty

    buckets["total"] = buckets["entry"] + buckets["exit"] + buckets["reweight"]
    return buckets


def _regime_profile(index_prices: pd.Series, reb_dates: list[date]) -> dict:
    """Characterize the regime overlay: daily whipsaw + month-end toggles."""
    overlay = RegimeOverlay(index_prices, cfg=CANDIDATE_REGIME)

    # Daily whipsaw over the DISCOVERY window.
    in_window = index_prices.index[
        (index_prices.index >= pd.Timestamp(DISCOVERY[0]))
        & (index_prices.index <= pd.Timestamp(DISCOVERY[1]))
    ]
    daily = [overlay.deployable_fraction(ts) for ts in in_window]
    daily_transitions = sum(1 for i in range(1, len(daily)) if daily[i] != daily[i - 1])
    days_risk_off = sum(1 for f in daily if f < 1.0)

    # Month-end target exposure (what the plan actually sees → drives turnover).
    me = [overlay.deployable_fraction(pd.Timestamp(d)) for d in reb_dates]
    me_risk_off = sum(1 for f in me if f < 1.0)
    me_flips = sum(1 for i in range(1, len(me)) if me[i] != me[i - 1])

    return {
        "n_trading_days": len(daily),
        "daily_transitions": daily_transitions,
        "pct_days_risk_off": (days_risk_off / len(daily) * 100) if daily else 0.0,
        "n_rebalances": len(me),
        "month_end_risk_off": me_risk_off,
        "month_end_flips": me_flips,
    }


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    for noisy in ("app.backtest_v2", "pandas_ta_classic", "pandas_ta"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    print("Turnover decomposition — T3 candidate (READ-ONLY, no param changed)")
    print(f"  Candidate regime: {CANDIDATE_REGIME}")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}  (base cost)\n")

    print("Loading prices_adjusted...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}", flush=True)

    print("Loading real Nifty 50 price index (cached)...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(f"FAIL: regime index unavailable: {exc}", file=sys.stderr)
        return 2

    print("Precomputing signals on DISCOVERY (shared by both runs)...", flush=True)
    base_cfg = MomentumConfig(date_from=DISCOVERY[0], date_to=DISCOVERY[1])
    signal_store = precompute_signals(prices, base_cfg)

    # ---- Run A: candidate, regime ON --------------------------------------
    print("Run A: candidate (regime ON), monthly...", flush=True)
    res_on = engine.run(
        prices,
        base_cfg,
        index_prices=index_prices,
        regime_config=CANDIDATE_REGIME,
        cost_level="base",
        signal_store=signal_store,
    )
    m_on = metrics.compute_metrics(res_on)
    t_on = m_on.annualized_turnover

    # ---- Run B: same config, regime OFF (counterfactual) ------------------
    print("Run B: regime OFF (counterfactual), monthly...", flush=True)
    cfg_off = dataclasses.replace(base_cfg, use_regime_overlay=False)
    res_off = engine.run(
        prices,
        cfg_off,
        index_prices=index_prices,
        cost_level="base",
        signal_store=signal_store,
    )
    m_off = metrics.compute_metrics(res_off)
    t_off = m_off.annualized_turnover

    # Regime bucket = what turning the overlay ON adds.
    t_regime = t_on - t_off

    # ---- Split the no-regime turnover into churn vs reset ------------------
    dec = _decompose_fills(res_off)
    churn_dw = dec["entry"] + dec["exit"]
    reset_dw = dec["reweight"]
    total_dw = dec["total"]
    churn_frac = churn_dw / total_dw if total_dw > 0 else 0.0
    reset_frac = reset_dw / total_dw if total_dw > 0 else 0.0

    t_churn = churn_frac * t_off
    t_reset = reset_frac * t_off

    # Reconciliation: fill-derived Σ|Δw| vs engine's per_rebalance Σ|Δw| (no-regime).
    engine_total_dw_off = sum(t for _, t in res_off.per_rebalance_turnover)
    recon = (
        (total_dw / engine_total_dw_off) if engine_total_dw_off > 0 else float("nan")
    )

    prof = _regime_profile(index_prices, res_on.rebalance_dates_used)

    # ---------------------------------------------------------------------- #
    print("\n" + "=" * 72)
    print("  TURNOVER DECOMPOSITION  (annualized, two-way Σ|Δweight|)")
    print("=" * 72)
    print(f"  Candidate (regime ON) total turnover : {t_on * 100:6.0f}%")
    print(f"  Regime OFF (counterfactual) total    : {t_off * 100:6.0f}%")
    print("  " + "-" * 50)
    print(
        f"  1. REGIME (overlay toggling book)    : {t_regime * 100:6.0f}%"
        f"   ({t_regime / t_on * 100:4.0f}% of total)"
    )
    print(
        f"  2. CHURN  (membership entry/exit)    : {t_churn * 100:6.0f}%"
        f"   ({t_churn / t_on * 100:4.0f}% of total)"
    )
    print(
        f"  3. WEIGHT-RESET (trim/top-up held)   : {t_reset * 100:6.0f}%"
        f"   ({t_reset / t_on * 100:4.0f}% of total)"
    )
    print("  " + "-" * 50)
    print(f"  Σ check: {(t_regime + t_churn + t_reset) * 100:.0f}% ≈ {t_on * 100:.0f}%")

    print("\n  No-regime fill split (Σ|Δw| units):")
    print(
        f"    entry={dec['entry']:.2f}  exit={dec['exit']:.2f}  "
        f"reweight={dec['reweight']:.2f}  total={total_dw:.2f}"
    )
    print(
        f"    churn={churn_frac:.0%}  weight-reset={reset_frac:.0%}  "
        f"(fill↔engine reconciliation: {recon:.1%})"
    )

    print("\n  Regime overlay profile (debounce=1, rof=0.25):")
    print(f"    trading days in window     : {prof['n_trading_days']}")
    print(f"    daily state transitions    : {prof['daily_transitions']}")
    print(f"    % trading days risk-off    : {prof['pct_days_risk_off']:.1f}%")
    print(f"    monthly rebalances         : {prof['n_rebalances']}")
    print(f"    month-ends at risk-off     : {prof['month_end_risk_off']}")
    print(f"    month-end exposure flips   : {prof['month_end_flips']}")

    print("\n  Context metrics:")
    print(
        f"    regime ON : calmar={m_on.calmar:.3f}  cagr={m_on.cagr * 100:.2f}%  "
        f"maxdd={m_on.max_drawdown:.2%}  time-in-cash≈{(1 - _avg_exposure(res_on)) * 100:.1f}%"
    )
    print(
        f"    regime OFF: calmar={m_off.calmar:.3f}  cagr={m_off.cagr * 100:.2f}%  "
        f"maxdd={m_off.max_drawdown:.2%}"
    )
    print("=" * 72)
    return 0


def _avg_exposure(result: engine.EngineResult) -> float:
    exps = [s.exposure for s in result.snapshots]
    return sum(exps) / len(exps) if exps else 0.0


if __name__ == "__main__":
    sys.exit(main())
