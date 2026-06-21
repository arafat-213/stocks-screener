"""
r10_oos.py — R10.3: the ONE-SHOT FINAL_OOS run on locked S3. EXPLORATORY (under §13).

Pre-registration: `specs/v3/10_SKEW_REVALIDATION_PREREG.md` §8/§9/§12 + the §13 post-hoc
deviation. S3 cleared the R10.2 battery (all HARD gates except the §13-waived §6.3), so
per §13 it is authorized for the single, irreversible FINAL_OOS run.

╔══════════════════════════════════════════════════════════════════════════════════════╗
║  THIS SCRIPT CONSUMES THE PRISTINE FINAL_OOS BLOCK (2023-07-01 → 2026-06-12).          ║
║  It is the FIRST and ONLY time FINAL_OOS is observed across the entire v2→v3 program.  ║
║  Byte-for-byte locked S3 (08 SU2 / 10 §3) — NO re-tuning, NO re-pick, run ONCE.        ║
║  Verdict ceiling is capped at "exploratory / disclosed-deviation" (§13.1) — a pass is  ║
║  NEVER "validated"; it warrants a fresh, properly pre-registered re-test, not deploy.  ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

What is measured on FINAL_OOS (§9):
  - base + pessimistic Calmar / maxDD / Sharpe / turnover.
  - deploy bar §2c: beats fair-costed Nifty200 Mom30 on base Calmar AND stays above it at
    pessimistic, maxDD ≤ 100%; zero-cost TRI reported as the conservative cross-check.
  - the four HARD gates hold OOS: §6.1 (pess Calmar ratio vs Nifty50 TRI ≥ 1.0),
    §6.2-skew (median≥70%/p5≥50%/rot≥25 on the OOS book), §6.5 capacity. §6.3 is a
    DISCOVERY-lattice concept (already FAILED + waived §13) — N/A on a one-shot OOS.
  - raw + deflated Sharpe (Bailey & LdP 2016) across a documented cumulative-K range
    (the deflation headwind is severe and explicit, §7); PBO carried coarse from TBE7.

Run (CONSUMES FINAL_OOS — only after R10.2 advanced S3):
    backend/venv/bin/python -m app.backtest_v2.r10_oos
"""

from __future__ import annotations

import gc
import logging
import math
import sys
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.costs import CostConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.skew_robustness import (
    DROP_K,
    N_DRAWS,
    skew_aware_universe_perturbation,
)
from app.backtest_v2.stable_universe import build_stable_universe_mask
from app.backtest_v2.v3_config import TRACK_A_BASELINE, V3Config
from app.backtest_v2.validation import (
    FINAL_OOS,
    ConfigLedger,
    deflated_sharpe,
)
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Frozen S3 construction (`10` §3) — byte-for-byte the R10.2 / SU2 candidate.
_U, _B, _M = 350, 1.25, 130
_SMOOTHING = 0
_CADENCE = "monthly"

_S61_RATIO_FLOOR = 1.0
_MAX_ADV_PARTICIPATION_PCT = 5.0
_LIQUIDITY_FLOOR_CR = 5.0
_N_TOP_CONTRIBUTORS = 10

# §2c fair-costed Mom30 drag (identical model to r10_battery).
_ETF_EXPENSE_ANNUAL = 0.0030
_INDEX_TWOWAY_TURNOVER = 1.00

# Cumulative trial count K (DOCUMENTED program record, NOT a live ledger read — the
# in-memory ledger does not persist across sessions). `10` §7: K ≥ 69 (09) + VT + 4
# (su_md_skew_recheck) + 7 (R10.1 lattice) + 5 (R10.2). DSR is reported across a RANGE
# so the verdict does not hinge on one K; the deflation headwind is severe at every value.
_K_RANGE = (69, 85, 100)

