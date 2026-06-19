"""
md2_battery.py — v3 / 05 MD2: Stage 2 full robustness battery on the §6.1 survivors.

Pre-registration: specs/v3/05_MOMENTUM_DEPLOY_PREREG.md §5/MD2.

Stage-2 set (from MD1):
    1. M=130, sm=0, monthly  — base Calmar 0.523, ratio 1.35
    2. M=200, sm=0, monthly  — base Calmar 0.550, ratio 1.45

For each survivor run:
  §6.2  Universe perturbation — drop top-10 P&L names; Calmar retention >= 70%
  §6.3  Neighborhood plateau  — adjacent §4 grid points stay >= 85% of base Calmar
                                (uses MD1 base Calmar table; no new runs for §4 points)
  §6.4  Subperiod stability   — 3 market-cycle periods (DIAGNOSTIC ONLY per prereg §2)
  §6.5  Turnover / capacity   — avg trade participation < 5% ADV floor
  §5-4  Deployment bar        — beats Nifty200 Momentum 30 TRI on base Calmar; maxDD <= 70%

§5 acceptance rule then selects the single locked candidate or declares the null close.

DISCOVERY only — FINAL_OOS stays pristine.

Run:
    backend/venv/bin/python -m app.backtest_v2.md2_battery
"""

from __future__ import annotations

import logging
import math
import sys
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.v3_config import TRACK_A_BASELINE, V3Config
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# ---------------------------------------------------------------------------
# §6.1 survivors from MD1 (these are the only configs that enter Stage 2)
# ---------------------------------------------------------------------------
STAGE2_SURVIVORS: list[tuple[int, int, str]] = [
    (130, 0, "monthly"),
    (200, 0, "monthly"),
]

# MD1 base Calmar table — all 12 §4 configs, used for §6.3 plateau without re-running.
# Source: MD1 session log (specs/v3/05_MOMENTUM_DEPLOY_PREREG.md §MD1).
# These were already logged to ConfigLedger in MD1 (K=24). No new K entries here.
_MD1_BASE_CALMAR: dict[tuple[int, int, str], float] = {
    (70, 0, "monthly"): 0.396,
    (70, 0, "quarterly"): 0.147,
    (70, 3, "monthly"): 0.304,
    (70, 3, "quarterly"): 0.158,
    (130, 0, "monthly"): 0.523,
    (130, 0, "quarterly"): 0.115,
    (130, 3, "monthly"): 0.272,
    (130, 3, "quarterly"): 0.166,
    (200, 0, "monthly"): 0.550,
    (200, 0, "quarterly"): 0.061,
    (200, 3, "monthly"): 0.187,
    (200, 3, "quarterly"): 0.086,
}

# §4 lever grids (for computing ±1 neighbors)
_M_GRID: list[int] = [70, 130, 200]
_SMOOTH_GRID: list[int] = [0, 3]
_CADENCE_GRID: list[str] = ["monthly", "quarterly"]

# §6.3 plateau tolerance
_PLATEAU_TOL: float = 0.85

# §6.2 retention threshold
_RETENTION_THRESHOLD: float = 0.70
_N_TOP_CONTRIBUTORS: int = 10

# §6.5 ADV floor
_MAX_ADV_PARTICIPATION_PCT: float = 5.0
_LIQUIDITY_FLOOR_CR: float = 5.0

