"""
t6_robustness.py — v3 / Track-A T6: the five §6 robustness checks on the v3
candidate (the §6 gate before FINAL_OOS).

The candidate is the single config chosen by T5 (do NOT re-tune here — this is the
config UNDER TEST, not a new search, Rule 12):

    active_factors = ["mom_12_1", "low_vol", "trend_quality", "mom_6_1", "reversal"]
    cadence=monthly   M=70   smoothing=0   N=20   regime ON

Five checks (04 §6), reusing robustness.py's criteria and thresholds verbatim —
only the candidate config is adapted (prereg T6 do-item: "adapt the candidate
config, not the checks"):

    §6.1  Cost stress       — beats Nifty50 TRI Calmar at pessimistic cost
    §6.2  Universe perturb  — drop top-10 P&L names; Calmar retains >= 70%
    §6.3  Neighborhood      — plateau on candidate + immediate turnover-knob neighbors
    §6.4  Subperiod + conc. — >= 2/3 positive Calmar AND no single positive period
                              > 5x the mean of the others  (HARDENED — the v2 gap)
    §6.5  Turnover/capacity — avg trade participation < 5% of ADV floor

§6.3 note: v2's neighborhood varied the regime params (debounce, risk_off). v3
fixes the regime overlay, so the analogous "immediate neighbors" are the T4
turnover knobs the candidate was actually selected on — M ∈ {50, 70} and
smoothing ∈ {0, 2}, one grid step each around (M=70, smoothing=0), cadence held at
monthly (quarterly was a hard-rejected lone peak in T4, Calmar 0.019 — not a local
plateau probe). Same 2-axis structure, same plateau_check, same 0.85 tolerance.

§6.4 is HARDENED per the prereg (§6.4 predicate, 04 §4): the v2 coded check passed
on subperiod-positivity alone and missed that the edge was concentrated in one
regime. T6 adds `v3_config.passes_concentration_hard` as a second, hard gate.

DISCOVERY only — FINAL_OOS stays pristine for T7. Offline: prices and the regime
index load from the local cache; never live yfinance/NSE (Rule 5).

Run:
    backend/venv/bin/python -m app.backtest_v2.t6_robustness
"""

from __future__ import annotations

import logging
import math
import sys
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.iterate import GridPoint, plateau_check
from app.backtest_v2.robustness import (
    GLITCH_PNL_RATIO_THRESHOLD,
    MAX_ADV_PARTICIPATION_PCT,  # noqa: F401  (re-exported context for the report)
    N_TOP_CONTRIBUTORS,
    SUBPERIOD_MIN_POSITIVE,
    SUBPERIODS,
    UNIVERSE_PERTURB_THRESHOLD,
    CheckResult,
    check_turnover_capacity,
)
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.v3_config import V3Config, passes_concentration_hard
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

# Regime index range — same cache key as t4 / t5 (offline hit).
_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Plateau tolerance — the same 0.85 fraction T4 / T5 / the regime layer use (04 §4).
_TOL = 0.85

# ---------------------------------------------------------------------------
# CANDIDATE — the T5-chosen v3 config. LOCKED. This is the config under test.
# ---------------------------------------------------------------------------
_CAND_FACTORS: list[str] = [
    "mom_12_1",
    "low_vol",
    "trend_quality",
    "mom_6_1",
    "reversal",
]
_CAND_CADENCE = "monthly"
_CAND_M = 70
_CAND_SMOOTHING = 0

# T5 candidate fingerprint — the base candidate run here must reproduce these or
# there is wiring drift from T5; surface it before trusting T6 (Rule 12).
_T5_CAND_CALMAR = 0.396
_T5_CAND_TURNOVER = 9.56  # fraction (956%)
_T5_CAND_RETENTION = 0.32

# §6.3 neighborhood — immediate turnover-knob neighbors of (M=70, smoothing=0).
_NBR_M: list[int] = [50, 70]
_NBR_SMOOTHING: list[int] = [0, 2]


# ---------------------------------------------------------------------------
# Config plumbing (mirrors t5_factors — run scripts stay independent)
# ---------------------------------------------------------------------------


def _candidate_cfg(
    date_from: date,
    date_to: date,
    smoothing: int = _CAND_SMOOTHING,
    buffer_m: int = _CAND_M,
) -> V3Config:
    """The locked 5-factor candidate, optionally re-pointed in the §6.3 neighborhood
    (smoothing / buffer_m only — the factor set, cadence and N never move)."""
    return V3Config(
        sell_rank_buffer=buffer_m,
        rebalance_cadence=_CAND_CADENCE,
        rank_smoothing_months=smoothing,
        active_factors=list(_CAND_FACTORS),
        date_from=date_from,
        date_to=date_to,
    )


