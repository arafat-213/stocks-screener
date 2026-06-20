"""
su2_battery.py — v3 / 08 SU2: Stage 2 full robustness battery on the §6.1 survivors.

Pre-registration: specs/v3/08_STABLE_UNIVERSE_PREREG.md §5 (Stage 2) / §6 / §13 SU2.

Stage-2 set (from SU1 — §6.1 ratio ≥ 1.0 on Nifty50 TRI):
    C0  floor (status quo, re-floored daily)   — base Calmar 0.523, ratio 1.35  (anchor/control)
    S2  stable U=200 B=1.00 semi-annual         — base Calmar 0.457, ratio 1.15
    S3  stable U=350 B=1.25 semi-annual         — base Calmar 0.575, ratio 1.51
(S1 U=200 B=1.25 was DROPPED at SU1: §6.1 ratio 0.96.)

Momentum is held constant at the `06` MD1 §6.1 survivor (5-factor, N=20, M=130,
sm=0, monthly, regime ON, ₹5cr floor). The ONLY axis that varies is the universe
(mode / U / B). This mirrors md2_battery.py but on the universe axis.

For each survivor:
  §6.2  Universe perturbation — drop top-10 P&L names; Calmar retention >= 70%
                                (concentration gate — NOT relaxed, 08 §2b)
  §6.3  Neighborhood plateau  — §5 universe-neighbors (±1 step on U and B) stay
                                >= 85% of base Calmar, reusing the SU1 base-Calmar
                                table (no new runs — the §5 points are already logged).
                                C0 is the off-lattice floor control → no §5 universe
                                neighbors → §6.3 N/A (reported, see 08 §6.3 caveat).
  §6.4  Subperiod stability   — 3 market-cycle periods (DIAGNOSTIC ONLY, 08 §2b/§7)
  §6.5  Turnover / capacity   — avg trade participation < 5% ADV floor
  §6-4  Deployment bar (08 §2b/§6.4): beats Nifty200 Momentum 30 TRI on base Calmar
                                AND maxDD <= 100% of benchmark (CORRECTED from MD2's 70%)

§6 acceptance items 1–5 then select the single locked candidate or declare the null
close (lowest-churn tie-break). DISCOVERY only — FINAL_OOS stays pristine.

Run:
    backend/venv/bin/python -m app.backtest_v2.su2_battery
"""

from __future__ import annotations

import logging
import math
import sys
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.stable_universe import build_stable_universe_mask
from app.backtest_v2.v3_config import TRACK_A_BASELINE, V3Config
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Held-constant momentum construction (08 §3) — the MD1 §6.1 survivor, NOT searched.
_M = 130
_SMOOTHING = 0
_CADENCE = "monthly"

# §6.2 retention threshold (08 §6 item 2 — NOT relaxed).
_RETENTION_THRESHOLD = 0.70
_N_TOP_CONTRIBUTORS = 10

# §6.3 plateau tolerance (08 §6 item 3).
_PLATEAU_TOL = 0.85

# §6.5 ADV floor capacity check.
_MAX_ADV_PARTICIPATION_PCT = 5.0
_LIQUIDITY_FLOOR_CR = 5.0

# §6.4 subperiods — identical to md2_battery / robustness, fixed before any run (Rule 12).
SUBPERIODS: list[tuple[str, date, date]] = [
    ("Pre-COVID chop", date(2018, 2, 6), date(2020, 3, 31)),
    ("Post-COVID bull", date(2020, 4, 1), date(2022, 1, 31)),
    ("Rate-hike correction", date(2022, 2, 1), date(2023, 6, 30)),
]

# ---------------------------------------------------------------------------
# SU1 base-Calmar table (all 4 §5 configs, already logged to ConfigLedger in
# SU1 — reused for §6.3 plateau without re-running, exactly as MD2 reused MD1).
# Source: 08 §13 SU1 session log.
# ---------------------------------------------------------------------------
_SU1_BASE_CALMAR: dict[str, float] = {
    "C0": 0.523,
    "S1": 0.391,
    "S2": 0.457,
    "S3": 0.575,
}

