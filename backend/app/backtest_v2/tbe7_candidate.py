"""
tbe7_candidate.py — TBE7: lock the single Track-B candidate, run the full five
§6 robustness checks on TRACK_B_DISCOVERY, account for the search honestly
(deflated Sharpe + PBO), and state the H3 verdict that gates FINAL_OOS.

CANDIDATE (LOCKED — the config UNDER TEST, not a new search, Rule 12):
  Both fundamental layers were DROPPED upstream — B1 (value, TBE4) and B2
  (quality, TBE5) — and TBE6 (block-weight) was therefore N/A. So the single
  pre-committed Track-B candidate is the **Track-A baseline** (03 §6 honest-drop
  rule), with no V/Q blocks:

      active_factors = ["mom_12_1", "low_vol", "trend_quality", "mom_6_1", "reversal"]
      cadence=monthly   M=70   smoothing=0   N=20   regime ON

  This is byte-for-byte TRACK_A_BASELINE (v3_config). It is also exactly the
  config TBE3 characterized on the Track-B window — so the base run here must
  reproduce the TBE3 anchor (Calmar 1.591) or there is wiring drift (flagged).

FIVE §6 CHECKS (04 §6) — same criteria/thresholds as the v3 battery (t6_robustness):
  §6.1  Cost stress       — beats Nifty50 TRI Calmar at pessimistic cost
  §6.2  Universe perturb  — drop top-10 P&L names; Calmar retains >= 70%
  §6.3  Neighborhood      — plateau on candidate + immediate turnover-knob neighbors
  §6.4  Subperiod + conc. — >= 2/3 positive Calmar AND no single positive period
                            > 5x the mean of the others  (HARDENED — passes_concentration_hard)
  §6.5  Turnover/capacity — avg trade participation < 5% of ADV floor

§6.1/§6.2/§6.5 are reused verbatim from the v3 battery (window-driven by eng_cfg).
§6.3 and §6.4 are reimplemented here only to re-point the window to
TRACK_B_DISCOVERY and the subperiods to the LOCKED Track-B market cycles (the
same dates TBE3/TBE4/TBE5 used) — the criteria are identical.

DEFLATION + PBO (04 §5):
  - deflated_sharpe with K = Track-A trials + Track-B trials. Cumulative K
    entering TBE7 is 28 (16 Track-A + 4 TBE3 + 4 TBE4 + 4 TBE5; TBE6 N/A); this
    file's ledger entries are added on top (a fresh family does NOT reset K).
    Raw Sharpe, K and deflated Sharpe are reported together (Rule 12).
  - PBO via pbo_cscv on walk_forward_windows over the Track-B window (expanding
    folds; no fold touches FINAL_OOS). The config universe is the §6.3
    neighborhood grid (M × smoothing) scored per fold.

H3 VERDICT (03 §2 primary predicate): "does the candidate pass §6.4 WHERE the
TBE3 baseline FAILED?"  TBE3's critical finding was that the baseline
**unexpectedly PASSES §6.4** on this window — so the predicate is VACUOUS (the
baseline never failed), and the candidate IS the baseline (identical config), so
there is no pass-where-it-failed to demonstrate. With both V/Q blocks dropped the
supporting-evidence path is empty too. H3 therefore CANNOT be confirmed →
Track B closes as a research note (03 §9/§10), TBE8 is N/A, FINAL_OOS stays
pristine. This is the pre-accepted outcome, not an engineered one (Rule 12).

DISCOVERY only — FINAL_OOS untouched. Offline: prices and the regime index load
from the local cache; never live yfinance/NSE (Rule 5).

Run:
    backend/venv/bin/python -m app.backtest_v2.tbe7_candidate
"""

from __future__ import annotations