def _engine_cfg(v3cfg: V3Config, date_from: date, date_to: date) -> MomentumConfig:
    """Project the V3Config knobs the engine consumes onto a MomentumConfig
    (cadence → `rebalance`, buffer → `sell_rank_buffer`). Multi-factor ordering
    rides in via the signal_store, not this config."""
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
    """Run the v3 candidate (regime ON via use_regime_overlay + index_prices,
    matching exactly how T5 selected it)."""
    res = engine.run(
        prices,
        eng_cfg,
        index_prices=index_prices,
        cost_level=cost_level,
        signal_store=signal_store,
    )
    return res, metrics.compute_metrics(res)


# ---------------------------------------------------------------------------
# §6.1 Cost stress
# ---------------------------------------------------------------------------


def check_cost_stress(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    eng_cfg: MomentumConfig,
    signal_store,
    ledger: ConfigLedger,
) -> CheckResult:
    """§6.1: candidate beats Nifty50 TRI Calmar at pessimistic cost on DISCOVERY."""
    ledger.add(
        {"candidate": _CAND_FACTORS, "cost_level": "pessimistic"},
        check="§6.1_cost_stress",
    )
    result, _ = _run(
        prices, index_prices, eng_cfg, signal_store, cost_level="pessimistic"
    )

    trading_cal = [pd.Timestamp(s.date) for s in result.snapshots]
    tri = benchmark.load_tri(
        benchmark.TRI_NIFTY_50, _BENCH_FETCH_START, _BENCH_FETCH_END
    )
    bench = benchmark.align_benchmark(
        tri, eng_cfg.date_from, trading_cal, eng_cfg.starting_capital
    )
    bm = metrics.compute_benchmark_metrics(_equity_series(result), bench)

    passed = bm.calmar_ratio >= 1.0
    summary = (
        f"PASS — calmar_ratio {bm.calmar_ratio:.2f} >= 1.0 at pessimistic cost"
        if passed
        else (
            f"FAIL — calmar_ratio {bm.calmar_ratio:.2f} < 1.0: "
            "can't beat Nifty50 at worst-case cost"
        )
    )
    return CheckResult(
        name="§6.1 Cost stress",
        passed=passed,
        summary=summary,
        details={
            "cost_level": "pessimistic",
            "c_strat": round(bm.strategy_calmar, 3),
            "c_nifty50": round(bm.benchmark_calmar, 3),
            "calmar_ratio": round(bm.calmar_ratio, 2),
        },
    )


# ---------------------------------------------------------------------------
# §6.2 Universe perturbation
# ---------------------------------------------------------------------------


def check_universe_perturbation(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    eng_cfg: MomentumConfig,
    signal_store,
    base_metrics: metrics.BacktestMetrics,
    ledger: ConfigLedger,
) -> CheckResult:
    """§6.2: drop top-N realized-P&L names, re-run the SAME signal_store on the
    perturbed prices (engine derives its universe from prices → dropped ISINs are
    structurally excluded), retention = perturbed_calmar / base_calmar >= 70%."""
    sorted_names = sorted(
        base_metrics.per_name_stats, key=lambda ns: ns.realized_pnl, reverse=True
    )
    top_n = sorted_names[:N_TOP_CONTRIBUTORS]
    top_isins = {ns.isin for ns in top_n}
    top_symbols = [ns.symbol for ns in top_n]

    glitch_flags: list[str] = []
    for ns in top_n:
        if ns.buy_notional > 0:
            ratio = ns.realized_pnl / ns.buy_notional
            if ratio > GLITCH_PNL_RATIO_THRESHOLD:
                glitch_flags.append(f"{ns.symbol} pnl_ratio={ratio:.1f}x")

    prices_perturbed = prices[~prices["isin"].isin(top_isins)].copy()
    ledger.add(
        {"n_dropped": N_TOP_CONTRIBUTORS, "dropped_symbols": top_symbols},
        check="§6.2_universe_perturb",
    )
    _, m_perturbed = _run(
        prices_perturbed, index_prices, eng_cfg, signal_store, cost_level="base"
    )

    base_calmar = base_metrics.calmar
    if base_calmar > 0 and not math.isnan(base_calmar):
        retention = m_perturbed.calmar / base_calmar
    else:
        retention = float("nan")

    passed = (not math.isnan(retention)) and retention >= UNIVERSE_PERTURB_THRESHOLD
    summary = (
        f"PASS — Calmar retention {retention:.0%} >= {UNIVERSE_PERTURB_THRESHOLD:.0%} "
        f"after dropping top-{N_TOP_CONTRIBUTORS} names"
        if passed
        else (
            f"FAIL — Calmar retention {retention:.0%} < {UNIVERSE_PERTURB_THRESHOLD:.0%}: "
            "edge concentrated in top names"
        )
    )
    return CheckResult(
        name="§6.2 Universe perturbation",
        passed=passed,
        summary=summary,
        details={
            "base_calmar": round(base_calmar, 3),
            "perturbed_calmar": round(m_perturbed.calmar, 3),
            "calmar_retention": round(retention, 2)
            if not math.isnan(retention)
            else "n/a",
            "top_contributors": top_symbols,
            "glitch_flags": glitch_flags,
        },
    )


