"""
vt2_battery.py — v3 / 09 VT2: Stage 2 full §6 battery on the §6.1 survivor(s).

Pre-registration: specs/v3/09_MOMENTUM_VALUE_TILT_PREREG.md §6 / §7 / §13 VT2.

VT1 §6.1 survivor set = {T-400-lo} (U=400, λ=0.3) — the lone config of 9 to clear
the pessimistic-cost Calmar ratio ≥ 1.0 (ratio 1.01, base Calmar 0.392). This stage
runs the full §6 battery on it and applies the §6 acceptance rule (items 1–5 +
tie-break), then locks a single OOS candidate OR declares the pre-accepted null close.

Momentum base held constant (09 §3 retention-first): [mom_12_1, low_vol], N=20,
M=130, sm=0, monthly, regime ON, cat-stop 25%, ₹5cr floor, stable U=400 B=1.25. The
ONLY new source is the value tilt λ=0.3 (final_rank = momentum + λ·value_rank).

Battery (09 §6):
  §6.1  pessimistic-cost Calmar ratio ≥ 1.0 — ALREADY CONFIRMED in VT1 (1.01); carried.
  §6.2  SKEW-AWARE (PRIMARY gate, 09 §2c/§6 item 2, threshold NOT relaxed):
          (a) random-subset retention — 200 draws each dropping a RANDOM 10 of the
              held names; median retention ≥ 0.70 AND p5 retention ≥ 0.50.
          (b) contributor rotation — union of per-calendar-year top-10 P&L
              contributors spans ≥ 25 distinct names across DISCOVERY.
        CLASSIC drop-top-10 retention is computed + reported alongside (NOT the gate;
        the §2c contamination guard — pass-skew-fail-classic ⇒ "conditional").
  §6.3  Neighborhood plateau — the §5 U×λ neighbors (±1 step on U and on λ) stay
        ≥ 85% of the config's base Calmar. Reuses the VT1 base-Calmar table (no new
        runs — the §5 points are already logged), exactly as SU2 reused SU1.
  §6.4  Subperiod stability — 3 market-cycle periods (DIAGNOSTIC ONLY, 09 §6 item 5).
  §6.5  Turnover / capacity — avg trade participation < 5% ADV floor (reported).
  bar   Deployment bar (09 §6 item 4 / §10): beats REAL Nifty200 Momentum 30 TRI on
        base-cost Calmar AND maxDD ≤ 100% of benchmark.

TILT TRADE-OFF DIAGNOSTIC (09 §6, required): the λ=0 control C-400 is run through the
same base + skew-aware §6.2 so the close records (i) did the tilt lift Calmar over the
index at the robust cell, and (ii) did it move skew-aware retention vs the λ=0 control.

DISCOVERY only — FINAL_OOS stays pristine. VT3 (one-shot FINAL_OOS) runs ONLY if this
stage locks a single candidate; N/A on the null.

Run:
    backend/venv/bin/python -m app.backtest_v2.vt2_battery
"""

from __future__ import annotations

import logging
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.engine import _rebalance_dates
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import (
    V3SignalStore,
    _apply_value_tilt,
    build_value_rank,
)
from app.backtest_v2.skew_robustness import (
    contributor_rotation,
    random_subset_retention,
)
from app.backtest_v2.stable_universe import build_stable_universe_mask
from app.backtest_v2.tbe4_value_block import _build_fund_frames
from app.backtest_v2.v3_config import TRACK_A_BASELINE, V3Config
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store
from app.db.session import SessionLocal

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Held-constant momentum construction (09 §3) — retention-first 2-factor base.
_BASE_FACTORS = ["mom_12_1", "low_vol"]
_M = 130
_SMOOTHING = 0
_CADENCE = "monthly"
_BUFFER_B = 1.25  # the `08` churn antidote, fixed (not a grid lever)

# §6.2 classic drop-top-10 (reported alongside skew-aware — NOT the gate, 09 §2c).
_CLASSIC_RETENTION_THRESHOLD = 0.70
_N_TOP_CONTRIBUTORS = 10

# §6.3 plateau tolerance (09 §6 item 3).
_PLATEAU_TOL = 0.85

# §6.5 ADV floor capacity check.
_MAX_ADV_PARTICIPATION_PCT = 5.0
_LIQUIDITY_FLOOR_CR = 5.0