# PBO carried coarse from TBE7 (DISCOVERY walk-forward, 2 folds → 0.00). A fresh
# fine-grained CSCV (7 configs × N folds) is out of this run's budget (Rule 6); the OOS
# verdict turns on the deploy bar + DSR, not PBO. Disclosed, not silently skipped (Rule 12).
_PBO_CARRIED = 0.00
_PBO_NOTE = "carried coarse from TBE7 (DISCOVERY WF, 2 folds); not re-computed here"


def _v3_config(date_from: date, date_to: date) -> V3Config:
    return V3Config(
        active_factors=list(TRACK_A_BASELINE.active_factors),
        rebalance_cadence=_CADENCE,
        sell_rank_buffer=_M,
        rank_smoothing_months=_SMOOTHING,
        target_positions=TRACK_A_BASELINE.target_positions,
        use_regime_overlay=True,
        catastrophic_stop_pct=25.0,
        liquidity_floor_cr=5.0,
        universe_mode="stable",
        universe_size_U=_U,
        universe_buffer_B=_B,
        date_from=date_from,
        date_to=date_to,
    )


def _engine_cfg(v3cfg: V3Config, date_from: date, date_to: date) -> MomentumConfig:
    return MomentumConfig(
        target_positions=v3cfg.target_positions,
        sell_rank_buffer=v3cfg.sell_rank_buffer,
        liquidity_floor_cr=v3cfg.liquidity_floor_cr,
        momentum_lookback_days=v3cfg.momentum_lookback_days,
        momentum_skip_days=v3cfg.momentum_skip_days,
        vol_lookback_days=v3cfg.vol_lookback_days,
        trend_ma=v3cfg.trend_ma,
        max_position_pct=v3cfg.max_position_pct,
        starting_capital=v3cfg.starting_capital,
        use_regime_overlay=v3cfg.use_regime_overlay,
        catastrophic_stop_pct=v3cfg.catastrophic_stop_pct,
        rebalance=v3cfg.rebalance_cadence,
        date_from=date_from,
        date_to=date_to,
    )


def _equity_series(result: engine.EngineResult) -> pd.Series:
    return pd.Series(
        [s.equity for s in result.snapshots],
        index=pd.DatetimeIndex([pd.Timestamp(s.date) for s in result.snapshots]),
    )


def _daily_returns(result: engine.EngineResult) -> np.ndarray:
    eq = _equity_series(result).to_numpy(dtype=float)
    if eq.size < 2:
        return np.array([], dtype=float)
    return eq[1:] / eq[:-1] - 1.0


def _annual_fair_cost_drag(cost_level: str) -> float:
    cfg = CostConfig.base() if cost_level == "base" else CostConfig.pessimistic()
    statutory_both = (cfg.exchange_txn_pct + cfg.sebi_pct) * (1.0 + cfg.gst_pct)
    buy_rate = cfg.stt_pct + cfg.stamp_duty_pct + cfg.base_slippage_pct + statutory_both
    sell_rate = cfg.stt_pct + cfg.base_slippage_pct + statutory_both
    repl = (_INDEX_TWOWAY_TURNOVER / 2.0) * (buy_rate + sell_rate)
    return _ETF_EXPENSE_ANNUAL + repl


def _apply_fair_cost(tri: pd.Series, annual_drag: float) -> pd.Series:
    years = (tri.index - tri.index[0]).days / 365.25
    return tri * ((1.0 - annual_drag) ** years)


def _per_year_top_contributors(
    result: engine.EngineResult, top_n: int = _N_TOP_CONTRIBUTORS
) -> dict[int, list[str]]:
    by_year: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for f in result.fills_log:
        notional = f.qty * f.price
        signed = notional if f.side in ("sell", "trim") else -notional
        by_year[f.date.year][f.symbol] += signed - f.cost_rupees
    out: dict[int, list[str]] = {}
    for yr, names in by_year.items():
        ranked = sorted(names.items(), key=lambda kv: kv[1], reverse=True)
        out[yr] = [sym for sym, _ in ranked[:top_n]]
    return out


