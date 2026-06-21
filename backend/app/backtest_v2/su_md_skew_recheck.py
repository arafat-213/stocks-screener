"""
su_md_skew_recheck.py — DIAGNOSTIC: re-evaluate the two index-beating configs that
classic §6.2 rejected (SU2's S3, MD2's MD-M200) under the SKEW-AWARE §6.2 gate that
was adopted in 09 §2c/§6.2 (skew_robustness.py) — the fairer concentration test.

WHY (the question this answers, NOT a new prereg):
  - S3 (stable U=350 B=1.25, 5-factor, M=130) and MD-M200 (floor, 5-factor, M=200)
    both BEAT the Nifty200 Mom30 TRI on base-cost Calmar (0.575 / 0.550 vs 0.473) and
    pass the corrected maxDD ≤ 100% clause, yet were eliminated on §6.2 *classic*
    drop-top-10 retention (35% / 34%).
  - 09 §2c concluded classic drop-top-10 is an ex-post, lookahead-flavoured perturbation
    that is structurally hostile to a positively-skewed momentum strategy, and REPLACED
    it (for VT) with the skew-aware test: random-subset retention (median ≥ 0.70 AND
    p5 ≥ 0.50 over 200 random-10 drops) + contributor rotation (≥ 25 distinct per-year
    top-10 names). That gate was never applied to S3 / MD-M200.

This script applies the *already-committed* skew-aware gate to those two configs.

DISCIPLINE (explicit — read before trusting the output):
  - DISCOVERY only. FINAL_OOS is NOT touched, NOT loaded, NOT consumed.
  - This does NOT retroactively change the SU2 / MD2 closes — those stand as the record
    under the gates as-run. This is a diagnostic that informs whether a *separate* prereg
    amendment (formal re-test + one-shot OOS) is warranted; it locks nothing by itself.
  - The skew-aware thresholds are imported verbatim from skew_robustness.py (09-locked):
    NOT re-tuned here. classic drop-top-10 is reported alongside (the §2c guard).
  - All runs logged to ConfigLedger — K is honest (these are real trials).

Run (full, 200 draps/config — the locked N_DRAWS):
    backend/venv/bin/python -m app.backtest_v2.su_md_skew_recheck

Smoke test only (NOT a valid result — loud banner): SKEW_NDRAWS=3 backend/venv/bin/python -m ...
"""

from __future__ import annotations

import gc
import logging
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.skew_robustness import (
    DROP_K,
    N_DRAWS,
    skew_aware_universe_perturbation,
)
from app.backtest_v2.stable_universe import build_stable_universe_mask
from app.backtest_v2.v3_config import TRACK_A_BASELINE, V3Config
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

_SMOOTHING = 0
_CADENCE = "monthly"
_N_TOP_CONTRIBUTORS = 10
_CLASSIC_RETENTION_THRESHOLD = 0.70

# Smoke-test knob ONLY (default = the 09-locked 200). A non-200 value prints a loud
# banner and the run is NOT a valid result.
_N_DRAWS = int(os.environ.get("SKEW_NDRAWS", N_DRAWS))


@dataclass
class ReConfig:
    name: str
    universe_mode: str  # "stable" | "floor"
    universe_size_U: int
    universe_buffer_B: float
    sell_rank_buffer_M: int
    anchor_calmar: float  # expected base Calmar (sanity reproduction, not a gate)
    source: str

    @property
    def label(self) -> str:
        univ = (
            f"stable U={self.universe_size_U} B={self.universe_buffer_B:g}"
            if self.universe_mode == "stable"
            else "floor (daily)"
        )
        return f"{univ} M={self.sell_rank_buffer_M}"


# The two index-beaters classic §6.2 rejected (5-factor TRACK_A_BASELINE base).
_CONFIGS: list[ReConfig] = [
    ReConfig("S3", "stable", 350, 1.25, 130, 0.575, "SU2 (08): §6.2-classic 35% FAIL"),
    ReConfig(
        "MD-M200", "floor", 200, 1.25, 200, 0.550, "MD2 (06): §6.2-classic 34% FAIL"
    ),
]