# §6.4 subperiods — identical to su2_battery / md2_battery, fixed before any run.
SUBPERIODS: list[tuple[str, date, date]] = [
    ("Pre-COVID chop", date(2018, 2, 6), date(2020, 3, 31)),
    ("Post-COVID bull", date(2020, 4, 1), date(2022, 1, 31)),
    ("Rate-hike correction", date(2022, 2, 1), date(2023, 6, 30)),
]

# ---------------------------------------------------------------------------
# VT1 base-Calmar table (all 9 §5 U×λ configs, already logged to ConfigLedger in
# VT1 — reused for §6.3 plateau without re-running, exactly as SU2 reused SU1).
# Source: 09 §13 VT1 session log.
# ---------------------------------------------------------------------------
_VT1_BASE_CALMAR: dict[tuple[int, float], float] = {
    (300, 0.0): 0.205,
    (300, 0.3): 0.315,
    (300, 0.6): 0.295,
    (350, 0.0): 0.295,
    (350, 0.3): 0.318,
    (350, 0.6): 0.265,
    (400, 0.0): 0.289,
    (400, 0.3): 0.392,
    (400, 0.6): 0.326,
}
_U_GRID = [300, 350, 400]
_LAMBDA_GRID = [0.0, 0.3, 0.6]


@dataclass
class VT2Config:
    """One §6.1 survivor carried into the full battery (+ its λ=0 control)."""

    name: str
    universe_size_U: int
    value_tilt_lambda: float
    role: str

    @property
    def label(self) -> str:
        return f"stable U={self.universe_size_U} B={_BUFFER_B:g} λ={self.value_tilt_lambda:g}"


# VT1 §6.1 survivor + its λ=0 control (the tilt trade-off baseline, 09 §6).
_SURVIVOR = VT2Config("T-400-lo", 400, 0.3, "§6.1 survivor (ratio 1.01)")
_CONTROL = VT2Config("C-400", 400, 0.0, "λ=0 control (tilt trade-off baseline)")


@dataclass
class SkewResult:
    median_retention: float
    p5_retention: float
    rs_passes: bool
    n_distinct_contributors: int
    rotation_passes: bool
    passes: bool


@dataclass
class SurvivorResult:
    name: str
    label: str
    role: str
    base_calmar: float
    base_max_dd: float
    turnover_pct: float
    # §6.2 skew-aware (primary gate)
    skew: SkewResult
    # §6.2 classic drop-top-10 (reported, NOT gating)
    classic_retention: float
    classic_perturbed_calmar: float
    classic_top_contributors: list[str]
    classic_passes: bool
    # §6.3 plateau
    s63_threshold: float
    s63_neighbors: dict[str, float]
    s63_absent: list[str]
    s63_passes: bool
    # §6.4 diagnostic
    s64_calmar_per_period: dict[str, float] = field(default_factory=dict)
    s64_n_positive: int = 0
    # §6.5 capacity
    s65_participation_pct: float = 0.0
    s65_passes: bool = False
    # deployment bar
    dep_calmar_strat: float = 0.0
    dep_calmar_bench: float = 0.0
    dep_max_dd_strat: float = 0.0
    dep_max_dd_bench: float = 0.0
    dep_dd_ratio: float = 0.0
    dep_calmar_beats: bool = False
    dep_dd_ok: bool = False
    dep_passes: bool = False
    # §6 verdict
    s6_passes: bool = False


# ---------------------------------------------------------------------------
# Config plumbing (mirrors vt1_cost_screen / su2_battery)
# ---------------------------------------------------------------------------