import logging
import math
import sys
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.iterate import GridPoint, plateau_check
from app.backtest_v2.robustness import (
    SUBPERIOD_MIN_POSITIVE,
    CheckResult,
    check_turnover_capacity,
)
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.t6_robustness import (
    check_cost_stress,
    check_universe_perturbation,
)
from app.backtest_v2.v3_config import (
    TRACK_A_BASELINE,
    TRACK_B_DISCOVERY,
    V3Config,
    passes_concentration_hard,
)
from app.backtest_v2.validation import (
    ConfigLedger,
    deflated_sharpe,
    pbo_cscv,
    walk_forward_windows,
)
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Plateau tolerance — the same 0.85 fraction T4/T5/T6 use (04 §4).
_TOL = 0.85

# Cumulative ConfigLedger K entering TBE7 (04 doc, TBE5 session log):
#   16 Track-A + 4 TBE3 + 4 TBE4 + 4 TBE5 (TBE6 N/A — no runs). A fresh family
#   does NOT reset K (03 §5); this file's entries are added on top.
_PRIOR_K = 28

# ---------------------------------------------------------------------------
# CANDIDATE — the LOCKED Track-B candidate = Track-A baseline (B1+B2 dropped).
# ---------------------------------------------------------------------------
_CAND_FACTORS: list[str] = list(TRACK_A_BASELINE.active_factors)
_CAND_CADENCE = TRACK_A_BASELINE.rebalance_cadence
_CAND_M = TRACK_A_BASELINE.sell_rank_buffer
_CAND_SMOOTHING = TRACK_A_BASELINE.rank_smoothing_months

# TBE3 anchor on the Track-B window — the base run must reproduce these or there
# is wiring drift; surface it before trusting TBE7 (Rule 12).
_TBE3_CALMAR = 1.591
_TBE3_SHARPE = 1.335

# §6.3 neighborhood — immediate turnover-knob neighbors of (M=70, smoothing=0),
# same 2-axis structure as t6 (M ∈ {50,70} × smoothing ∈ {0,2}, cadence/N fixed).
_NBR_M: list[int] = [50, 70]
_NBR_SMOOTHING: list[int] = [0, 2]

# §6.4 Track-B subperiods — LOCKED market cycles, identical to TBE3/4/5 (Rule 12).
TRACK_B_SUBPERIODS: list[tuple[str, date, date]] = [
    ("COVID crash + V-recovery", date(2020, 1, 31), date(2021, 3, 31)),
    ("Post-COVID bull", date(2021, 4, 1), date(2022, 1, 31)),
    ("Rate-hike correction", date(2022, 2, 1), date(2023, 6, 30)),
]


# ---------------------------------------------------------------------------
# Config plumbing (mirrors t6_robustness — run scripts stay independent)
# ---------------------------------------------------------------------------


def _candidate_cfg(
    date_from: date,
    date_to: date,
    smoothing: int = _CAND_SMOOTHING,
    buffer_m: int = _CAND_M,
) -> V3Config:
    """The locked candidate, optionally re-pointed in the §6.3 neighborhood
    (smoothing / buffer_m only — the factor set, cadence and N never move)."""
    return V3Config(
        sell_rank_buffer=buffer_m,
        rebalance_cadence=_CAND_CADENCE,
        rank_smoothing_months=smoothing,
        active_factors=list(_CAND_FACTORS),
        target_positions=TRACK_A_BASELINE.target_positions,
        date_from=date_from,
        date_to=date_to,
    )


def _engine_cfg(v3cfg: V3Config, date_from: date, date_to: date) -> MomentumConfig:
    """Project the V3Config knobs the engine consumes onto a MomentumConfig.
    Multi-factor ordering rides in via the signal_store, not this config."""
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


def _build_store(prices: pd.DataFrame, cfg: V3Config, ind) -> V3SignalStore:
    """Composite rank → V3SignalStore on the shared v2 indicator cache `ind`."""
    comp = factors.composite_rank(prices, cfg)
    return V3SignalStore(ind, comp, cfg)