# §5 universe-lattice neighbors (±1 step in U OR B among the §5 stable points).
# The §5 grid is sparse: U∈{200,350}, B∈{1.0,1.25}, but only S1(200,1.25),
# S2(200,1.0), S3(350,1.25) exist — (350,1.0) was never enumerated, so some
# ±1 steps land off-grid and are reported as "absent" (08 §6.3 caveat).
# C0 (floor) is off the stable lattice entirely → no universe neighbors.
_S5_NEIGHBORS: dict[str, list[str]] = {
    "S2": ["S1"],  # +B → S1(200,1.25);  +U → (350,1.0) absent from §5 grid
    "S3": ["S1"],  # −U → S1(200,1.25);  −B → (350,1.0) absent from §5 grid
}


@dataclass
class SU2Config:
    name: str
    universe_mode: str
    universe_size_U: int
    universe_buffer_B: float
    role: str

    @property
    def universe_label(self) -> str:
        if self.universe_mode == "floor":
            return "₹5cr floor (daily)"
        return f"stable U={self.universe_size_U} B={self.universe_buffer_B:g}"


# §6.1 survivors from SU1 (S1 dropped at 0.96).
_SURVIVORS: list[SU2Config] = [
    SU2Config("C0", "floor", 0, 0.0, "anchor/control (churning floor)"),
    SU2Config("S2", "stable", 200, 1.00, "stable, hard review"),
    SU2Config("S3", "stable", 350, 1.25, "stable, broader"),
]


@dataclass
class SurvivorResult:
    name: str
    universe_label: str
    base_calmar: float
    base_max_dd: float
    turnover_pct: float
    # §6.2
    s62_retention: float
    s62_perturbed_calmar: float
    s62_top_contributors: list[str]
    s62_passes: bool
    # §6.3 (N/A for C0 — off-lattice control)
    s63_applicable: bool
    s63_neighbors: dict[str, float]
    s63_absent: list[str]
    s63_threshold: float
    s63_passes: bool | None
    # §6.4 (diagnostic only)
    s64_calmar_per_period: dict[str, float] = field(default_factory=dict)
    s64_n_positive: int = 0
    s64_passes_concentration: bool = False
    # §6.5
    s65_participation_pct: float = 0.0
    s65_passes: bool = False
    # Deployment bar (08 §2b/§6.4 — maxDD ≤ 100%)
    dep_calmar_strat: float = 0.0
    dep_calmar_bench: float = 0.0
    dep_max_dd_strat: float = 0.0
    dep_max_dd_bench: float = 0.0
    dep_dd_ratio: float = 0.0
    dep_calmar_beats: bool = False
    dep_dd_ok: bool = False
    dep_passes: bool = False
    # §6 verdict (§6.1 already confirmed by SU1)
    s6_passes: bool = False


# ---------------------------------------------------------------------------
# Config plumbing (mirrors su1_cost_screen)
# ---------------------------------------------------------------------------