def _v3_config(cfg: VT2Config, date_from: date, date_to: date) -> V3Config:
    return V3Config(
        active_factors=list(_BASE_FACTORS),
        rebalance_cadence=_CADENCE,
        sell_rank_buffer=_M,
        rank_smoothing_months=_SMOOTHING,
        target_positions=TRACK_A_BASELINE.target_positions,
        use_regime_overlay=True,
        catastrophic_stop_pct=25.0,
        liquidity_floor_cr=5.0,
        universe_mode="stable",
        universe_size_U=cfg.universe_size_U,
        universe_buffer_B=_BUFFER_B,
        value_tilt_lambda=cfg.value_tilt_lambda,
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


# ---------------------------------------------------------------------------
# §6.2b per-calendar-year top-10 contributors (from fills_log)
# ---------------------------------------------------------------------------


def _per_year_top_contributors(
    result: engine.EngineResult, top_n: int = _N_TOP_CONTRIBUTORS
) -> dict[int, list[str]]:
    """Per calendar year, the top-`top_n` names by that year's realized net cashflow.

    Net cashflow per (year, name) = Σ sell/trim notional − Σ buy notional − Σ cost,
    mirroring metrics.PerNameStats.realized_pnl but partitioned by fill year. This is
    a per-year P&L *attribution* proxy (inventory carried across a year boundary is
    not re-marked) — sufficient to ask whether the winners ROTATE (09 §6.2b). Identity
    is the symbol (consistent with the classic top-contributor report).
    """
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


# ---------------------------------------------------------------------------
# §6.3 Neighborhood plateau (reuse VT1 table — no new runs)
# ---------------------------------------------------------------------------


def check_s63_plateau(u: int, lam: float) -> dict:
    """§5 U×λ-neighbor plateau from the VT1 base-Calmar table (09 §6 item 3).

    Neighbors = ±1 step on U and on λ among the §5 grid points. Each PRESENT neighbor
    must stay ≥ 85% of the config's own base Calmar (a region, not a spike). Steps that
    land off the §5 grid (e.g. U=450) are reported as absent.
    """
    base = _VT1_BASE_CALMAR[(u, lam)]
    threshold = base * _PLATEAU_TOL
    ui = _U_GRID.index(u)
    li = _LAMBDA_GRID.index(lam)
    neighbors: dict[str, float] = {}
    absent: list[str] = []
    # ±1 on U (λ fixed), ±1 on λ (U fixed)
    for du, dl in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nu_i, nl_i = ui + du, li + dl
        if 0 <= nu_i < len(_U_GRID) and 0 <= nl_i < len(_LAMBDA_GRID):
            nu, nl = _U_GRID[nu_i], _LAMBDA_GRID[nl_i]
            neighbors[f"U={nu} λ={nl:g}"] = _VT1_BASE_CALMAR[(nu, nl)]
        else:
            axis = f"U={u + du * 50}" if dl == 0 else f"λ={lam + dl * 0.3:g}"
            absent.append(f"{axis} ({'U' if dl == 0 else 'λ'} step)")
    passes = all(nc >= threshold for nc in neighbors.values()) and bool(neighbors)
    return {
        "threshold": round(threshold, 4),
        "neighbors": neighbors,
        "absent": absent,
        "passes": passes,
    }


# ---------------------------------------------------------------------------
# §6.4 Subperiod stability (diagnostic — no gate)
# ---------------------------------------------------------------------------


def run_s64_subperiods(
    cfg: VT2Config,
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
                "lambda": cfg.value_tilt_lambda,
                "subperiod": label,
            },
            stage="VT2_s64_subperiod",
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
    return {"calmar_per_period": calmar_map, "n_positive": n_positive}


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
# §6.2 skew-aware + classic for one config (the expensive part — 200 reruns)
# ---------------------------------------------------------------------------


def run_skew_and_classic(
    cfg: VT2Config,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    eng: MomentumConfig,
    ss: V3SignalStore,
    res_base: engine.EngineResult,
    m_base: metrics.BacktestMetrics,
    ledger: ConfigLedger,
) -> tuple[SkewResult, float, float, list[str], bool]:
    base_calmar = m_base.calmar
    held_isins = [ns.isin for ns in m_base.per_name_stats]

    # run_perturbed seam (09 §2c): drop a set of ISINs from prices, rerun, return Calmar.
    def run_perturbed(drop_set: frozenset[str]) -> float:
        prices_p = prices[~prices["isin"].isin(drop_set)]
        res_p = engine.run(
            prices_p, eng, index_prices=index_prices, cost_level="base", signal_store=ss
        )
        return metrics.compute_metrics(res_p).calmar

    # (a) random-subset retention — 200 draws of a random-10 drop (no lookahead).
    log.info("  [§6.2a] random-subset retention (200×drop-10, seeded) ...")
    rs = random_subset_retention(held_isins, base_calmar, run_perturbed)
    ledger.add(
        {
            "config": cfg.name,
            "test": "skew_random_subset",
            "n_draws": rs.n_draws,
            "drop_k": rs.drop_k,
            "median_retention": round(rs.median_retention, 4),
            "p5_retention": round(rs.p5_retention, 4),
        },
        stage="VT2_s62_skew",
    )
    log.info("    %s", rs.summary)

    # (b) contributor rotation — per-year top-10 union ≥ 25 distinct names.
    log.info("  [§6.2b] contributor rotation (per-year top-10 union) ...")
    per_year = _per_year_top_contributors(res_base)
    rot = contributor_rotation(per_year)
    log.info("    %s", rot.summary)

    skew = SkewResult(
        median_retention=rs.median_retention,
        p5_retention=rs.p5_retention,
        rs_passes=rs.passed,
        n_distinct_contributors=rot.n_distinct,
        rotation_passes=rot.passed,
        passes=rs.passed and rot.passed,
    )

    # CLASSIC drop-top-10 realized-P&L (reported alongside; NOT the gate — 09 §2c).
    log.info(
        "  [§6.2 classic] drop top-%d realized P&L (reported) ...", _N_TOP_CONTRIBUTORS
    )
    sorted_names = sorted(
        m_base.per_name_stats, key=lambda ns: ns.realized_pnl, reverse=True
    )
    top_n = sorted_names[:_N_TOP_CONTRIBUTORS]
    classic_calmar = run_perturbed(frozenset(ns.isin for ns in top_n))
    classic_retention = (
        classic_calmar / base_calmar if base_calmar > 0 else float("nan")
    )
    classic_passes = (
        not math.isnan(classic_retention)
        and classic_retention >= _CLASSIC_RETENTION_THRESHOLD
    )
    log.info(
        "    classic perturbed calmar=%.3f  retention=%.0f%%  %s",
        classic_calmar,
        classic_retention * 100 if not math.isnan(classic_retention) else float("nan"),
        "pass" if classic_passes else "FAIL",
    )
    return (
        skew,
        classic_retention,
        classic_calmar,
        [ns.symbol for ns in top_n],
        classic_passes,
    )


# ---------------------------------------------------------------------------
# Full battery for one config
# ---------------------------------------------------------------------------


def run_config(
    cfg: VT2Config,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    tri_momentum30: pd.Series,
    base_composite: pd.DataFrame,
    value_rank: pd.DataFrame,
    mask,
    gate_ind,
    ledger: ConfigLedger,
    *,
    full_battery: bool,
) -> SurvivorResult:
    """Run the §6 battery. full_battery=False (the λ=0 control) runs only the base +
    skew-aware §6.2 + deployment bar (enough for the tilt trade-off diagnostic)."""
    v3cfg = _v3_config(cfg, *DISCOVERY)
    eng = _engine_cfg(v3cfg, *DISCOVERY)
    composite = _apply_value_tilt(base_composite, value_rank, cfg.value_tilt_lambda)
    ss = V3SignalStore(gate_ind, composite, v3cfg, universe_mask=mask)

    payload = {
        "config": cfg.name,
        "universe_mode": "stable",
        "U": cfg.universe_size_U,
        "B": _BUFFER_B,
        "lambda": cfg.value_tilt_lambda,
        "M": _M,
        "smoothing": _SMOOTHING,
        "cadence": _CADENCE,
        "base_factors": _BASE_FACTORS,
    }

    # -- Base run --
    log.info("  [base run] %s — %s ...", cfg.name, cfg.label)
    ledger.add({**payload, "cost_level": "base"}, stage="VT2_base")
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

    # -- §6.2 skew-aware (+ classic reported) --
    skew, classic_ret, classic_calmar, classic_top, classic_passes = (
        run_skew_and_classic(
            cfg, prices, index_prices, eng, ss, res_base, m_base, ledger
        )
    )

    # -- §6.3 plateau (VT1 table — no new runs) --
    s63 = check_s63_plateau(cfg.universe_size_U, cfg.value_tilt_lambda)
    log.info(
        "    §6.3  threshold=%.4f  %s",
        s63["threshold"],
        "PASS" if s63["passes"] else "FAIL",
    )
    for lbl, nc in s63["neighbors"].items():
        log.info(
            "          neighbor %-12s base Calmar=%.3f  %s",
            lbl,
            nc,
            "ok" if nc >= s63["threshold"] else "BELOW",
        )

    # -- §6.4 subperiod (diagnostic) + §6.5 capacity — only for the full battery --
    if full_battery:
        log.info("  [§6.4] subperiod stability (diagnostic) ...")
        s64 = run_s64_subperiods(
            cfg, prices, index_prices, composite, gate_ind, mask, ledger
        )
        s65 = check_s65(m_base)
        log.info(
            "    §6.5  participation=%.3f%%  %s",
            s65["participation_pct"],
            "PASS" if s65["passes"] else "FAIL",
        )
    else:
        s64 = {"calmar_per_period": {}, "n_positive": 0}
        s65 = {"participation_pct": float("nan"), "passes": False}

    # -- Deployment bar (REAL Nifty200 Mom30, base cost, maxDD ≤ 100%) --
    trading_cal = [pd.Timestamp(s.date) for s in res_base.snapshots]
    bench_aligned = benchmark.align_benchmark(
        tri_momentum30, eng.date_from, trading_cal, eng.starting_capital
    )
    bm = metrics.compute_benchmark_metrics(_equity_series(res_base), bench_aligned)
    dep_calmar_beats = bm.strategy_calmar > bm.benchmark_calmar
    dep_dd_ok = (not math.isnan(bm.max_dd_ratio)) and bm.max_dd_ratio <= 1.0
    dep_passes = dep_calmar_beats and dep_dd_ok
    log.info(
        "    bar   C_strat=%.3f  C_bench=%.3f  beats=%s  dd_ratio=%.2f (≤1.0)  %s",
        bm.strategy_calmar,
        bm.benchmark_calmar,
        dep_calmar_beats,
        bm.max_dd_ratio,
        "PASS" if dep_passes else "FAIL",
    )

    # -- §6 acceptance (items 1–4 hard; §6.1 already PASS via VT1; §6.4 diagnostic) --
    # item1 §6.1 = PASS (VT1); item2 §6.2 skew; item3 §6.3; item4 deployment bar.
    s6_passes = (
        full_battery and skew.passes and s63["passes"] and dep_passes and s65["passes"]
    )

    return SurvivorResult(
        name=cfg.name,
        label=cfg.label,
        role=cfg.role,
        base_calmar=m_base.calmar,
        base_max_dd=m_base.max_drawdown,
        turnover_pct=m_base.annualized_turnover * 100,
        skew=skew,
        classic_retention=classic_ret,
        classic_perturbed_calmar=classic_calmar,
        classic_top_contributors=classic_top,
        classic_passes=classic_passes,
        s63_threshold=s63["threshold"],
        s63_neighbors=s63["neighbors"],
        s63_absent=s63["absent"],
        s63_passes=s63["passes"],
        s64_calmar_per_period=s64["calmar_per_period"],
        s64_n_positive=s64["n_positive"],
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


def _print_one(r: SurvivorResult, *, full: bool) -> None:
    print(f"\n{'─' * 78}")
    print(
        f"  {r.name}  ({r.label})  [{r.role}]\n"
        f"  base Calmar {r.base_calmar:.3f}, maxDD {r.base_max_dd:.1%}, "
        f"turnover {r.turnover_pct:.0f}%"
    )

    s = r.skew
    print(f"\n  §6.2  SKEW-AWARE (PRIMARY gate) — {'PASS' if s.passes else 'FAIL'}")
    print(
        f"        (a) random-subset: median {s.median_retention:.0%} (≥70%) · "
        f"p5 {s.p5_retention:.0%} (≥50%) → {'pass' if s.rs_passes else 'FAIL'}"
    )
    print(
        f"        (b) rotation: {s.n_distinct_contributors} distinct top-10 "
        f"contributors (≥25) → {'pass' if s.rotation_passes else 'FAIL'}"
    )
    cret = (
        f"{r.classic_retention:.0%}" if not math.isnan(r.classic_retention) else "n/a"
    )
    print(
        f"        classic drop-top-10 (reported, NOT gating): retention {cret} "
        f"(perturbed Calmar {r.classic_perturbed_calmar:.3f}) → "
        f"{'pass' if r.classic_passes else 'FAIL'}"
    )

    print(f"\n  §6.3  Neighborhood plateau — {'PASS' if r.s63_passes else 'FAIL'}")
    print(
        f"        threshold={r.s63_threshold:.4f} (85% × {r.base_calmar:.3f}); "
        f"absent §5 corner(s): {', '.join(r.s63_absent) or 'none'}"
    )
    for lbl, nc in r.s63_neighbors.items():
        ok = nc >= r.s63_threshold
        print(f"        {'ok  ' if ok else 'BELOW'} {lbl:12s} base Calmar={nc:.3f}")

    if full:
        print("\n  §6.4  Subperiod stability — DIAGNOSTIC (not gating)")
        print(f"        n_positive={r.s64_n_positive}/3")
        for period, c in r.s64_calmar_per_period.items():
            print(f"        {period:24s}  calmar={c:.3f}")
        print(f"\n  §6.5  Turnover / capacity — {'PASS' if r.s65_passes else 'FAIL'}")
        print(f"        participation={r.s65_participation_pct:.3f}% (<5% ADV floor)")

    print(
        f"\n  bar   Deployment bar (REAL Nifty200 Mom30, base cost) — "
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

    if full:
        verdict = (
            "PASS — qualifies for OOS candidate" if r.s6_passes else "FAIL — eliminated"
        )
        print(f"\n  §6 VERDICT: {verdict}")
        if not r.s6_passes:
            fails = []
            if not r.skew.passes:
                fails.append("§6.2 skew-aware")
            if not r.s63_passes:
                fails.append("§6.3 plateau")
            if not r.s65_passes:
                fails.append("§6.5")
            if not r.dep_passes:
                fails.append("deployment bar")
            print(f"        Failed/blocking hard gates: {', '.join(fails)}")


def _print_tradeoff(survivor: SurvivorResult, control: SurvivorResult) -> None:
    print(f"\n{'═' * 78}")
    print("  TILT TRADE-OFF DIAGNOSTIC (09 §6 — required, the research value)")
    print(f"{'═' * 78}")
    print(
        f"  (i)  Calmar vs the REAL Nifty200 Mom30 index at the robust cell:\n"
        f"         control C-400 (λ=0): C_strat {control.dep_calmar_strat:.3f} vs "
        f"index {control.dep_calmar_bench:.3f} "
        f"({'beats' if control.dep_calmar_beats else 'trails'})\n"
        f"         survivor T-400-lo (λ=0.3): C_strat {survivor.dep_calmar_strat:.3f} vs "
        f"index {survivor.dep_calmar_bench:.3f} "
        f"({'beats' if survivor.dep_calmar_beats else 'trails'})\n"
        f"         → tilt moved base Calmar {control.base_calmar:.3f} → "
        f"{survivor.base_calmar:.3f} "
        f"({survivor.base_calmar - control.base_calmar:+.3f})"
    )
    print(
        f"  (ii) Skew-aware median retention vs the λ=0 control:\n"
        f"         control C-400 (λ=0): median {control.skew.median_retention:.0%}, "
        f"p5 {control.skew.p5_retention:.0%}\n"
        f"         survivor T-400-lo (λ=0.3): median {survivor.skew.median_retention:.0%}, "
        f"p5 {survivor.skew.p5_retention:.0%}\n"
        f"         → tilt moved median retention "
        f"{survivor.skew.median_retention - control.skew.median_retention:+.0%}"
    )


def _print_outcome(survivor: SurvivorResult) -> None:
    sep = "=" * 78
    print(f"\n{sep}")
    if survivor.s6_passes:
        print(
            f"  §6 OUTCOME: SINGLE LOCKED CANDIDATE → {survivor.name} ({survivor.label})"
        )
        cond = (
            "  ⚠ passes skew-aware but FAILS classic drop-top-10 → labeled "
            "'research-note, conditional' (09 §2c/§10), NOT 'validated'."
            if survivor.skew.passes and not survivor.classic_passes
            else ""
        )
        if cond:
            print(cond)
        print("  Proceeds to VT3 (one-shot FINAL_OOS).")
    else:
        print("  §6 OUTCOME: NULL CLOSE")
        print(
            "  The lone §6.1 survivor T-400-lo fails the §6 hard gates on full DISCOVERY."
        )
        print(
            "  Per prereg §6: momentum × value-tilt closes as a RESEARCH NOTE — "
            "FINAL_OOS stays\n  pristine and untouched; VT3 is NOT performed (N/A on the null)."
        )
        print(
            "  Pre-accepted, honest finding — no stick moved, no lever added (00 §1 / 09 §6)."
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

    print("v3 / 09 VT2 — Stage 2: full §6 battery on the §6.1 survivor {T-400-lo}")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    print(
        f"  Momentum base held constant: {_BASE_FACTORS}, N=20, M={_M}, sm={_SMOOTHING}, "
        f"{_CADENCE}, regime ON, stable U=400 B={_BUFFER_B:g}; value tilt λ=0.3"
    )
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

    print("Loading REAL Nifty200 Momentum 30 TRI (deployment bar)...", flush=True)
    try:
        tri_momentum30 = benchmark.load_tri(
            benchmark.TRI_MOMENTUM_30, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
    except Exception as exc:
        print(f"FAIL: Nifty200 Momentum 30 TRI unavailable: {exc}", file=sys.stderr)
        return 2

    # Shared 2-factor momentum base + gate cache (identical across λ; only the tilt
    # differs). sm=0 → one composite for both configs.
    ref_v3 = _v3_config(_CONTROL, *DISCOVERY)
    print("Precomputing gate cache + 2-factor composite (shared)...", flush=True)
    gate_store = precompute_signals(prices, _engine_cfg(ref_v3, *DISCOVERY))
    gate_ind = gate_store._data
    base_composite = factors.composite_rank(prices, ref_v3)

    # Value block (E/P, B/P) over DISCOVERY monthly rebalances → value_rank.
    disc_prices = prices[
        (prices["date"] >= pd.Timestamp(DISCOVERY[0]))
        & (prices["date"] <= pd.Timestamp(DISCOVERY[1]))
    ]
    calendar = sorted(disc_prices["date"].unique().tolist())
    rebalance_dates = [ts.date() for ts in sorted(_rebalance_dates(calendar, _CADENCE))]
    print(
        f"Building value block (E/P, B/P) over {len(rebalance_dates)} rebalances...",
        flush=True,
    )
    session = SessionLocal()
    try:
        fund_frames = _build_fund_frames(prices, rebalance_dates, session)
    finally:
        session.close()
    value_rank = build_value_rank(fund_frames)

    # Stable-universe mask for U=400 (shared by survivor + control).
    print("Building stable-universe mask (U=400, B=1.25)...", flush=True)
    mask = build_stable_universe_mask(
        prices,
        400,
        _BUFFER_B,
        ref_v3.universe_rank_lookback_td,
        ref_v3.universe_review_cadence,
    )

    ledger = ConfigLedger()

    print(f"\n[1/2] Full battery: {_SURVIVOR.name} — {_SURVIVOR.label}", flush=True)
    survivor = run_config(
        _SURVIVOR,
        prices,
        index_prices,
        tri_momentum30,
        base_composite,
        value_rank,
        mask,
        gate_ind,
        ledger,
        full_battery=True,
    )

    print(
        f"\n[2/2] λ=0 control (tilt trade-off): {_CONTROL.name} — {_CONTROL.label}",
        flush=True,
    )
    control = run_config(
        _CONTROL,
        prices,
        index_prices,
        tri_momentum30,
        base_composite,
        value_rank,
        mask,
        gate_ind,
        ledger,
        full_battery=False,
    )

    # ---- Report ----
    sep = "=" * 78
    print(f"\n{sep}")
    print("  VT2 Stage 2 — full §6 battery (DISCOVERY 2018-02-06 → 2023-06-30)")
    print(
        "  §6.2 SKEW-AWARE primary (classic reported); §6.4 diagnostic; bar maxDD ≤ 100%"
    )
    print(sep)
    _print_one(survivor, full=True)
    _print_one(control, full=False)
    _print_tradeoff(survivor, control)
    _print_outcome(survivor)

    print(f"\n  VT2 new ConfigLedger entries (K this run): {ledger.n_trials}")
    print("  Cumulative K at VT3 = ledger (≥69 + VT1's 18) + these entries (09 §8).")
    print("  FINAL_OOS untouched.")
    return 0 if survivor.s6_passes else 1


if __name__ == "__main__":
    sys.exit(main())