# ---------------------------------------------------------------------------
# §6.3 Parameter neighborhood (turnover knobs)
# ---------------------------------------------------------------------------


def check_neighborhood(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    ind,
    ledger: ConfigLedger,
    store_smoothing: dict[int, V3SignalStore],
) -> CheckResult:
    """§6.3: plateau check on the candidate + immediate turnover-knob neighbors —
    M ∈ {50, 70} × smoothing ∈ {0, 2}, cadence=monthly, 5-factor set fixed. Same
    plateau_check / tolerance as T4 / T5 so the criterion is identical."""
    combos = [(m, s) for m in _NBR_M for s in _NBR_SMOOTHING]
    points: list[GridPoint] = []
    for buffer_m, smoothing in combos:
        cfg = _candidate_cfg(
            DISCOVERY[0], DISCOVERY[1], smoothing=smoothing, buffer_m=buffer_m
        )
        eng_c = _engine_cfg(cfg, *DISCOVERY)
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
# §6.4 Subperiod stability + HARDENED concentration
# ---------------------------------------------------------------------------


def check_subperiod_stability(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    eng_cfg_for: dict,  # subperiod-label → MomentumConfig
    signal_store,
    ledger: ConfigLedger,
) -> CheckResult:
    """§6.4 HARDENED: needs (a) positive Calmar in >= 2/3 market-cycle subperiods
    AND (b) no single positive subperiod > 5x the mean of the others
    (`passes_concentration_hard`). v2's coded check tested only (a) and so missed
    single-regime concentration — T6 adds (b) as a hard gate (prereg §6.4)."""
    subresults: list[tuple[str, metrics.BacktestMetrics]] = []
    for label, start, end in SUBPERIODS:
        ledger.add(
            {"subperiod": label, "start": str(start), "end": str(end)},
            check="§6.4_subperiod",
        )
        eng_c = eng_cfg_for[label]
        _, m = _run(prices, index_prices, eng_c, signal_store, cost_level="base")
        subresults.append((label, m))
        log.info(
            "  Subperiod '%s': calmar=%.3f  cagr=%.2f%%", label, m.calmar, m.cagr * 100
        )

    calmars = [m.calmar for _, m in subresults]
    n_positive = sum(1 for c in calmars if not math.isnan(c) and c > 0)
    positivity_ok = n_positive >= SUBPERIOD_MIN_POSITIVE
    concentration_ok = passes_concentration_hard(
        [c for c in calmars if not math.isnan(c)]
    )
    passed = positivity_ok and concentration_ok

    calmar_map = {lbl: round(m.calmar, 3) for lbl, m in subresults}
    cagr_map = {lbl: round(m.cagr * 100, 2) for lbl, m in subresults}

    if passed:
        summary = (
            f"PASS — {n_positive}/{len(SUBPERIODS)} subperiods positive Calmar AND "
            "no single regime > 5x the mean of the others"
        )
    elif not positivity_ok:
        summary = (
            f"FAIL — only {n_positive}/{len(SUBPERIODS)} subperiods positive Calmar "
            f"(need >= {SUBPERIOD_MIN_POSITIVE}): single-regime trap"
        )
    else:
        summary = (
            "FAIL — concentration gate: one positive subperiod > 5x the mean of the "
            "others (edge is single-regime, the v2 §6.4 gap)"
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
            "calmar_per_subperiod": calmar_map,
            "cagr_per_subperiod_%": cagr_map,
        },
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(results: list[CheckResult]) -> None:
    print()
    print("=" * 78)
    print("  v3 / T6 — ROBUSTNESS BATTERY  (the §6 gate on the T5 candidate)")
    print(f"  Candidate: {_CAND_FACTORS}")
    print(
        f"             cadence={_CAND_CADENCE}  M={_CAND_M}  "
        f"smoothing={_CAND_SMOOTHING}  N=20  regime ON"
    )
    print(f"  Window:    DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    print("=" * 78)

    for cr in results:
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

    n_pass = sum(1 for r in results if r.passed)
    all_pass = n_pass == len(results)
    print()
    print("=" * 78)
    verdict = (
        "ALL PASS — T7 (FINAL_OOS) unblocked"
        if all_pass
        else f"{n_pass}/{len(results)} PASS — T7 BLOCKED (any §6 fail blocks OOS)"
    )
    print(f"  T6 OVERALL: >>> {verdict} <<<")
    print("=" * 78)


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

    print("v3 / T6 — Robustness battery on the v3 candidate (§6 gate)")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}  (regime ON)")
    print(
        f"  Candidate: {_CAND_FACTORS}  cadence={_CAND_CADENCE} M={_CAND_M} "
        f"smoothing={_CAND_SMOOTHING}"
    )
    print()

    print("Loading prices_adjusted (offline cache)...", flush=True)
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

    # Shared v2 indicator cache (gate inputs) — built ONCE, reused for every store.
    cand_cfg = _candidate_cfg(DISCOVERY[0], DISCOVERY[1])
    print("Precomputing v2 indicator cache on DISCOVERY (shared gate)...", flush=True)
    ind = precompute_signals(prices, _engine_cfg(cand_cfg, *DISCOVERY))._data

    # Candidate composite/store (smoothing=0) — reused by §6.1/§6.2/§6.4 and the
    # smoothing=0 column of §6.3. The smoothing=2 store is built for §6.3 only.
    print("Building candidate composite signal store...", flush=True)
    store_s0 = _build_store(prices, cand_cfg, ind)
    store_s2 = _build_store(
        prices, _candidate_cfg(DISCOVERY[0], DISCOVERY[1], smoothing=2), ind
    )

    ledger = ConfigLedger()
    cand_eng = _engine_cfg(cand_cfg, *DISCOVERY)

    # Base run (base cost) — feeds §6.2 per_name_stats and §6.5 turnover; also the
    # wiring-sanity check vs the T5 candidate fingerprint.
    print("Base run (base cost, DISCOVERY)...", flush=True)
    ledger.add(
        {"candidate": _CAND_FACTORS, "cost_level": "base"}, check="base_reference"
    )
    _, base_m = _run(prices, index_prices, cand_eng, store_s0, cost_level="base")
    base_turn = base_m.annualized_turnover
    print(
        f"  calmar={base_m.calmar:.3f}  turnover={base_turn * 100:.0f}%"
        f"  fills={base_m.n_fills}  maxdd={base_m.max_drawdown:.2%}",
        flush=True,
    )

    calmar_ok = abs(base_m.calmar - _T5_CAND_CALMAR) < 0.005
    turn_ok = abs(base_turn - _T5_CAND_TURNOVER) < 0.05
    if calmar_ok and turn_ok:
        print(
            f"  ✓ reproduces T5 candidate ({_T5_CAND_CALMAR} / "
            f"{_T5_CAND_TURNOVER * 100:.0f}%) — no drift."
        )
    else:
        print(
            f"  ⚠ WARNING: base differs from T5 candidate "
            f"({_T5_CAND_CALMAR} / {_T5_CAND_TURNOVER * 100:.0f}%). "
            f"calmar_ok={calmar_ok} turn_ok={turn_ok}. "
            "Investigate wiring drift before trusting T6 (Rule 12).",
            file=sys.stderr,
        )

    # Per-subperiod engine configs (windowed; same candidate store reused).
    eng_cfg_for = {
        label: _engine_cfg(_candidate_cfg(start, end), start, end)
        for label, start, end in SUBPERIODS
    }

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
    checks.append(
        check_neighborhood(
            prices,
            index_prices,
            ind,
            ledger,
            store_smoothing={0: store_s0, 2: store_s2},
        )
    )

    print("§6.4 Subperiod stability + concentration (3 market cycles)...", flush=True)
    checks.append(
        check_subperiod_stability(prices, index_prices, eng_cfg_for, store_s0, ledger)
    )

    print("§6.5 Turnover / capacity...", flush=True)
    checks.append(check_turnover_capacity(base_m))

    _print_report(checks)
    print(f"\n  Total trials in ledger (K): {ledger.n_trials}")
    print("  (K feeds deflated_sharpe at T7 — report raw Sharpe and K together.)")

    return 0 if all(c.passed for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