@dataclass
class ReResult:
    name: str
    label: str
    source: str
    base_calmar: float
    base_max_dd: float
    turnover_pct: float
    n_held: int
    # skew-aware §6.2 (the question)
    skew_median: float
    skew_p5: float
    skew_rs_pass: bool
    rot_n_distinct: int
    rot_pass: bool
    skew_pass: bool
    # classic drop-top-10 (reported guard)
    classic_retention: float
    classic_pass: bool
    classic_dropped: list[str]
    # deploy bar (confirm they still beat the index)
    dep_calmar_strat: float
    dep_calmar_bench: float
    dep_dd_ratio: float
    dep_pass: bool


def _v3_config(cfg: ReConfig, date_from: date, date_to: date) -> V3Config:
    return V3Config(
        active_factors=list(TRACK_A_BASELINE.active_factors),
        rebalance_cadence=_CADENCE,
        sell_rank_buffer=cfg.sell_rank_buffer_M,
        rank_smoothing_months=_SMOOTHING,
        target_positions=TRACK_A_BASELINE.target_positions,
        use_regime_overlay=True,
        catastrophic_stop_pct=25.0,
        liquidity_floor_cr=5.0,
        universe_mode=cfg.universe_mode,
        universe_size_U=cfg.universe_size_U,
        universe_buffer_B=cfg.universe_buffer_B,
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


def _rss_mb() -> float:
    """Resident set size in MB (Linux /proc), for memory observability."""
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except OSError:
        pass
    return float("nan")


def _per_year_top_contributors(
    result: engine.EngineResult, top_n: int = _N_TOP_CONTRIBUTORS
) -> dict[int, list[str]]:
    """Per calendar year, the top-`top_n` names by that year's realized net cashflow
    (mirrors vt2_battery._per_year_top_contributors — identity by symbol)."""
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


def run_config(
    cfg: ReConfig,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    tri_momentum30: pd.Series,
    composite: pd.DataFrame,
    gate_ind,
    ledger: ConfigLedger,
) -> ReResult:
    v3cfg = _v3_config(cfg, *DISCOVERY)
    eng = _engine_cfg(v3cfg, *DISCOVERY)
    mask = (
        build_stable_universe_mask(
            prices,
            cfg.universe_size_U,
            cfg.universe_buffer_B,
            v3cfg.universe_rank_lookback_td,
            v3cfg.universe_review_cadence,
        )
        if cfg.universe_mode == "stable"
        else None
    )
    ss = V3SignalStore(gate_ind, composite, v3cfg, universe_mask=mask)

    payload = {
        "config": cfg.name,
        "universe_mode": cfg.universe_mode,
        "U": cfg.universe_size_U if cfg.universe_mode == "stable" else None,
        "B": cfg.universe_buffer_B if cfg.universe_mode == "stable" else None,
        "M": cfg.sell_rank_buffer_M,
        "factors": list(TRACK_A_BASELINE.active_factors),
    }

    # -- Base run --
    log.info("  [base] %s — %s ...", cfg.name, cfg.label)
    ledger.add({**payload, "cost_level": "base"}, stage="SKEW_RECHECK_base")
    res_base = engine.run(
        prices, eng, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    m_base = metrics.compute_metrics(res_base)
    held_isins = [ns.isin for ns in m_base.per_name_stats]
    log.info(
        "    base calmar=%.3f (anchor %.3f)  maxdd=%.1f%%  turn=%.0f%%  held=%d",
        m_base.calmar,
        cfg.anchor_calmar,
        m_base.max_drawdown * 100,
        m_base.annualized_turnover * 100,
        len(held_isins),
    )
    log.info("    [mem] RSS=%.0f MB after base run", _rss_mb())

    # run_perturbed seam: drop ISINs from prices, rerun, return Calmar (same as su2/vt2).
    # Memory-safe: free the per-draw frame copy + engine result before returning so
    # RSS cannot creep across the 200 draws (the OOM cause in the first attempt).
    def run_perturbed(drop_set: frozenset[str]) -> float:
        prices_p = prices[~prices["isin"].isin(drop_set)]
        res_p = engine.run(
            prices_p, eng, index_prices=index_prices, cost_level="base", signal_store=ss
        )
        cal = metrics.compute_metrics(res_p).calmar
        del prices_p, res_p
        gc.collect()
        return cal

    # -- Skew-aware §6.2 (the question) --
    log.info(
        "  [§6.2 skew-aware] %d random-%d drops + contributor rotation ...",
        _N_DRAWS,
        DROP_K,
    )
    per_year = _per_year_top_contributors(res_base)
    skew = skew_aware_universe_perturbation(
        held_isins, m_base.calmar, run_perturbed, per_year, n_draws=_N_DRAWS
    )
    log.info("    %s", skew.random_subset.summary)
    log.info("    %s", skew.rotation.summary)
    log.info("    [mem] RSS=%.0f MB after %d-draw skew test", _rss_mb(), _N_DRAWS)
    ledger.add(
        {
            **payload,
            "test": "skew_aware_s62",
            "n_draws": _N_DRAWS,
            "median_retention": round(skew.random_subset.median_retention, 4),
            "p5_retention": round(skew.random_subset.p5_retention, 4),
            "rotation_distinct": skew.rotation.n_distinct,
        },
        stage="SKEW_RECHECK_s62_skew",
    )

    # -- classic drop-top-10 (reported guard, NOT the gate) --
    sorted_names = sorted(
        m_base.per_name_stats, key=lambda ns: ns.realized_pnl, reverse=True
    )
    top10 = sorted_names[:_N_TOP_CONTRIBUTORS]
    classic_calmar = run_perturbed(frozenset(ns.isin for ns in top10))
    classic_ret = classic_calmar / m_base.calmar if m_base.calmar > 0 else float("nan")
    classic_pass = (
        not math.isnan(classic_ret) and classic_ret >= _CLASSIC_RETENTION_THRESHOLD
    )
    log.info(
        "    [classic drop-top-10] retention=%.0f%%  %s",
        classic_ret * 100 if not math.isnan(classic_ret) else float("nan"),
        "pass" if classic_pass else "FAIL",
    )

    # -- Deployment bar (confirm still beats the index; base cost, maxDD ≤ 100%) --
    trading_cal = [pd.Timestamp(s.date) for s in res_base.snapshots]
    bench_aligned = benchmark.align_benchmark(
        tri_momentum30, eng.date_from, trading_cal, eng.starting_capital
    )
    bm = metrics.compute_benchmark_metrics(_equity_series(res_base), bench_aligned)
    dep_pass = bm.strategy_calmar > bm.benchmark_calmar and (
        not math.isnan(bm.max_dd_ratio) and bm.max_dd_ratio <= 1.0
    )

    return ReResult(
        name=cfg.name,
        label=cfg.label,
        source=cfg.source,
        base_calmar=m_base.calmar,
        base_max_dd=m_base.max_drawdown,
        turnover_pct=m_base.annualized_turnover * 100,
        n_held=len(held_isins),
        skew_median=skew.random_subset.median_retention,
        skew_p5=skew.random_subset.p5_retention,
        skew_rs_pass=skew.random_subset.passed,
        rot_n_distinct=skew.rotation.n_distinct,
        rot_pass=skew.rotation.passed,
        skew_pass=skew.passed,
        classic_retention=classic_ret,
        classic_pass=classic_pass,
        classic_dropped=[ns.symbol for ns in top10],
        dep_calmar_strat=bm.strategy_calmar,
        dep_calmar_bench=bm.benchmark_calmar,
        dep_dd_ratio=bm.max_dd_ratio,
        dep_pass=dep_pass,
    )


def _print_report(results: list[ReResult]) -> None:
    sep = "=" * 86
    print(f"\n{sep}")
    print("  SKEW-AWARE §6.2 RE-CHECK — the index-beaters classic-§6.2 rejected")
    print(
        "  DISCOVERY 2018-02-06 → 2023-06-30 | gate = 09 §2c skew-aware (median≥70% &"
    )
    print(
        "  p5≥50% over random-10 drops) + rotation ≥25 | classic drop-top-10 reported"
    )
    print(sep)

    for r in results:
        print(f"\n{'─' * 74}")
        print(f"  {r.name}  ({r.label})")
        print(f"  was: {r.source}")
        print(
            f"  base Calmar {r.base_calmar:.3f}, maxDD {r.base_max_dd:.1%}, "
            f"turnover {r.turnover_pct:.0f}%, distinct names held {r.n_held}"
        )
        print(f"\n  §6.2 SKEW-AWARE (the gate) — {'PASS' if r.skew_pass else 'FAIL'}")
        print(
            f"        (a) random-subset: median {r.skew_median:.0%} (≥70%) · "
            f"p5 {r.skew_p5:.0%} (≥50%) → {'pass' if r.skew_rs_pass else 'FAIL'}"
        )
        print(
            f"        (b) rotation: {r.rot_n_distinct} distinct per-year top-10 names "
            f"(≥25) → {'pass' if r.rot_pass else 'FAIL'}"
        )
        cret = (
            f"{r.classic_retention:.0%}"
            if not math.isnan(r.classic_retention)
            else "n/a"
        )
        print(
            f"        classic drop-top-10 (reported, NOT the gate): {cret} → "
            f"{'pass' if r.classic_pass else 'FAIL'}"
        )
        print(
            f"\n  deploy bar (Nifty200 Mom30, base cost): C_strat {r.dep_calmar_strat:.3f} "
            f"vs C_bench {r.dep_calmar_bench:.3f}, dd_ratio {r.dep_dd_ratio:.2f} → "
            f"{'PASS' if r.dep_pass else 'FAIL'}"
        )
        # combined read
        if r.skew_pass and r.dep_pass:
            print(
                f"\n  → {r.name} BEATS the index AND passes skew-aware §6.2. "
                f"§6.3 plateau (sparse-lattice) still pending; OOS untouched."
            )
        elif not r.skew_pass:
            print(
                f"\n  → {r.name} still fails the concentration test even skew-aware. "
                f"The 'buy the index' read holds for it."
            )

    print(f"\n{sep}")
    print("  DISCIPLINE: FINAL_OOS untouched. This does NOT alter the SU2/MD2 closes")
    print(
        "  or lock any candidate. If a config clears skew-aware §6.2 + deploy bar, the"
    )
    print(
        "  next step is a SEPARATE prereg amendment (formal §6.3 re-test + one-shot OOS)."
    )
    print(sep)


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

    print("SKEW-AWARE §6.2 re-check — S3 (SU2) + MD-M200 (MD2)")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    if _N_DRAWS != N_DRAWS:
        print(f"\n  {'!' * 70}")
        print(
            f"  SMOKE MODE — n_draws={_N_DRAWS} (NOT the 09-locked {N_DRAWS}). "
            f"NOT A VALID RESULT."
        )
        print(f"  {'!' * 70}\n")

    print("Loading prices_adjusted (offline cache)...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    # Memory + discipline: this re-check lives entirely on DISCOVERY. Drop every row
    # after DISCOVERY end (the FINAL_OOS region) — not needed here and forbidden to
    # touch; carrying it inflates every per-draw copy ~50%. Warmup (pre-2018) is kept.
    prices = prices[prices["date"] <= pd.Timestamp(DISCOVERY[1])].copy()
    print(
        f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}"
        f"  range={prices['date'].min().date()} → {prices['date'].max().date()}"
        f"  (sliced ≤ DISCOVERY end {DISCOVERY[1]})",
        flush=True,
    )

    print("Loading Nifty 50 price index (regime overlay)...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(f"FAIL: regime index unavailable: {exc}", file=sys.stderr)
        return 2

    print("Loading REAL Nifty200 Momentum 30 TRI (deploy bar)...", flush=True)
    try:
        tri_momentum30 = benchmark.load_tri(
            benchmark.TRI_MOMENTUM_30, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
    except Exception as exc:
        print(f"FAIL: Nifty200 Momentum 30 TRI unavailable: {exc}", file=sys.stderr)
        return 2

    # Shared 5-factor gate cache + composite (identical across S3 / MD-M200: same
    # TRACK_A_BASELINE factors; M and universe-mode don't affect precompute/composite).
    ref_v3 = _v3_config(_CONFIGS[0], *DISCOVERY)
    print("Precomputing v2 gate cache + 5-factor composite (shared)...", flush=True)
    gate_store = precompute_signals(prices, _engine_cfg(ref_v3, *DISCOVERY))
    gate_ind = gate_store._data
    composite = factors.composite_rank(prices, ref_v3)

    ledger = ConfigLedger()
    results: list[ReResult] = []
    for i, cfg in enumerate(_CONFIGS, 1):
        print(f"\n[{i}/{len(_CONFIGS)}] {cfg.name} — {cfg.label}", flush=True)
        results.append(
            run_config(
                cfg, prices, index_prices, tri_momentum30, composite, gate_ind, ledger
            )
        )

    _print_report(results)
    print(
        f"\n  ConfigLedger entries this run (K): {ledger.n_trials}  | FINAL_OOS untouched."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