def _v3_config(cfg: SU2Config, date_from: date, date_to: date) -> V3Config:
    return V3Config(
        active_factors=list(TRACK_A_BASELINE.active_factors),
        rebalance_cadence=_CADENCE,
        sell_rank_buffer=_M,
        rank_smoothing_months=_SMOOTHING,
        target_positions=TRACK_A_BASELINE.target_positions,
        use_regime_overlay=True,
        catastrophic_stop_pct=25.0,
        liquidity_floor_cr=5.0,
        universe_mode=cfg.universe_mode,
        universe_size_U=cfg.universe_size_U if cfg.universe_mode == "stable" else 200,
        universe_buffer_B=cfg.universe_buffer_B
        if cfg.universe_mode == "stable"
        else 1.25,
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


def _build_mask(v3cfg: V3Config):
    """Point-in-time stable mask (None for the floor control)."""
    if v3cfg.universe_mode != "stable":
        return None
    return build_stable_universe_mask(
        prices_for_mask,  # bound in main() — module global set once on full prices
        v3cfg.universe_size_U,
        v3cfg.universe_buffer_B,
        v3cfg.universe_rank_lookback_td,
        v3cfg.universe_review_cadence,
    )


# Module-level handle so the mask is built once per config from full-window prices
# (point-in-time membership is causal — the same mask serves base / perturbed /
# subperiod runs; the engine queries it by date).
prices_for_mask: pd.DataFrame | None = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# §6.3 Neighborhood plateau (reuse SU1 table — no new runs)
# ---------------------------------------------------------------------------


def check_s63_plateau(name: str) -> dict:
    """§5 universe-neighbor plateau from the SU1 base-Calmar table.

    Returns applicable=False for C0 (off-lattice floor control — no §5 universe
    neighbors). For stable configs the present neighbors must each stay ≥ 85% of
    the config's own base Calmar.
    """
    if name not in _S5_NEIGHBORS:
        return {
            "applicable": False,
            "threshold": float("nan"),
            "neighbors": {},
            "absent": [],
            "passes": None,
        }
    base = _SU1_BASE_CALMAR[name]
    threshold = base * _PLATEAU_TOL
    neighbor_map: dict[str, float] = {}
    passes = True
    for nb in _S5_NEIGHBORS[name]:
        nc = _SU1_BASE_CALMAR[nb]
        neighbor_map[nb] = nc
        if nc < threshold:
            passes = False
    # Off-grid ±1 steps that were never enumerated in §5 (the (350,1.0) corner).
    absent = ["U=350 B=1.0 (+U step)" if name == "S2" else "U=350 B=1.0 (−B step)"]
    return {
        "applicable": True,
        "threshold": round(threshold, 4),
        "neighbors": neighbor_map,
        "absent": absent,
        "passes": passes,
    }


# ---------------------------------------------------------------------------
# §6.4 Subperiod stability (diagnostic — no gate)
# ---------------------------------------------------------------------------


def run_s64_subperiods(
    cfg: SU2Config,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    composite: pd.DataFrame,
    gate_ind,
    mask,
    ledger: ConfigLedger,
) -> dict:
    calmar_map: dict[str, float] = {}
    for label, sub_start, sub_end in SUBPERIODS:
        ledger.add(
            {
                "config": cfg.name,
                "M": _M,
                "smoothing": _SMOOTHING,
                "subperiod": label,
                "start": str(sub_start),
                "end": str(sub_end),
            },
            stage="SU2_s64_subperiod",
        )
        v3cfg_sub = _v3_config(cfg, sub_start, sub_end)
        eng_sub = _engine_cfg(v3cfg_sub, sub_start, sub_end)
        ss_sub = V3SignalStore(gate_ind, composite, v3cfg_sub, universe_mask=mask)
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
    return {
        "participation_pct": round(participation_pct, 3),
        "passes": participation_pct < _MAX_ADV_PARTICIPATION_PCT,
    }


# ---------------------------------------------------------------------------
# Full battery for one survivor
# ---------------------------------------------------------------------------


def run_survivor(
    cfg: SU2Config,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    tri_momentum30: pd.Series,
    composite: pd.DataFrame,
    gate_ind,
    ledger: ConfigLedger,
) -> SurvivorResult:
    v3cfg = _v3_config(cfg, *DISCOVERY)
    eng = _engine_cfg(v3cfg, *DISCOVERY)
    mask = _build_mask(v3cfg)
    ss = V3SignalStore(gate_ind, composite, v3cfg, universe_mask=mask)

    payload = {
        "config": cfg.name,
        "universe_mode": v3cfg.universe_mode,
        "U": v3cfg.universe_size_U if v3cfg.universe_mode == "stable" else None,
        "B": v3cfg.universe_buffer_B if v3cfg.universe_mode == "stable" else None,
        "M": _M,
        "smoothing": _SMOOTHING,
        "cadence": _CADENCE,
    }

    # -- Base run --
    log.info("  [base run] %s — %s ...", cfg.name, cfg.universe_label)
    ledger.add({**payload, "cost_level": "base"}, stage="SU2_base")
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

    # -- §6.2 Universe perturbation (drop top-10 P&L names) --
    log.info("  [§6.2] top-%d drop ...", _N_TOP_CONTRIBUTORS)
    sorted_names = sorted(
        m_base.per_name_stats, key=lambda ns: ns.realized_pnl, reverse=True
    )
    top_n = sorted_names[:_N_TOP_CONTRIBUTORS]
    top_isins = {ns.isin for ns in top_n}
    top_symbols = [ns.symbol for ns in top_n]
    prices_perturbed = prices[~prices["isin"].isin(top_isins)].copy()
    ledger.add(
        {**payload, "n_dropped": _N_TOP_CONTRIBUTORS, "dropped_symbols": top_symbols},
        stage="SU2_s62_perturb",
    )
    res_perturb = engine.run(
        prices_perturbed,
        eng,
        index_prices=index_prices,
        cost_level="base",
        signal_store=ss,
    )
    m_perturb = metrics.compute_metrics(res_perturb)
    if m_base.calmar > 0 and not math.isnan(m_base.calmar):
        retention = m_perturb.calmar / m_base.calmar
    else:
        retention = float("nan")
    s62_passes = (not math.isnan(retention)) and retention >= _RETENTION_THRESHOLD
    log.info(
        "    §6.2  perturbed calmar=%.3f  retention=%.0f%%  %s",
        m_perturb.calmar,
        retention * 100 if not math.isnan(retention) else float("nan"),
        "PASS" if s62_passes else "FAIL",
    )

    # -- §6.3 Neighborhood plateau (SU1 table, no new runs) --
    s63 = check_s63_plateau(cfg.name)
    if s63["applicable"]:
        log.info(
            "    §6.3  threshold=%.4f  %s",
            s63["threshold"],
            "PASS" if s63["passes"] else "FAIL",
        )
        for lbl, nc in s63["neighbors"].items():
            log.info(
                "          neighbor %-6s calmar=%.3f  %s",
                lbl,
                nc,
                "ok" if nc >= s63["threshold"] else "BELOW",
            )
    else:
        log.info("    §6.3  N/A — C0 is the off-lattice floor control (08 §6.3)")

    # -- §6.4 Subperiod stability (diagnostic) --
    log.info("  [§6.4] subperiod stability (diagnostic) ...")
    s64 = run_s64_subperiods(
        cfg, prices, index_prices, composite, gate_ind, mask, ledger
    )

    # -- §6.5 Turnover / capacity --
    s65 = check_s65(m_base)
    log.info(
        "    §6.5  participation=%.3f%%  %s",
        s65["participation_pct"],
        "PASS" if s65["passes"] else "FAIL",
    )

    # -- Deployment bar (08 §2b/§6.4): Nifty200 Mom30, base cost, maxDD ≤ 100% --
    trading_cal = [pd.Timestamp(s.date) for s in res_base.snapshots]
    bench_aligned = benchmark.align_benchmark(
        tri_momentum30, eng.date_from, trading_cal, eng.starting_capital
    )
    bm = metrics.compute_benchmark_metrics(_equity_series(res_base), bench_aligned)
    dep_calmar_beats = bm.strategy_calmar > bm.benchmark_calmar
    dep_dd_ok = (not math.isnan(bm.max_dd_ratio)) and bm.max_dd_ratio <= 1.0
    dep_passes = dep_calmar_beats and dep_dd_ok
    log.info(
        "    §6-4  C_strat=%.3f  C_bench=%.3f  beats=%s  dd_ratio=%.2f (≤1.0)  %s",
        bm.strategy_calmar,
        bm.benchmark_calmar,
        dep_calmar_beats,
        bm.max_dd_ratio,
        "PASS" if dep_passes else "FAIL",
    )

    # -- §6 acceptance (items 1–5; §6.1 already PASS via SU1; §6.4 diagnostic) --
    # For C0, §6.3 is N/A — it cannot be the locked stable-universe candidate.
    s63_ok = bool(s63["passes"]) if s63["applicable"] else False
    s6_passes = s62_passes and s63_ok and s65["passes"] and dep_passes

    return SurvivorResult(
        name=cfg.name,
        universe_label=cfg.universe_label,
        base_calmar=m_base.calmar,
        base_max_dd=m_base.max_drawdown,
        turnover_pct=m_base.annualized_turnover * 100,
        s62_retention=retention,
        s62_perturbed_calmar=m_perturb.calmar,
        s62_top_contributors=top_symbols,
        s62_passes=s62_passes,
        s63_applicable=s63["applicable"],
        s63_neighbors=s63["neighbors"],
        s63_absent=s63["absent"],
        s63_threshold=s63["threshold"],
        s63_passes=s63["passes"],
        s64_calmar_per_period=s64["calmar_per_period"],
        s64_n_positive=s64["n_positive"],
        s64_passes_concentration=s64["passes_concentration"],
        s65_participation_pct=s65["participation_pct"],
        s65_passes=s65["passes"],
        dep_calmar_strat=bm.strategy_calmar,
        dep_calmar_bench=bm.benchmark_calmar,
        dep_max_dd_strat=bm.strategy_max_dd,
        dep_max_dd_bench=bm.benchmark_max_dd,
        dep_dd_ratio=bm.max_dd_ratio,
        dep_calmar_beats=dep_calmar_beats,
        dep_dd_ok=dep_dd_ok,
        dep_passes=dep_passes,
        s6_passes=s6_passes,
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(results: list[SurvivorResult]) -> None:
    sep = "=" * 84
    print()
    print(sep)
    print("  SU2 Stage 2 — Full §6 battery on §6.1 survivors {C0, S2, S3}")
    print(
        "  DISCOVERY 2018-02-06 → 2023-06-30  |  momentum held constant (M=130 sm=0 monthly)"
    )
    print(
        "  §6.4 DIAGNOSTIC only; deployment bar maxDD ≤ 100% (08 §2b, corrected from MD2's 70%)"
    )
    print(sep)

    for r in results:
        print(f"\n{'─' * 74}")
        print(
            f"  {r.name}  ({r.universe_label})  base Calmar {r.base_calmar:.3f}, "
            f"maxDD {r.base_max_dd:.1%}, turnover {r.turnover_pct:.0f}%"
        )

        ret = f"{r.s62_retention:.0%}" if not math.isnan(r.s62_retention) else "n/a"
        print(f"\n  §6.2  Universe perturbation — {'PASS' if r.s62_passes else 'FAIL'}")
        print(
            f"        perturbed calmar={r.s62_perturbed_calmar:.3f}  "
            f"retention={ret} (≥70%)"
        )
        print(f"        dropped: {r.s62_top_contributors}")

        if r.s63_applicable:
            print(
                f"\n  §6.3  Neighborhood plateau — {'PASS' if r.s63_passes else 'FAIL'}"
            )
            print(
                f"        threshold={r.s63_threshold:.4f} (85% × {r.base_calmar:.3f}); "
                f"absent §5 corner(s): {', '.join(r.s63_absent)}"
            )
            for lbl, nc in r.s63_neighbors.items():
                ok = nc >= r.s63_threshold
                print(
                    f"        {'ok  ' if ok else 'FAIL'} {lbl:6s} base Calmar={nc:.3f}"
                )
        else:
            print("\n  §6.3  Neighborhood plateau — N/A")
            print(
                "        C0 is the off-lattice floor control (no §5 universe neighbors)."
            )
            print(
                "        It cannot be the locked stable-universe candidate (08 §6.3)."
            )

        print("\n  §6.4  Subperiod stability — DIAGNOSTIC (not gating)")
        print(
            f"        concentration_hard_pass={r.s64_passes_concentration}  "
            f"n_positive={r.s64_n_positive}/3"
        )
        for period, c in r.s64_calmar_per_period.items():
            print(f"        {period:24s}  calmar={c:.3f}")

        print(f"\n  §6.5  Turnover / capacity — {'PASS' if r.s65_passes else 'FAIL'}")
        print(f"        participation={r.s65_participation_pct:.3f}% (<5% ADV floor)")

        print(
            f"\n  §6-4  Deployment bar (Nifty200 Mom30, base cost) — "
            f"{'PASS' if r.dep_passes else 'FAIL'}"
        )
        print(
            f"        C_strat={r.dep_calmar_strat:.3f}  C_bench={r.dep_calmar_bench:.3f}  "
            f"calmar_beats={r.dep_calmar_beats}"
        )
        print(
            f"        maxDD_strat={r.dep_max_dd_strat:.1%}  maxDD_bench={r.dep_max_dd_bench:.1%}  "
            f"dd_ratio={r.dep_dd_ratio:.2f} (≤1.00)"
        )

        verdict = (
            "PASS — qualifies for OOS candidate" if r.s6_passes else "FAIL — eliminated"
        )
        print(f"\n  §6 VERDICT: {verdict}")
        if not r.s6_passes:
            fails = []
            if not r.s62_passes:
                fails.append("§6.2")
            if r.s63_applicable and not r.s63_passes:
                fails.append("§6.3")
            if not r.s63_applicable:
                fails.append("§6.3 N/A (control)")
            if not r.s65_passes:
                fails.append("§6.5")
            if not r.dep_passes:
                fails.append("deployment bar")
            print(f"        Failed/blocking gates: {', '.join(fails)}")

    candidates = [r for r in results if r.s6_passes]
    print()
    print(sep)
    if not candidates:
        print("  §6 OUTCOME: NULL CLOSE")
        print("  Zero configs satisfy §6 items 1–4 on full DISCOVERY.")
        print("  Per prereg §6: stable-universe momentum closes as a research note.")
        print(
            "  FINAL_OOS remains pristine and untouched — the OOS run is NOT performed."
        )
        print(
            "  Pre-accepted, honest finding — no stick moved, no lever added (00 §1)."
        )
    elif len(candidates) == 1:
        c = candidates[0]
        print(f"  §6 OUTCOME: SINGLE LOCKED CANDIDATE → {c.name} ({c.universe_label})")
        print("  Proceeds to SU3 (one-shot FINAL_OOS).")
    else:
        # Tie-break: lowest realized membership churn, then lowest turnover (08 §6).
        winner = min(candidates, key=lambda r: r.turnover_pct)
        print(
            f"  §6 OUTCOME: {len(candidates)} configs pass — tie-break (lowest churn/turnover)."
        )
        print(f"  LOCKED CANDIDATE → {winner.name} ({winner.universe_label})")
    print(sep)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    global prices_for_mask

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in (
        "app.backtest_v2",
        "app.core.strategy",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(noisy).setLevel(logging.ERROR)
    logging.getLogger(__name__).setLevel(logging.INFO)

    print("v3 / 08 SU2 — Stage 2: full §6 battery on §6.1 survivors {C0, S2, S3}")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    print()

    print("Loading prices_adjusted (offline cache)...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    prices_for_mask = prices
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

    print("Loading Nifty200 Momentum 30 TRI (§6.4 deployment bar)...", flush=True)
    try:
        tri_momentum30 = benchmark.load_tri(
            benchmark.TRI_MOMENTUM_30, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
    except Exception as exc:
        print(f"FAIL: Nifty200 Momentum 30 TRI unavailable: {exc}", file=sys.stderr)
        return 2

    # Shared gate-indicator cache + composite (momentum identical across the grid;
    # only the universe mask differs). sm=0 → one composite for all configs.
    ref_v3 = _v3_config(_SURVIVORS[0], *DISCOVERY)
    print(
        "Precomputing v2 gate indicator cache + composite (DISCOVERY, shared)...",
        flush=True,
    )
    gate_store = precompute_signals(prices, _engine_cfg(ref_v3, *DISCOVERY))
    gate_ind = gate_store._data
    composite = factors.composite_rank(prices, ref_v3)

    ledger = ConfigLedger()
    results: list[SurvivorResult] = []
    for i, cfg in enumerate(_SURVIVORS, 1):
        print(
            f"\n[{i}/{len(_SURVIVORS)}] Battery: {cfg.name} — {cfg.universe_label} ({cfg.role})",
            flush=True,
        )
        results.append(
            run_survivor(
                cfg, prices, index_prices, tri_momentum30, composite, gate_ind, ledger
            )
        )

    _print_report(results)

    print(f"\n  SU2 new ConfigLedger entries (K this run): {ledger.n_trials}")
    print(
        "  Cumulative K at SU3 = ledger (≥46 at TBE7 + 8 at SU1) + these entries (08 §8)."
    )
    print("  FINAL_OOS untouched.")

    candidates = [r for r in results if r.s6_passes]
    return 0 if len(candidates) >= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