def _run(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    eng_cfg: MomentumConfig,
    signal_store,
    cost_level: str = "base",
) -> tuple[engine.EngineResult, metrics.BacktestMetrics]:
    res = engine.run(
        prices,
        eng_cfg,
        index_prices=index_prices,
        cost_level=cost_level,
        signal_store=signal_store,
    )
    return res, metrics.compute_metrics(res)


# ---------------------------------------------------------------------------
# §6.3 Parameter neighborhood (turnover knobs) — Track-B window
# ---------------------------------------------------------------------------


def check_neighborhood_tb(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    ledger: ConfigLedger,
    store_smoothing: dict[int, V3SignalStore],
) -> CheckResult:
    """§6.4-analogue from t6, re-pointed to TRACK_B_DISCOVERY: plateau check on
    the candidate + immediate turnover-knob neighbors (M ∈ {50,70} × smoothing ∈
    {0,2}). Same plateau_check / 0.85 tolerance — the criterion is identical."""
    tb_start, tb_end = TRACK_B_DISCOVERY
    combos = [(m, s) for m in _NBR_M for s in _NBR_SMOOTHING]
    points: list[GridPoint] = []
    for buffer_m, smoothing in combos:
        cfg = _candidate_cfg(tb_start, tb_end, smoothing=smoothing, buffer_m=buffer_m)
        eng_c = _engine_cfg(cfg, tb_start, tb_end)
        ss = store_smoothing[smoothing]
        trial_id = ledger.add(
            {"buffer_M": buffer_m, "smoothing": smoothing}, check="§6.3_neighborhood"
        )
        _, m = _run(prices, index_prices, eng_c, ss, cost_level="base")
        points.append(
            GridPoint(
                params={"buffer_M": buffer_m, "smoothing": smoothing},
                trial_id=trial_id,
                calmar=m.calmar,
                sharpe=m.sharpe,
                cagr=m.cagr,
                max_dd=m.max_drawdown,
            )
        )
        log.info("  nbr M=%d smoothing=%d  calmar=%.3f", buffer_m, smoothing, m.calmar)

    axes: list[tuple[str, list]] = [
        ("buffer_M", _NBR_M),
        ("smoothing", _NBR_SMOOTHING),
    ]
    verdict = plateau_check(points, axes, tolerance=_TOL)
    passed = verdict.has_plateau
    summary = (
        f"PASS — {verdict.explanation}" if passed else f"FAIL — {verdict.explanation}"
    )
    min_nbr = (
        round(min(n.calmar for n in verdict.neighbors), 3)
        if verdict.neighbors
        else "n/a"
    )
    return CheckResult(
        name="§6.3 Parameter neighborhood",
        passed=passed,
        summary=summary,
        details={
            "n_combos": len(combos),
            "winner_calmar": round(verdict.winner.calmar, 3),
            "winner_params": verdict.winner.params,
            "n_neighbors": len(verdict.neighbors),
            "min_neighbor_calmar": min_nbr,
        },
    )


# ---------------------------------------------------------------------------
# §6.4 Subperiod stability + HARDENED concentration — Track-B subperiods
# ---------------------------------------------------------------------------