def _check_s65(m: metrics.BacktestMetrics) -> tuple[float, bool]:
    capital = m.start_equity or 1_000_000.0
    years = m.n_calendar_days / 365.25
    n_fills = max(m.n_fills, 1)
    total_one_way = capital * m.annualized_turnover * years / 2.0
    avg_trade = total_one_way / n_fills
    pct = (avg_trade / (_LIQUIDITY_FLOOR_CR * 1e7)) * 100.0
    return round(pct, 3), pct < _MAX_ADV_PARTICIPATION_PCT


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in (
        "app.backtest_v2",
        "app.core.strategy",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(noisy).setLevel(logging.ERROR)
    logging.getLogger(__name__).setLevel(logging.INFO)

    print("=" * 90)
    print(
        "  R10.3 — ONE-SHOT FINAL_OOS on locked S3 (EXPLORATORY, under §13 deviation)"
    )
    print(
        f"  FINAL_OOS {FINAL_OOS[0]} → {FINAL_OOS[1]}  |  S3 = stable U={_U} B={_B}, 5-factor, M={_M}"
    )
    print(
        "  *** This CONSUMES the pristine FINAL_OOS — first and only observation. ***"
    )
    print(
        "  Verdict ceiling: 'exploratory / disclosed-deviation' — NEVER 'validated' (§13.1)."
    )
    print("=" * 90)

    print(
        "\nLoading prices_adjusted (FULL history — INCLUDES FINAL_OOS region)...",
        flush=True,
    )
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(
        f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}"
        f"  range={prices['date'].min().date()} → {prices['date'].max().date()}",
        flush=True,
    )
    if prices["date"].max() < pd.Timestamp(FINAL_OOS[1]):
        print(
            f"FAIL: price history ends {prices['date'].max().date()} < FINAL_OOS end "
            f"{FINAL_OOS[1]} — cannot run the OOS. Aborting (FINAL_OOS NOT consumed).",
            file=sys.stderr,
        )
        return 2

    print("Loading Nifty50 price index (regime) + Mom30/Nifty50 TRI...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
        tri_mom30 = benchmark.load_tri(
            benchmark.TRI_MOMENTUM_30, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
        tri_nifty50 = benchmark.load_tri(
            benchmark.TRI_NIFTY_50, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
    except Exception as exc:
        print(f"FAIL: benchmark unavailable: {exc}", file=sys.stderr)
        return 2

    v3cfg = _v3_config(*FINAL_OOS)
    eng = _engine_cfg(v3cfg, *FINAL_OOS)
    print(
        "Building stable mask (point-in-time, causal) + gate cache + composite...",
        flush=True,
    )
    mask = build_stable_universe_mask(
        prices, _U, _B, v3cfg.universe_rank_lookback_td, v3cfg.universe_review_cadence
    )
    gate_store = precompute_signals(prices, eng)
    gate_ind = gate_store._data
    composite = factors.composite_rank(prices, v3cfg)
    ss = V3SignalStore(gate_ind, composite, v3cfg, universe_mask=mask)
    ledger = ConfigLedger()

    # ---- The one-shot: base + pessimistic on FINAL_OOS ----
    print(
        "\n*** FIRING THE ONE-SHOT: locked S3 on FINAL_OOS (base + pessimistic) ***",
        flush=True,
    )
    ledger.add(
        {
            "config": "S3",
            "U": _U,
            "B": _B,
            "M": _M,
            "window": "FINAL_OOS",
            "cost_level": "base",
        },
        stage="R10_OOS_base",
    )
    res_base = engine.run(
        prices, eng, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    m_base = metrics.compute_metrics(res_base)
    base_eq = _equity_series(res_base)
    base_ret = _daily_returns(res_base)
    trading_cal = [pd.Timestamp(s.date) for s in res_base.snapshots]

    ledger.add(
        {"config": "S3", "window": "FINAL_OOS", "cost_level": "pessimistic"},
        stage="R10_OOS_pess",
    )
    res_pess = engine.run(
        prices,
        eng,
        index_prices=index_prices,
        cost_level="pessimistic",
        signal_store=ss,
    )
    m_pess = metrics.compute_metrics(res_pess)
    pess_eq = _equity_series(res_pess)
    cal_pess = [pd.Timestamp(s.date) for s in res_pess.snapshots]
    _OOS_BASE_ANCHOR = m_base.calmar  # the authoritative one-shot (full history)
    print(
        f"  OOS base    Calmar={m_base.calmar:.3f}  maxDD={m_base.max_drawdown:.1%}  "
        f"Sharpe={m_base.sharpe:.3f}  turn={m_base.annualized_turnover * 100:.0f}%",
        flush=True,
    )
    print(
        f"  OOS pessim. Calmar={m_pess.calmar:.3f}  maxDD={m_pess.max_drawdown:.1%}",
        flush=True,
    )

    # ---- Deploy bar §2c (fair-costed Mom30, base + pessimistic) + zero-cost cross-check ----
    drag_b, drag_p = (
        _annual_fair_cost_drag("base"),
        _annual_fair_cost_drag("pessimistic"),
    )
    zc_aligned = benchmark.align_benchmark(
        tri_mom30, eng.date_from, trading_cal, eng.starting_capital
    )
    bm_zc = metrics.compute_benchmark_metrics(base_eq, zc_aligned)
    fb_aligned = benchmark.align_benchmark(
        _apply_fair_cost(tri_mom30, drag_b),
        eng.date_from,
        trading_cal,
        eng.starting_capital,
    )
    bm_fb = metrics.compute_benchmark_metrics(base_eq, fb_aligned)
    fp_aligned = benchmark.align_benchmark(
        _apply_fair_cost(tri_mom30, drag_p),
        eng.date_from,
        cal_pess,
        eng.starting_capital,
    )
    bm_fp = metrics.compute_benchmark_metrics(pess_eq, fp_aligned)
    dep_base_pass = (
        bm_fb.strategy_calmar > bm_fb.benchmark_calmar
        and not math.isnan(bm_fb.max_dd_ratio)
        and bm_fb.max_dd_ratio <= 1.0
    )
    dep_pess_pass = (
        bm_fp.strategy_calmar > bm_fp.benchmark_calmar
        and not math.isnan(bm_fp.max_dd_ratio)
        and bm_fp.max_dd_ratio <= 1.0
    )

    # ---- §6.1 OOS: pess Calmar ratio vs Nifty50 TRI ----
    n50_aligned = benchmark.align_benchmark(
        tri_nifty50, eng.date_from, cal_pess, eng.starting_capital
    )
    bm_n50 = metrics.compute_benchmark_metrics(pess_eq, n50_aligned)
    s61_pass = (
        not math.isnan(bm_n50.calmar_ratio) and bm_n50.calmar_ratio >= _S61_RATIO_FLOOR
    )

    # ---- §6.5 OOS capacity ----
    s65_pct, s65_pass = _check_s65(m_base)

    # ---- Deflation: raw + deflated Sharpe across documented K range; PBO carried ----
    raw_sharpe = m_base.sharpe
    dsr = {k: deflated_sharpe(raw_sharpe, base_ret, k) for k in _K_RANGE}

    # Print the cheap gate results immediately (the skew loop below is the only slow part).
    print(
        f"\n  [deploy base] S3 {bm_fb.strategy_calmar:.3f} vs fair-Mom30 {bm_fb.benchmark_calmar:.3f} "
        f"(zero-cost TRI {bm_zc.benchmark_calmar:.3f}) dd {bm_fb.max_dd_ratio:.2f} → {'PASS' if dep_base_pass else 'FAIL'}",
        flush=True,
    )
    print(
        f"  [deploy pess BINDING] S3 {bm_fp.strategy_calmar:.3f} vs fair-Mom30 {bm_fp.benchmark_calmar:.3f} "
        f"dd {bm_fp.max_dd_ratio:.2f} → {'PASS' if dep_pess_pass else 'FAIL'}",
        flush=True,
    )
    print(
        f"  [§6.1] pess Calmar ratio vs Nifty50 TRI {bm_n50.calmar_ratio:.2f} → {'PASS' if s61_pass else 'FAIL'}",
        flush=True,
    )
    print(
        f"  [§6.5] participation {s65_pct:.3f}% → {'PASS' if s65_pass else 'FAIL'}",
        flush=True,
    )
    print(
        f"  [deflation] raw Sharpe {raw_sharpe:.3f}; DSR "
        + ", ".join(f"K={k}:{dsr[k]:+.3f}" for k in _K_RANGE),
        flush=True,
    )

    # ---- §6.2-skew OOS (the book's breadth out-of-sample) ----
    # The 200-draw perturbation re-runs the engine 200×. To keep it tractable WITHOUT
    # changing the result, run it on a warmup-sufficient slice (>= 2021-07-01: ~2yr of
    # warmup before the 2023-07 OOS start, covering the 252-td momentum + 200-td trend
    # lookbacks). The precomputed gate cache / composite / mask are unchanged (built on
    # full history, reused via `ss`), so the engine is deterministic. We ASSERT the base
    # run on the slice reproduces the authoritative full-history OOS Calmar before trusting
    # any skew number (fail loud — Rule 12). This is reproduction of the SAME one-shot, not
    # a new shot.
    prices_skew = prices[prices["date"] >= pd.Timestamp(2022, 1, 1)].copy()
    res_slice = engine.run(
        prices_skew, eng, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    cal_slice = metrics.compute_metrics(res_slice).calmar
    slice_ok = abs(cal_slice - _OOS_BASE_ANCHOR) <= 1e-6
    print(
        f"\n  [§6.2-skew OOS] warmup-slice base Calmar {cal_slice:.6f} vs full {_OOS_BASE_ANCHOR:.6f} "
        f"→ {'reproduced' if slice_ok else 'MISMATCH — slice unsafe, skew SKIPPED'}",
        flush=True,
    )
    del res_slice
    gc.collect()

    if slice_ok:
        held_isins = [ns.isin for ns in m_base.per_name_stats]
        per_year = _per_year_top_contributors(res_base)

        def run_perturbed(drop_set: frozenset[str]) -> float:
            prices_p = prices_skew[~prices_skew["isin"].isin(drop_set)]
            res_p = engine.run(
                prices_p,
                eng,
                index_prices=index_prices,
                cost_level="base",
                signal_store=ss,
            )
            cal = metrics.compute_metrics(res_p).calmar
            del prices_p, res_p
            gc.collect()
            return cal

        print(
            f"  [§6.2-skew OOS] {N_DRAWS} random-{DROP_K} drops + contributor rotation ...",
            flush=True,
        )
        skew = skew_aware_universe_perturbation(
            held_isins, m_base.calmar, run_perturbed, per_year, n_draws=N_DRAWS
        )
        s62_pass = skew.passed
        s62_median = skew.random_subset.median_retention
        s62_p5 = skew.random_subset.p5_retention
        s62_rot = skew.rotation.n_distinct
        print(f"    {skew.random_subset.summary}", flush=True)
        print(f"    {skew.rotation.summary}", flush=True)
    else:
        # Slice unsafe → do not fabricate a skew result; mark indeterminate (gate fails closed).
        s62_pass, s62_median, s62_p5, s62_rot = False, float("nan"), float("nan"), 0

    # ---- §9 verdict ----
    four_gate_hold = (
        s61_pass and s62_pass and dep_base_pass and dep_pess_pass and s65_pass
    )
    sep = "=" * 90
    print(f"\n{sep}")
    print("  R10.3 — FINAL_OOS VERDICT (EXPLORATORY, §13 ceiling)")
    print(sep)
    print(
        f"\n  OOS base Calmar {m_base.calmar:.3f} | pess {m_pess.calmar:.3f} | Sharpe {raw_sharpe:.3f} | maxDD {m_base.max_drawdown:.1%}"
    )
    print("\n  DEPLOY BAR §2c (fair-costed Nifty200 Mom30):")
    print(
        f"     base:        S3 {bm_fb.strategy_calmar:.3f} vs fair {bm_fb.benchmark_calmar:.3f} "
        f"(zero-cost TRI {bm_zc.benchmark_calmar:.3f}) dd_ratio {bm_fb.max_dd_ratio:.2f} → {'PASS' if dep_base_pass else 'FAIL'}"
    )
    print(
        f"     pessimistic: S3 {bm_fp.strategy_calmar:.3f} vs fair {bm_fp.benchmark_calmar:.3f} "
        f"dd_ratio {bm_fp.max_dd_ratio:.2f} → {'PASS' if dep_pess_pass else 'FAIL'}  ← BINDING"
    )
    print("\n  FOUR HARD GATES (OOS hold):")
    print(
        f"     §6.1 pess Calmar ratio vs Nifty50 TRI {bm_n50.calmar_ratio:.2f} (≥1.0) → {'PASS' if s61_pass else 'FAIL'}"
    )
    _sm = f"{s62_median:.0%}" if not math.isnan(s62_median) else "n/a"
    _sp = f"{s62_p5:.0%}" if not math.isnan(s62_p5) else "n/a"
    print(
        f"     §6.2-skew median {_sm} / p5 {_sp} / rot {s62_rot} → {'PASS' if s62_pass else 'FAIL'}"
    )
    print(
        "     §6.3 dense-lattice → N/A on one-shot OOS (FAILED+waived §13; DISCOVERY-only concept)"
    )
    print(f"     §6.5 capacity {s65_pct:.3f}% (<5%) → {'PASS' if s65_pass else 'FAIL'}")
    print(f"\n  DEFLATION (severe headwind, §7):  raw Sharpe {raw_sharpe:.3f}")
    for k in _K_RANGE:
        print(
            f"     K={k:<4d} → deflated Sharpe {dsr[k]:+.3f} {'(> 0)' if dsr[k] > 0 else '(≤ 0 — selection explains it)'}"
        )
    print(f"     PBO {_PBO_CARRIED:.2f} ({_PBO_NOTE})")

    print(f"\n{sep}")
    deploy_ok = dep_base_pass and dep_pess_pass and (not math.isnan(bm_fb.max_dd_ratio))
    dsr_ok = all(dsr[k] > 0 for k in _K_RANGE)
    if four_gate_hold and deploy_ok:
        verdict = "EXPLORATORY OOS PASS"
        if not dsr_ok:
            verdict += (
                " — but DEFLATION-MARGINAL (deploy-bar pass, deflated Sharpe ≤ 0 at K≳)"
            )
        print(f"  §9 VERDICT: {verdict}")
        print(
            "  Reached via a DISCLOSED post-hoc §6.3 waiver (§13) — NOT 'validated'. Warrants a"
        )
        print(
            "  fresh, properly pre-registered re-test, NOT deployment. Conditional name-concentration"
        )
        print(
            "  caveat (classic §6.2 35%) + §6.4 regime-concentration risk both stand."
        )
    else:
        print(
            "  §9 VERDICT: RESEARCH NOTE — the OOS does not hold the deploy bar / four gates."
        )
        print(
            "  'Buy the index fund' stands as the earned, money-saving conclusion (Rule 12 — no softening)."
        )
    print("  *** FINAL_OOS is now CONSUMED — no longer pristine. One shot, spent. ***")
    print(sep)
    print(
        f"\n  ConfigLedger entries this run: {ledger.n_trials}  (K for DSR carried from program record)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