# §6.4 subperiods — same as robustness.py, fixed before any run (Rule 12)
SUBPERIODS: list[tuple[str, date, date]] = [
    ("Pre-COVID chop", date(2018, 2, 6), date(2020, 3, 31)),
    ("Post-COVID bull", date(2020, 4, 1), date(2022, 1, 31)),
    ("Rate-hike correction", date(2022, 2, 1), date(2023, 6, 30)),
]


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass
class SurvivorResult:
    m: int
    smoothing: int
    cadence: str
    # Base run metrics
    base_calmar: float
    base_max_dd: float
    turnover_pct: float
    # §6.2
    s62_retention: float
    s62_perturbed_calmar: float
    s62_top_contributors: list[str]
    s62_passes: bool
    # §6.3
    s63_neighbors: dict[str, float]  # label → neighbor calmar
    s63_threshold: float
    s63_all_pass: bool
    s63_passes: bool
    # §6.4 (diagnostic only — not a gate)
    s64_calmar_per_period: dict[str, float]
    s64_n_positive: int
    s64_passes_concentration: bool  # reported but not gating
    # §6.5
    s65_participation_pct: float
    s65_passes: bool
    # Deployment bar (§5 item 4)
    dep_base_calmar_strat: float
    dep_base_calmar_bench: float
    dep_max_dd_strat: float
    dep_max_dd_bench: float
    dep_calmar_beats: bool
    dep_dd_ok: bool
    dep_passes: bool
    # Overall §5 verdict (§6.1 already confirmed by MD1)
    s5_passes: bool

    @property
    def label(self) -> str:
        return f"M={self.m} sm={self.smoothing} {self.cadence}"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _v3cfg(m: int, smoothing: int, cadence: str) -> V3Config:
    return V3Config(
        active_factors=list(TRACK_A_BASELINE.active_factors),
        rebalance_cadence=cadence,
        sell_rank_buffer=m,
        rank_smoothing_months=smoothing,
        target_positions=TRACK_A_BASELINE.target_positions,
        date_from=DISCOVERY[0],
        date_to=DISCOVERY[1],
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


# ---------------------------------------------------------------------------
# §6.3 Neighborhood plateau
# ---------------------------------------------------------------------------


def _get_neighbors(m: int, smoothing: int, cadence: str) -> list[tuple[int, int, str]]:
    """Return all adjacent §4 grid points (±1 step per lever dimension)."""
    nbrs: list[tuple[int, int, str]] = []
    m_idx = _M_GRID.index(m)
    sm_idx = _SMOOTH_GRID.index(smoothing)
    cad_idx = _CADENCE_GRID.index(cadence)

    if m_idx > 0:
        nbrs.append((_M_GRID[m_idx - 1], smoothing, cadence))
    if m_idx < len(_M_GRID) - 1:
        nbrs.append((_M_GRID[m_idx + 1], smoothing, cadence))
    if sm_idx > 0:
        nbrs.append((m, _SMOOTH_GRID[sm_idx - 1], cadence))
    if sm_idx < len(_SMOOTH_GRID) - 1:
        nbrs.append((m, _SMOOTH_GRID[sm_idx + 1], cadence))
    if cad_idx > 0:
        nbrs.append((m, smoothing, _CADENCE_GRID[cad_idx - 1]))
    if cad_idx < len(_CADENCE_GRID) - 1:
        nbrs.append((m, smoothing, _CADENCE_GRID[cad_idx + 1]))

    return nbrs


def check_s63_plateau(m: int, smoothing: int, cadence: str) -> dict:
    """
    §6.3: use MD1 base Calmar table. No new runs — neighbors are §4 points already logged.
    Returns a dict with: neighbors, threshold, all_pass, passes, neighbor_calmar_map.
    """
    base_calmar = _MD1_BASE_CALMAR[(m, smoothing, cadence)]
    threshold = base_calmar * _PLATEAU_TOL
    nbrs = _get_neighbors(m, smoothing, cadence)

    neighbor_calmar_map: dict[str, float] = {}
    all_pass = True
    for nm, nsm, ncad in nbrs:
        nc = _MD1_BASE_CALMAR[(nm, nsm, ncad)]
        lbl = f"M={nm} sm={nsm} {ncad}"
        neighbor_calmar_map[lbl] = nc
        if nc < threshold:
            all_pass = False

    return {
        "base_calmar": base_calmar,
        "threshold": round(threshold, 4),
        "neighbors": neighbor_calmar_map,
        "all_pass": all_pass,
        "passes": all_pass,
    }


# ---------------------------------------------------------------------------
# §6.4 Subperiod stability (diagnostic — no gate)
# ---------------------------------------------------------------------------


def run_s64_subperiods(
    m: int,
    smoothing: int,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    composite: pd.DataFrame,
    gate_ind,
    ledger: ConfigLedger,
) -> dict:
    """Run §6.4 subperiod stability. Diagnostic only — does NOT gate §5."""
    calmar_map: dict[str, float] = {}
    for label, sub_start, sub_end in SUBPERIODS:
        ledger.add(
            {
                "M": m,
                "smoothing": smoothing,
                "subperiod": label,
                "start": str(sub_start),
                "end": str(sub_end),
            },
            stage="MD2_s64_subperiod",
        )
        v3cfg_sub = V3Config(
            active_factors=list(TRACK_A_BASELINE.active_factors),
            rebalance_cadence="monthly",
            sell_rank_buffer=m,
            rank_smoothing_months=smoothing,
            target_positions=TRACK_A_BASELINE.target_positions,
            date_from=sub_start,
            date_to=sub_end,
        )
        eng_sub = _engine_cfg(v3cfg_sub, sub_start, sub_end)
        ss_sub = V3SignalStore(gate_ind, composite, v3cfg_sub)
        res_sub = engine.run(
            prices,
            eng_sub,
            index_prices=index_prices,
            cost_level="base",
            signal_store=ss_sub,
        )
        m_sub = metrics.compute_metrics(res_sub)
        calmar_map[label] = round(m_sub.calmar, 3)
        log.info("    §6.4  %-25s  calmar=%.3f", label, m_sub.calmar)

    n_positive = sum(1 for c in calmar_map.values() if not math.isnan(c) and c > 0)

    # passes_concentration_hard: no single subperiod > 5× mean of others
    pos_calmars = [c for c in calmar_map.values() if c > 0]
    conc_hard_pass = True
    if len(pos_calmars) >= 2:
        for i, c in enumerate(pos_calmars):
            others = [x for j, x in enumerate(pos_calmars) if j != i]
            if c > 5.0 * (sum(others) / len(others)):
                conc_hard_pass = False

    return {
        "calmar_per_period": calmar_map,
        "n_positive": n_positive,
        "passes_concentration": conc_hard_pass,
    }


# ---------------------------------------------------------------------------
# §6.5 Turnover / capacity
# ---------------------------------------------------------------------------


def check_s65(m_metrics: metrics.BacktestMetrics) -> dict:
    capital = m_metrics.start_equity or 1_000_000.0
    years = m_metrics.n_calendar_days / 365.25
    n_fills = max(m_metrics.n_fills, 1)
    total_one_way = capital * m_metrics.annualized_turnover * years / 2.0
    avg_trade = total_one_way / n_fills
    adv_floor_inr = _LIQUIDITY_FLOOR_CR * 1e7
    participation_pct = (avg_trade / adv_floor_inr) * 100.0
    passes = participation_pct < _MAX_ADV_PARTICIPATION_PCT
    return {
        "turnover_pct": round(m_metrics.annualized_turnover * 100, 1),
        "n_fills": m_metrics.n_fills,
        "avg_trade_inr": round(avg_trade, 0),
        "participation_pct": round(participation_pct, 3),
        "passes": passes,
    }


# ---------------------------------------------------------------------------
# Full battery for one survivor
# ---------------------------------------------------------------------------


def run_survivor(
    m: int,
    smoothing: int,
    cadence: str,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    tri_momentum30: pd.Series,
    composite: pd.DataFrame,
    gate_ind,
    ledger: ConfigLedger,
) -> SurvivorResult:
    v3cfg = _v3cfg(m, smoothing, cadence)
    eng = _engine_cfg(v3cfg, *DISCOVERY)
    ss = V3SignalStore(gate_ind, composite, v3cfg)

    # -- Base run (needed for §6.2 per_name_stats, §6.5, deployment bar) --
    log.info("  [base run] M=%d sm=%d %s ...", m, smoothing, cadence)
    ledger.add(
        {"M": m, "smoothing": smoothing, "cadence": cadence, "cost_level": "base"},
        stage="MD2_base",
    )
    res_base = engine.run(
        prices, eng, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    m_base = metrics.compute_metrics(res_base)
    log.info(
        "    base calmar=%.3f  maxdd=%.1f%%  turn=%.0f%%  sharpe=%.3f",
        m_base.calmar,
        m_base.max_drawdown * 100,
        m_base.annualized_turnover * 100,
        m_base.sharpe,
    )

    # -- §6.2 Universe perturbation --
    log.info("  [§6.2] top-%d drop ...", _N_TOP_CONTRIBUTORS)
    sorted_names = sorted(
        m_base.per_name_stats, key=lambda ns: ns.realized_pnl, reverse=True
    )
    top_n = sorted_names[:_N_TOP_CONTRIBUTORS]
    top_isins: set[str] = {ns.isin for ns in top_n}
    top_symbols: list[str] = [ns.symbol for ns in top_n]

    prices_perturbed = prices[~prices["isin"].isin(top_isins)].copy()
    ledger.add(
        {
            "M": m,
            "smoothing": smoothing,
            "cadence": cadence,
            "n_dropped": _N_TOP_CONTRIBUTORS,
            "dropped_symbols": top_symbols,
        },
        stage="MD2_s62_perturb",
    )
    res_perturb = engine.run(
        prices_perturbed,
        eng,
        index_prices=index_prices,
        cost_level="base",
        signal_store=ss,
    )
    m_perturb = metrics.compute_metrics(res_perturb)

    base_calmar = m_base.calmar
    if base_calmar > 0 and not math.isnan(base_calmar):
        retention = m_perturb.calmar / base_calmar
    else:
        retention = float("nan")
    s62_passes = (not math.isnan(retention)) and retention >= _RETENTION_THRESHOLD
    log.info(
        "    §6.2  perturbed calmar=%.3f  retention=%.0f%%  %s",
        m_perturb.calmar,
        retention * 100 if not math.isnan(retention) else float("nan"),
        "PASS" if s62_passes else "FAIL",
    )

    # -- §6.3 Neighborhood plateau (MD1 table, no new runs) --
    s63 = check_s63_plateau(m, smoothing, cadence)
    log.info(
        "    §6.3  threshold=%.4f  all_nbr_pass=%s  %s",
        s63["threshold"],
        s63["all_pass"],
        "PASS" if s63["passes"] else "FAIL",
    )
    for lbl, nc in s63["neighbors"].items():
        log.info(
            "          neighbor %-28s calmar=%.3f  %s",
            lbl,
            nc,
            "ok" if nc >= s63["threshold"] else "BELOW",
        )

    # -- §6.4 Subperiod stability (diagnostic only) --
    log.info("  [§6.4] subperiod stability (diagnostic) ...")
    s64 = run_s64_subperiods(
        m, smoothing, prices, index_prices, composite, gate_ind, ledger
    )

    # -- §6.5 Turnover / capacity --
    s65 = check_s65(m_base)
    log.info(
        "    §6.5  participation=%.3f%%  %s",
        s65["participation_pct"],
        "PASS" if s65["passes"] else "FAIL",
    )

    # -- Deployment bar (§5 item 4): Nifty200 Momentum 30, base cost --
    trading_cal = [pd.Timestamp(s.date) for s in res_base.snapshots]
    bench_aligned = benchmark.align_benchmark(
        tri_momentum30, eng.date_from, trading_cal, eng.starting_capital
    )
    bm = metrics.compute_benchmark_metrics(_equity_series(res_base), bench_aligned)
    dep_calmar_beats = bm.strategy_calmar > bm.benchmark_calmar
    dep_dd_ok = bm.max_dd_ratio <= 0.70
    dep_passes = dep_calmar_beats and dep_dd_ok
    log.info(
        "    §5-4  C_strat=%.3f  C_bench=%.3f  calmar_beats=%s  dd_ratio=%.2f  %s",
        bm.strategy_calmar,
        bm.benchmark_calmar,
        dep_calmar_beats,
        bm.max_dd_ratio,
        "PASS" if dep_passes else "FAIL",
    )

    # -- §5 acceptance rule --
    # §6.1 already confirmed (MD1 filter); §6.4 is diagnostic-only (not gating)
    s5_passes = s62_passes and s63["passes"] and s65["passes"] and dep_passes

    return SurvivorResult(
        m=m,
        smoothing=smoothing,
        cadence=cadence,
        base_calmar=m_base.calmar,
        base_max_dd=m_base.max_drawdown,
        turnover_pct=m_base.annualized_turnover * 100,
        # §6.2
        s62_retention=retention,
        s62_perturbed_calmar=m_perturb.calmar,
        s62_top_contributors=top_symbols,
        s62_passes=s62_passes,
        # §6.3
        s63_neighbors=s63["neighbors"],
        s63_threshold=s63["threshold"],
        s63_all_pass=s63["all_pass"],
        s63_passes=s63["passes"],
        # §6.4 (diagnostic)
        s64_calmar_per_period=s64["calmar_per_period"],
        s64_n_positive=s64["n_positive"],
        s64_passes_concentration=s64["passes_concentration"],
        # §6.5
        s65_participation_pct=s65["participation_pct"],
        s65_passes=s65["passes"],
        # Deployment bar
        dep_base_calmar_strat=bm.strategy_calmar,
        dep_base_calmar_bench=bm.benchmark_calmar,
        dep_max_dd_strat=bm.strategy_max_dd,
        dep_max_dd_bench=bm.benchmark_max_dd,
        dep_calmar_beats=dep_calmar_beats,
        dep_dd_ok=dep_dd_ok,
        dep_passes=dep_passes,
        # §5
        s5_passes=s5_passes,
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(results: list[SurvivorResult]) -> None:
    sep = "=" * 80

    print()
    print(sep)
    print(
        "  MD2 Stage 2 — Full battery on §6.1 survivors  (DISCOVERY 2018-02-06 → 2023-06-30)"
    )
    print("  §6.4 is DIAGNOSTIC ONLY (prereg §2 — demoted due to window-fragility)")
    print(sep)

    for r in results:
        print(f"\n{'─' * 70}")
        print(
            f"  Config: {r.label}  (base Calmar {r.base_calmar:.3f}, "
            f"turnover {r.turnover_pct:.0f}%)"
        )

        # §6.2
        ret_pct = f"{r.s62_retention:.0%}" if not math.isnan(r.s62_retention) else "n/a"
        print(f"\n  §6.2  Universe perturbation — {'PASS' if r.s62_passes else 'FAIL'}")
        print(
            f"        perturbed calmar={r.s62_perturbed_calmar:.3f}  "
            f"retention={ret_pct} (threshold ≥70%)"
        )
        print(f"        dropped: {r.s62_top_contributors}")

        # §6.3
        print(f"\n  §6.3  Neighborhood plateau — {'PASS' if r.s63_passes else 'FAIL'}")
        print(f"        threshold={r.s63_threshold:.4f} (85% × {r.base_calmar:.3f})")
        for lbl, nc in r.s63_neighbors.items():
            ok = nc >= r.s63_threshold
            print(f"        {'ok  ' if ok else 'FAIL'} {lbl:30s}  calmar={nc:.3f}")

        # §6.4 (diagnostic)
        print("\n  §6.4  Subperiod stability — DIAGNOSTIC (not gating)")
        print(
            f"        concentration_hard_pass={r.s64_passes_concentration}  "
            f"n_positive={r.s64_n_positive}/3"
        )
        for period, c in r.s64_calmar_per_period.items():
            print(f"        {period:30s}  calmar={c:.3f}")

        # §6.5
        print(f"\n  §6.5  Turnover / capacity — {'PASS' if r.s65_passes else 'FAIL'}")
        print(
            f"        participation={r.s65_participation_pct:.3f}% (threshold <5% ADV floor)"
        )

        # Deployment bar
        print(
            f"\n  §5-4  Deployment bar (Nifty200 Mom30, base cost) — {'PASS' if r.dep_passes else 'FAIL'}"
        )
        print(
            f"        C_strat={r.dep_base_calmar_strat:.3f}  "
            f"C_bench={r.dep_base_calmar_bench:.3f}  "
            f"calmar_beats={r.dep_calmar_beats}"
        )
        print(
            f"        maxDD_strat={r.dep_max_dd_strat:.1%}  "
            f"maxDD_bench={r.dep_max_dd_bench:.1%}  "
            f"dd_ratio={r.dep_max_dd_strat / r.dep_max_dd_bench:.2f}  (threshold ≤0.70)"
        )

        # §5 verdict
        print(
            f"\n  §5 VERDICT: {'PASS — qualifies for OOS candidate' if r.s5_passes else 'FAIL — eliminated'}"
        )
        if not r.s5_passes:
            fails = []
            if not r.s62_passes:
                fails.append("§6.2")
            if not r.s63_passes:
                fails.append("§6.3")
            if not r.s65_passes:
                fails.append("§6.5")
            if not r.dep_passes:
                fails.append("deployment bar")
            print(f"        Failed gates: {', '.join(fails)}")

    # Overall §5 outcome
    candidates = [r for r in results if r.s5_passes]
    print()
    print(sep)
    if not candidates:
        print("  §5 OUTCOME: NULL CLOSE")
        print("  Zero configs satisfy §5 items 1–4 on full DISCOVERY.")
        print("  Per prereg §5: momentum-only closes as a research note.")
        print("  FINAL_OOS remains pristine and untouched.")
        print(
            "  This is a pre-accepted, honest finding — no stick moved, no lever added."
        )
    elif len(candidates) == 1:
        c = candidates[0]
        print(f"  §5 OUTCOME: SINGLE LOCKED CANDIDATE → {c.label}")
        print("  Proceeds to MD3 (one-shot FINAL_OOS).")
    else:
        # Tie-break: lowest realized turnover
        winner = min(candidates, key=lambda r: r.turnover_pct)
        print(
            f"  §5 OUTCOME: {len(candidates)} configs pass — tie-break (lowest turnover)."
        )
        print(
            f"  LOCKED CANDIDATE → {winner.label}  (turnover {winner.turnover_pct:.0f}%)"
        )
    print(sep)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


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

    print("v3 / 05 MD2 — Stage 2: full battery on §6.1 survivors")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    print(f"  Survivors: {STAGE2_SURVIVORS}")
    print()

    print("Loading prices_adjusted (offline cache)...", flush=True)
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

    print("Loading Nifty 50 price index (regime overlay)...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(f"FAIL: regime index unavailable: {exc}", file=sys.stderr)
        return 2

    print("Loading Nifty200 Momentum 30 TRI (§5 deployment bar)...", flush=True)
    try:
        tri_momentum30 = benchmark.load_tri(
            benchmark.TRI_MOMENTUM_30, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
    except Exception as exc:
        print(f"FAIL: Nifty200 Momentum 30 TRI unavailable: {exc}", file=sys.stderr)
        return 2

    # Shared v2 indicator cache (gate inputs — same for all configs)
    ref_v3cfg = TRACK_A_BASELINE
    ref_eng = _engine_cfg(ref_v3cfg, *DISCOVERY)
    print("Precomputing v2 gate indicator cache (DISCOVERY, shared)...", flush=True)
    gate_store = precompute_signals(prices, ref_eng)
    gate_ind = gate_store._data

    ledger = ConfigLedger()

    results: list[SurvivorResult] = []
    for i, (m, smoothing, cadence) in enumerate(STAGE2_SURVIVORS, 1):
        print(
            f"\n[{i}/{len(STAGE2_SURVIVORS)}] Running battery: M={m} sm={smoothing} {cadence}",
            flush=True,
        )

        # Composite cache per smoothing value
        v3cfg_tmp = V3Config(
            active_factors=list(TRACK_A_BASELINE.active_factors),
            rebalance_cadence=cadence,
            sell_rank_buffer=m,
            rank_smoothing_months=smoothing,
            target_positions=TRACK_A_BASELINE.target_positions,
        )
        composite = factors.composite_rank(prices, v3cfg_tmp)

        sr = run_survivor(
            m,
            smoothing,
            cadence,
            prices,
            index_prices,
            tri_momentum30,
            composite,
            gate_ind,
            ledger,
        )
        results.append(sr)

    _print_report(results)

    # K accounting
    print(f"\n  MD2 new ConfigLedger entries (K this run): {ledger.n_trials}")
    print(
        "  Cumulative K at MD3 = Track-A T1–T6 entries + TBE3 entries + MD1 K=24 + MD2 K above."
    )
    print("  FINAL_OOS untouched.")

    candidates = [r for r in results if r.s5_passes]
    return 0 if len(candidates) >= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