def check_subperiod_stability_tb(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    signal_store,
    ledger: ConfigLedger,
) -> CheckResult:
    """§6.4 HARDENED on the LOCKED Track-B subperiods: needs (a) positive Calmar
    in >= 2/3 market cycles AND (b) no single positive subperiod > 5x the mean of
    the others (`passes_concentration_hard`). Identical criterion to t6."""
    subresults: list[tuple[str, metrics.BacktestMetrics]] = []
    for label, start, end in TRACK_B_SUBPERIODS:
        ledger.add(
            {"subperiod": label, "start": str(start), "end": str(end)},
            check="§6.4_subperiod",
        )
        eng_c = _engine_cfg(_candidate_cfg(start, end), start, end)
        _, m = _run(prices, index_prices, eng_c, signal_store, cost_level="base")
        subresults.append((label, m))
        log.info(
            "  Subperiod '%s': calmar=%.3f  cagr=%.2f%%", label, m.calmar, m.cagr * 100
        )

    calmars = [m.calmar for _, m in subresults]
    finite = [c for c in calmars if not math.isnan(c)]
    n_positive = sum(1 for c in finite if c > 0)
    positivity_ok = n_positive >= SUBPERIOD_MIN_POSITIVE
    concentration_ok = passes_concentration_hard(finite)
    passed = positivity_ok and concentration_ok

    # Spread ratio (best / mean of other positives) — reported for continuity
    # with the TBE3/4/5 §6.4 tables (not itself the gate).
    positives = sorted([c for c in finite if c > 0], reverse=True)
    if len(positives) >= 2:
        spread = positives[0] / (sum(positives[1:]) / len(positives[1:]))
    else:
        spread = float("nan")

    calmar_map = {lbl: round(m.calmar, 3) for lbl, m in subresults}
    cagr_map = {lbl: round(m.cagr * 100, 2) for lbl, m in subresults}

    if passed:
        summary = (
            f"PASS — {n_positive}/{len(TRACK_B_SUBPERIODS)} subperiods positive "
            "Calmar AND no single regime > 5x the mean of the others"
        )
    elif not positivity_ok:
        summary = (
            f"FAIL — only {n_positive}/{len(TRACK_B_SUBPERIODS)} subperiods positive "
            f"Calmar (need >= {SUBPERIOD_MIN_POSITIVE}): single-regime trap"
        )
    else:
        summary = (
            "FAIL — concentration gate: one positive subperiod > 5x the mean of the "
            "others (edge is single-regime)"
        )
    return CheckResult(
        name="§6.4 Subperiod stability + concentration",
        passed=passed,
        summary=summary,
        details={
            "n_positive": n_positive,
            "min_required": SUBPERIOD_MIN_POSITIVE,
            "positivity_ok": positivity_ok,
            "concentration_ok": concentration_ok,
            "spread_ratio": round(spread, 2) if not math.isnan(spread) else "n/a",
            "calmar_per_subperiod": calmar_map,
            "cagr_per_subperiod_%": cagr_map,
        },
    )


# ---------------------------------------------------------------------------
# PBO via CSCV — neighborhood configs × walk-forward folds
# ---------------------------------------------------------------------------


def compute_pbo(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    store_smoothing: dict[int, V3SignalStore],
    ledger: ConfigLedger,
) -> tuple[float, int, int]:
    """Build the (n_configs × n_folds) Calmar matrix over the §6.3 neighborhood
    grid and the Track-B expanding walk-forward folds, then run pbo_cscv.

    Returns (pbo, n_configs, n_folds). Each (config, fold) engine run is logged
    to the ledger so K stays honest. No fold reaches FINAL_OOS (hard-bounded by
    walk_forward_windows to the Track-B window)."""
    tb_start, tb_end = TRACK_B_DISCOVERY
    folds = walk_forward_windows(tb_start, tb_end)
    combos = [(m, s) for m in _NBR_M for s in _NBR_SMOOTHING]

    perf = np.full((len(combos), len(folds)), np.nan, dtype=float)
    for j, (buffer_m, smoothing) in enumerate(combos):
        ss = store_smoothing[smoothing]
        for k, w in enumerate(folds):
            cfg = _candidate_cfg(
                w.oos_start, w.oos_end, smoothing=smoothing, buffer_m=buffer_m
            )
            eng_c = _engine_cfg(cfg, w.oos_start, w.oos_end)
            ledger.add(
                {
                    "buffer_M": buffer_m,
                    "smoothing": smoothing,
                    "fold_oos": f"{w.oos_start}→{w.oos_end}",
                },
                check="PBO_fold",
            )
            _, m = _run(prices, index_prices, eng_c, ss, cost_level="base")
            perf[j, k] = m.calmar

    # Calmar can be NaN on a flat fold; CSCV needs finite values. Replace NaN
    # with 0.0 (a flat/zero-Calmar fold is a legitimate "no edge" observation).
    perf = np.nan_to_num(perf, nan=0.0)
    pbo = pbo_cscv(perf, higher_is_better=True)
    return pbo, len(combos), len(folds)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_check(cr: CheckResult) -> None:
    mark = "  PASS" if cr.passed else "  FAIL"
    print(f"\n{mark}  {cr.name}")
    print(f"       {cr.summary}")
    for k, v in cr.details.items():
        if k not in ("top_contributors", "glitch_flags", "winner_params"):
            print(f"       {k}: {v}")
    if cr.details.get("glitch_flags"):
        print(f"       ⚠ glitch-flag candidates: {cr.details['glitch_flags']}")
    if cr.details.get("top_contributors"):
        print(f"       top contributors dropped: {cr.details['top_contributors']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    for noisy in (
        "app.backtest_v2",
        "app.core.strategy",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    tb_start, tb_end = TRACK_B_DISCOVERY

    print("=" * 78)
    print("  v3 / TBE7 — Candidate §6 battery + deflation/PBO + H3 verdict")
    print(f"  Window:    TRACK_B_DISCOVERY {tb_start} → {tb_end}")
    print(f"  Candidate: {_CAND_FACTORS}")
    print(
        f"             cadence={_CAND_CADENCE}  M={_CAND_M}  "
        f"smoothing={_CAND_SMOOTHING}  N={TRACK_A_BASELINE.target_positions}  regime ON"
    )
    print("  = Track-A baseline (B1+B2 dropped, TBE6 N/A — the single candidate)")
    print(f"  TBE3 anchor: Calmar={_TBE3_CALMAR}  Sharpe={_TBE3_SHARPE}")
    print("=" * 78)

    print("\nLoading prices_adjusted (offline cache)...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}", flush=True)

    print("Loading real Nifty 50 price index for regime (cached)...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(f"FAIL: regime index unavailable: {exc}", file=sys.stderr)
        return 2

    print("Loading Nifty200 Momentum 30 TRI (primary benchmark)...", flush=True)
    try:
        tri_nm30 = benchmark.load_tri(
            benchmark.TRI_MOMENTUM_30, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
    except Exception as exc:
        print(f"  WARNING: NM30 TRI unavailable: {exc}", file=sys.stderr)
        tri_nm30 = None

    # Shared v2 indicator cache (gate inputs) — built ONCE on the full window.
    cand_cfg = _candidate_cfg(tb_start, tb_end)
    print("Precomputing v2 indicator cache (shared gate)...", flush=True)
    ind = precompute_signals(prices, _engine_cfg(cand_cfg, tb_start, tb_end))._data

    print("Building candidate composite signal stores (smoothing 0, 2)...", flush=True)
    store_s0 = _build_store(prices, cand_cfg, ind)
    store_s2 = _build_store(prices, _candidate_cfg(tb_start, tb_end, smoothing=2), ind)
    store_smoothing = {0: store_s0, 2: store_s2}

    ledger = ConfigLedger()
    cand_eng = _engine_cfg(cand_cfg, tb_start, tb_end)

    # ------------------------------------------------------------------
    # Base run (base cost) — feeds §6.2 per_name_stats, §6.5 turnover, deflation,
    # and the wiring-sanity check vs the TBE3 anchor.
    # ------------------------------------------------------------------
    print("\nBase run (base cost, TRACK_B_DISCOVERY)...", flush=True)
    ledger.add(
        {"candidate": _CAND_FACTORS, "cost_level": "base"}, check="base_reference"
    )
    base_res, base_m = _run(prices, index_prices, cand_eng, store_s0, cost_level="base")
    print(
        f"  calmar={base_m.calmar:.3f}  cagr={base_m.cagr * 100:.1f}%"
        f"  maxdd={base_m.max_drawdown:.2%}  sharpe={base_m.sharpe:.3f}"
        f"  turnover={base_m.annualized_turnover * 100:.0f}%"
        f"  fills={base_m.n_fills}",
        flush=True,
    )

    calmar_ok = abs(base_m.calmar - _TBE3_CALMAR) < 0.005
    sharpe_ok = abs(base_m.sharpe - _TBE3_SHARPE) < 0.005
    if calmar_ok and sharpe_ok:
        print(
            f"  ✓ reproduces TBE3 anchor (Calmar {_TBE3_CALMAR} / "
            f"Sharpe {_TBE3_SHARPE}) — no wiring drift."
        )
    else:
        print(
            f"  ⚠ WARNING: base differs from TBE3 anchor "
            f"(Calmar {_TBE3_CALMAR} / Sharpe {_TBE3_SHARPE}). "
            f"calmar_ok={calmar_ok} sharpe_ok={sharpe_ok}. "
            "Investigate wiring drift before trusting TBE7 (Rule 12).",
            file=sys.stderr,
        )

    # Benchmark-relative context (primary benchmark NM30 TRI).
    if tri_nm30 is not None:
        try:
            trading_cal = [pd.Timestamp(s.date) for s in base_res.snapshots]
            bench_aligned = benchmark.align_benchmark(
                tri_nm30, tb_start, trading_cal, cand_cfg.starting_capital
            )
            bm = metrics.compute_benchmark_metrics(
                _equity_series(base_res), bench_aligned
            )
            print(
                f"  vs NM30 TRI: c_strat={bm.strategy_calmar:.3f}"
                f"  c_bench={bm.benchmark_calmar:.3f}"
                f"  calmar_ratio={bm.calmar_ratio:.2f}"
                f"  excess_cagr={bm.excess_cagr * 100:+.1f}%",
                flush=True,
            )
        except Exception as exc:
            print(f"  WARNING: benchmark alignment failed: {exc}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Five §6 checks
    # ------------------------------------------------------------------
    checks: list[CheckResult] = []

    print("\n§6.1 Cost stress (pessimistic cost)...", flush=True)
    checks.append(check_cost_stress(prices, index_prices, cand_eng, store_s0, ledger))

    print("§6.2 Universe perturbation (drop top-10 P&L names)...", flush=True)
    checks.append(
        check_universe_perturbation(
            prices, index_prices, cand_eng, store_s0, base_m, ledger
        )
    )

    print("§6.3 Parameter neighborhood (M × smoothing local grid)...", flush=True)
    checks.append(check_neighborhood_tb(prices, index_prices, ledger, store_smoothing))

    print("§6.4 Subperiod stability + concentration (3 market cycles)...", flush=True)
    sec64 = check_subperiod_stability_tb(prices, index_prices, store_s0, ledger)
    checks.append(sec64)

    print("§6.5 Turnover / capacity...", flush=True)
    checks.append(check_turnover_capacity(base_m))

    # ------------------------------------------------------------------
    # PBO via CSCV (config universe = §6.3 neighborhood × walk-forward folds)
    # ------------------------------------------------------------------
    print("\nPBO via CSCV (walk-forward folds on Track-B window)...", flush=True)
    pbo, n_pbo_configs, n_folds = compute_pbo(
        prices, index_prices, store_smoothing, ledger
    )
    print(
        f"  PBO={pbo:.2f}  (configs={n_pbo_configs}  folds={n_folds})",
        flush=True,
    )

    # ------------------------------------------------------------------
    # Deflation — K = prior (28) + this session's ledger entries.
    # ------------------------------------------------------------------
    k_total = _PRIOR_K + ledger.n_trials
    daily_returns = _equity_series(base_res).pct_change().dropna().to_numpy()
    raw_sharpe = base_m.sharpe
    dsr = deflated_sharpe(raw_sharpe, daily_returns, n_trials=k_total)

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    print()
    print("=" * 78)
    print("  TBE7 RESULTS — §6 battery on the locked Track-B candidate")
    print("=" * 78)
    print(f"\n  Candidate:  {_CAND_FACTORS}")
    print(
        f"              cadence={_CAND_CADENCE}  M={_CAND_M}  "
        f"smoothing={_CAND_SMOOTHING}  N={TRACK_A_BASELINE.target_positions}"
    )
    print("  = Track-A baseline (the single candidate; B1+B2 dropped, TBE6 N/A)")

    for cr in checks:
        _print_check(cr)

    n_pass = sum(1 for r in checks if r.passed)
    all_pass = n_pass == len(checks)
    print("\n" + "-" * 78)
    print(
        f"  §6 BATTERY: {n_pass}/{len(checks)} PASS"
        + ("  (all five)" if all_pass else "  (one or more FAILED)")
    )

    print("\n  Deflation (04 §5):")
    print(f"    Raw annualized Sharpe:  {raw_sharpe:.3f}")
    print(f"    K (trials, 28 prior + {ledger.n_trials} this file): {k_total}")
    print(f"    Deflated Sharpe (DSR):  {dsr:.3f}")
    print(
        "    DSR > 0 means the edge exceeds what selecting the best of K random "
        "draws would explain."
    )

    print("\n  PBO via CSCV (04 §5):")
    print(f"    PBO:      {pbo:.2f}  (configs={n_pbo_configs}  folds={n_folds})")
    print("    PBO > 0.5 → near-certain overfitting; near 0 → IS rank predicts OOS.")
    if n_folds <= 2:
        print(
            "    NOTE: only %d walk-forward folds fit the Track-B window at the "
            "default\n          24m-IS/6m-OOS cadence, so CSCV is coarse "
            "(C(2,1)=2 partitions). Reported\n          honestly as a weak, "
            "low-resolution estimate (Rule 12)." % n_folds
        )

    # ------------------------------------------------------------------
    # H3 verdict (03 §2 primary predicate) — the FINAL_OOS gate.
    # ------------------------------------------------------------------
    # The predicate is "pass §6.4 WHERE the TBE3 baseline FAILED." TBE3 found the
    # baseline UNEXPECTEDLY PASSES §6.4 → baseline never failed → predicate vacuous.
    # The candidate IS the baseline (identical config), so there is nothing to
    # show "passing where it failed." Both V/Q blocks dropped → no supporting
    # evidence. H3 cannot be confirmed regardless of the §6.4 PASS above.
    baseline_failed_sec64 = False  # TBE3 critical finding: baseline PASSES §6.4
    h3_confirmed = baseline_failed_sec64  # vacuous predicate → cannot be True

    print("\n" + "=" * 78)
    print("  H3 VERDICT (03 §2 primary predicate — the FINAL_OOS gate)")
    print("=" * 78)
    print("  Predicate: candidate passes §6.4 WHERE the TBE3 baseline FAILED §6.4.")
    print(
        "    • TBE3 baseline §6.4: PASSED (the critical 'unexpected pass' finding) "
        "→ never failed"
    )
    print(
        f"    • Candidate §6.4 here: {'PASS' if sec64.passed else 'FAIL'} "
        "(but the candidate IS the baseline — identical config)"
    )
    print("    • Supporting evidence (accepted V/Q layer): NONE (B1+B2 both dropped)")
    print(
        "  → The pass-where-baseline-failed predicate is VACUOUS (baseline never "
        "failed),\n    and there is no fundamental layer to add supporting evidence."
    )
    print(f"\n  H3 CONFIRMED: {h3_confirmed}  →  >>> H3 NOT CONFIRMED <<<")
    print("  TBE8 (FINAL_OOS): N/A — Track B closes as a research note (03 §9/§10).")
    print("  FINAL_OOS: UNTOUCHED — left PRISTINE (a legitimate research outcome).")
    print("=" * 78)

    print(f"\n  ConfigLedger K this session: {ledger.n_trials}")
    print(f"  Cumulative K (28 prior + {ledger.n_trials}): {k_total}")
    print("=" * 78)

    # TBE7 is a research-note close. The script always exits 0 (it completed its
    # job); the H3 verdict — not the process exit — is the scientific result.
    return 0


if __name__ == "__main__":
    sys.exit(main())
