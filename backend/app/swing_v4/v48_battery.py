"""
v48_battery.py — v4 / 05 V4.8: full §6 acceptance battery on the §6.1 survivor.

Pre-registration: specs/v4/05_TURNOVER_TREND_PREREG.md §6 (binding gates) / §7 (K,
DSR, one-shot OOS) / §11 (V4.8). DISCOVERY only — v4-FINAL_OOS stays pristine; OOS
(V4.9) is touched ONLY on a config that clears §6.1–§6.4 here, which the V4.7
fragility flags + the pre-V4.8 mechanism diagnostic (87% of net P&L = one name,
ATGL) make a near-certain NULL.

The single survivor under test: atr_mult 5.0 / decision_cadence daily / neutral 0.75,
MOM, stable U=200, target_positions=15, ₹3.5L, whole-share, −25% floor.

GATES (`05` §6 — identical to `00`/`04`, nothing relaxed; ALL must hold to lock):
  §6.1  cost survival — pessimistic Calmar ratio vs Nifty 50 TRI ≥ 1.0  (re-confirm 1.27).
  §6.2  skew-aware concentration (`app/backtest_v2/skew_robustness.py`, the `09`/`10` gate):
        (a) random-subset retention — 200 draws, drop-10 RANDOM held names (no lookahead),
            median retention ≥ 0.70 AND p5 ≥ 0.50 of base Calmar.
        (b) contributor rotation — per-calendar-year top-10 net-P&L names, union ≥ 25 distinct.
        Classic drop-top-10 realized P&L reported as a contamination guard (DIAGNOSTIC,
        not gating — a trend book is *meant* to ride winners).
  §6.3  plateau — candidate + ±1-step neighbors on atr_mult {3,4,5} AND neutral {0.5,0.75}
        stay ≥ 85% of the candidate base Calmar (a region, not a lone peak).
  deploy bar (= `08` §2b / `00` §6.4) — base-cost Calmar beats Nifty 50 TRI with maxDD ≤
        100% of the benchmark.
  §6.4  subperiod stability — reported, DIAGNOSTIC (window-fragility demoted across v2→v4).

CONTEXT (§7, reported, NOT extra gates):
  DSR  — deflated Sharpe at K≈13 (raw Sharpe deflated for K-trial selection + non-normality).
  PBO  — CSCV probability of backtest overfitting over the plateau grid (coarse-fold caveat).

NON-GATING ADD-ONS (0 to K):
  §5 anti-thrash on the survivor (min_hold/cooldown) — confirms `03`.
  leave-top-k-out fragility DEMONSTRATION (Arafat, 2026-06-25): remove the top 1/2/5/10/20
  trades by net P&L → recompute a P&L-attribution CAGR. Shows how fast the edge vanishes;
  NOT a deployment rule, NOT a re-simulation.

Run:
    backend/venv/bin/python -m app.swing_v4.v48_battery
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from app.backtest_v2 import benchmark, metrics
from app.backtest_v2.skew_robustness import (
    contributor_rotation,
    random_subset_retention,
)
from app.backtest_v2.validation import (
    DISCOVERY,
    ConfigLedger,
    deflated_sharpe,
    pbo_cscv,
)
from app.data.bhavcopy import store
from app.swing_v4 import engine
from app.swing_v4.config import SwingConfig
from app.swing_v4.regime import RegimeScore
from app.swing_v4.signals import precompute_swing_signals
from app.swing_v4.v41_cost_screen import (
    _BENCH_FETCH_END,
    _BENCH_FETCH_START,
    _candidate_config,
    _equity_series,
    _run,
    _s61_ratio,
)
from app.swing_v4.v41_forensic import Trade, _reconstruct_trades
from app.swing_v4.v44_selector_screen import _forensic

log = logging.getLogger(__name__)

# --- the survivor under test (`05` §4 Stage 2) -----------------------------
_CAND_ATR = 5.0
_CAND_CADENCE = "daily"
_CAND_NEUTRAL = 0.75

# §6.3 plateau grid: atr {3,4,5} × neutral {0.5,0.75}. Candidate = atr5/0.75.
_ATR_GRID = [3.0, 4.0, 5.0]
_NEUTRAL_GRID = [0.5, 0.75]
_PLATEAU_THRESHOLD = 0.85  # neighbor base Calmar ≥ 85% of candidate base Calmar

# §6.4 subperiods — identical fixed split to su2_battery/md2 (Rule 12, before any run).
_SUBPERIODS: list[tuple[str, str, str]] = [
    ("Pre-COVID chop", "2018-02-06", "2020-03-31"),
    ("Post-COVID bull", "2020-04-01", "2022-01-31"),
    ("Rate-hike correction", "2022-02-01", "2023-06-30"),
]

# §7 K / DSR. Carried v4 K = 4; V4.7 Stage-1 +6 ⇒ 10; Stage-2 (0.5 deploy plateau-neighbor
# arm + its atr neighbors) ≈ +3 ⇒ K ≈ 13 at OOS (`05` §7.1). Report DSR across a small band.
_K_HEADLINE = 13
_K_BAND = [10, 12, 13, 14]

# §5 anti-thrash diagnostic bundle (10 td each, `05` §5).
_MIN_HOLD_TD = 10
_REENTRY_COOLDOWN_TD = 10

# leave-top-k-out demonstration.
_LEAVE_TOP_K = [0, 1, 2, 5, 10, 20]

# CSCV PBO: slice each config's full-DISCOVERY daily-return series into N contiguous folds
# (the textbook CSCV construction — split the single track record, no re-simulation).
_PBO_FOLDS = 8


# ---------------------------------------------------------------------------
# config helpers
# ---------------------------------------------------------------------------


def _base_cfg(atr: float = _CAND_ATR) -> SwingConfig:
    """Candidate config (DISCOVERY window) with the plateau atr lever set."""
    return _candidate_config(
        exit_type=3, atr_mult=atr, decision_cadence=_CAND_CADENCE, selector="mom"
    )


def _closed_trades(res: engine.SwingEngineResult) -> list[Trade]:
    trades = _reconstruct_trades(res.fills_log, res.exit_log)
    return [t for t in trades if t.exit_reason != "still_open"]


def _per_year_top_contributors(
    res: engine.SwingEngineResult, top_n: int = 10
) -> dict[int, list[str]]:
    """Per calendar year, the top-`top_n` symbols by that year's realized net cashflow
    (mirrors vt2_battery._per_year_top_contributors — 09 §6.2b). Identity = symbol."""
    by_year: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for f in res.fills_log:
        notional = f.qty * f.price
        signed = notional if f.side in ("sell", "trim") else -notional
        by_year[f.date.year][f.symbol] += signed - f.cost_rupees
    out: dict[int, list[str]] = {}
    for yr, names in by_year.items():
        ranked = sorted(names.items(), key=lambda kv: kv[1], reverse=True)
        out[yr] = [sym for sym, _ in ranked[:top_n]]
    return out


def _calmar_from_returns(rets: np.ndarray) -> float:
    """Annualized Calmar from a daily-return slice: CAGR / maxDD. Flat/positive-only
    slice (no drawdown) → NaN (excluded from the CSCV matrix via nan_to_num→0)."""
    rets = np.asarray(rets, dtype=float)
    if len(rets) < 2:
        return float("nan")
    eq = np.cumprod(1.0 + rets)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(-dd.min())
    years = len(rets) / 252.0
    if years <= 0 or eq[-1] <= 0:
        return float("nan")
    cagr = eq[-1] ** (1.0 / years) - 1.0
    if max_dd <= 0:
        return float("nan")
    return cagr / max_dd


def _emit(L: list[str], s: str = "") -> None:
    print(s, flush=True)
    L.append(s)


# ---------------------------------------------------------------------------
# result container
# ---------------------------------------------------------------------------


@dataclass
class BatteryResult:
    base_calmar: float
    base_sharpe: float
    base_maxdd: float
    base_cagr: float
    base_turnover: float
    # §6.1
    s61_c_strat: float
    s61_c_n50: float
    s61_ratio: float
    s61_pass: bool
    # §6.2
    s62_median_ret: float
    s62_p5_ret: float
    s62_rs_pass: bool
    s62_n_distinct: int
    s62_rot_pass: bool
    s62_classic_ret: float
    s62_pass: bool
    # §6.3
    plateau: dict[tuple[float, float], float]  # (atr, neutral) -> base Calmar
    s63_neighbors: dict[str, tuple[float, float]]  # label -> (calmar, retention)
    s63_pass: bool
    # deploy bar
    deploy_strat_calmar: float
    deploy_bench_calmar: float
    deploy_maxdd_ratio: float
    deploy_pass: bool
    # §6.4 (diagnostic)
    s64: dict[str, float]
    s64_n_positive: int
    # §7 context
    dsr: dict[int, float]
    raw_sharpe: float
    pbo: float
    pbo_n_configs: int
    pbo_n_folds: int
    # non-gating
    anti_thrash: dict[str, float]
    leave_top_k: list[tuple[int, float, float]]  # (k, remaining_net, cagr)
    # bookkeeping
    k_added: int


# ---------------------------------------------------------------------------
# the battery
# ---------------------------------------------------------------------------


def run_battery(
    prices: pd.DataFrame,
    regime_075: RegimeScore,
    regime_05: RegimeScore,
    signal_store,
    tri_nifty50: pd.Series,
    ledger: ConfigLedger,
) -> BatteryResult:
    regimes = {0.5: regime_05, 0.75: regime_075}
    cap = _base_cfg().starting_capital

    # --- candidate base + pessimistic ------------------------------------
    log.info("Candidate atr5/daily/0.75 — base + pessimistic ...")
    cand_cfg = _base_cfg(_CAND_ATR)
    ledger.add(
        {
            "atr_mult": _CAND_ATR,
            "cadence": _CAND_CADENCE,
            "neutral": _CAND_NEUTRAL,
            "cost": "base",
        },
        stage="V4.8_candidate",
    )
    res_base = _run(
        cand_cfg,
        prices=prices,
        regime=regime_075,
        signal_store=signal_store,
        cost_level="base",
        whole_shares=True,
    )
    m_base = metrics.compute_metrics(res_base)
    base_calmar = m_base.calmar

    res_pess = _run(
        cand_cfg,
        prices=prices,
        regime=regime_075,
        signal_store=signal_store,
        cost_level="pessimistic",
        whole_shares=True,
    )
    c_strat, c_n50, ratio = _s61_ratio(res_pess, tri_nifty50, cap)
    s61_pass = ratio >= 1.0

    # --- §6.2 skew-aware --------------------------------------------------
    held_isins = [ns.isin for ns in m_base.per_name_stats]
    log.info(
        "§6.2a random-subset retention (200×drop-10) on %d held names ...",
        len(held_isins),
    )

    def run_perturbed(drop_set: frozenset[str]) -> float:
        prices_p = prices[~prices["isin"].isin(drop_set)]
        res_p = _run(
            cand_cfg,
            prices=prices_p,
            regime=regime_075,
            signal_store=signal_store,
            cost_level="base",
            whole_shares=True,
        )
        return metrics.compute_metrics(res_p).calmar

    rs = random_subset_retention(held_isins, base_calmar, run_perturbed)
    log.info("    %s", rs.summary)
    per_year = _per_year_top_contributors(res_base)
    rot = contributor_rotation(per_year)
    log.info("    %s", rot.summary)
    # classic drop-top-10 realized P&L (contamination guard, DIAGNOSTIC)
    top10 = sorted(m_base.per_name_stats, key=lambda ns: ns.realized_pnl, reverse=True)[
        :10
    ]
    classic_calmar = run_perturbed(frozenset(ns.isin for ns in top10))
    classic_ret = classic_calmar / base_calmar if base_calmar > 0 else float("nan")
    s62_pass = rs.passed and rot.passed

    # --- §6.3 plateau -----------------------------------------------------
    log.info("§6.3 plateau grid (atr{3,4,5} × neutral{0.5,0.75}) ...")
    plateau: dict[tuple[float, float], float] = {}
    for atr in _ATR_GRID:
        for neu in _NEUTRAL_GRID:
            if atr == _CAND_ATR and neu == _CAND_NEUTRAL:
                plateau[(atr, neu)] = base_calmar
                continue
            ledger.add(
                {"atr_mult": atr, "neutral": neu, "cost": "base"}, stage="V4.8_plateau"
            )
            r = _run(
                _base_cfg(atr),
                prices=prices,
                regime=regimes[neu],
                signal_store=signal_store,
                cost_level="base",
                whole_shares=True,
            )
            plateau[(atr, neu)] = metrics.compute_metrics(r).calmar
            log.info(
                "    atr%.1f/neutral%.2f base Calmar %.3f",
                atr,
                neu,
                plateau[(atr, neu)],
            )

    # ±1-step neighbors of the candidate (atr5 boundary → only atr4; neutral 0.75 → 0.5)
    nbr_keys = {"atr 4.0 / 0.75": (4.0, 0.75), "atr 5.0 / 0.50": (5.0, 0.5)}
    s63_neighbors: dict[str, tuple[float, float]] = {}
    s63_pass = base_calmar > 0
    for label, key in nbr_keys.items():
        c = plateau[key]
        ret = c / base_calmar if base_calmar > 0 else float("nan")
        s63_neighbors[label] = (c, ret)
        if not (ret >= _PLATEAU_THRESHOLD):
            s63_pass = False

    # --- deploy bar (base cost) ------------------------------------------
    trading_cal = [pd.Timestamp(s.date) for s in res_base.snapshots]
    bench_base = benchmark.align_benchmark(tri_nifty50, DISCOVERY[0], trading_cal, cap)
    bm = metrics.compute_benchmark_metrics(_equity_series(res_base), bench_base)
    deploy_pass = bm.strategy_calmar > bm.benchmark_calmar and bm.max_dd_ratio <= 1.0

    # --- §6.4 subperiods (diagnostic) + PBO matrix -----------------------
    log.info("§6.4 subperiods (candidate) + PBO matrix (plateau grid, CSCV) ...")
    s64: dict[str, float] = {}
    for label, sub_a, sub_b in _SUBPERIODS:
        cfg_sub = replace(
            cand_cfg,
            date_from=pd.Timestamp(sub_a).date(),
            date_to=pd.Timestamp(sub_b).date(),
        )
        ledger.add({"subperiod": label, "cost": "base"}, stage="V4.8_s64")
        r = _run(
            cfg_sub,
            prices=prices,
            regime=regime_075,
            signal_store=signal_store,
            cost_level="base",
            whole_shares=True,
        )
        s64[label] = metrics.compute_metrics(r).calmar
        log.info("    §6.4 %-22s Calmar %.3f", label, s64[label])
    s64_n_positive = sum(1 for c in s64.values() if c == c and c > 0)

    # PBO via CSCV — slice each plateau config's full-DISCOVERY return series into folds.
    pbo, pbo_nc, pbo_nf = _compute_pbo(
        prices, regimes, signal_store, plateau, cand_cfg, res_base
    )

    # --- §7 DSR ----------------------------------------------------------
    base_ret = _equity_series(res_base).pct_change().dropna().to_numpy(dtype=float)
    raw_sharpe = m_base.sharpe
    dsr = {k: deflated_sharpe(raw_sharpe, base_ret, k) for k in _K_BAND}

    # --- §5 anti-thrash (non-gating) -------------------------------------
    log.info("§5 anti-thrash on the survivor (± min_hold/cooldown) ...")
    cfg_on = replace(
        cand_cfg, min_hold_td=_MIN_HOLD_TD, reentry_cooldown_td=_REENTRY_COOLDOWN_TD
    )
    res_on = _run(
        cfg_on,
        prices=prices,
        regime=regime_075,
        signal_store=signal_store,
        cost_level="base",
        whole_shares=True,
    )
    m_on = metrics.compute_metrics(res_on)
    fr_off, fr_on = _forensic(res_base), _forensic(res_on)
    anti = {
        "off_turnover": m_base.annualized_turnover * 100,
        "off_calmar": base_calmar,
        "off_medhold": fr_off.median_hold,
        "off_fills": m_base.n_fills,
        "on_turnover": m_on.annualized_turnover * 100,
        "on_calmar": m_on.calmar,
        "on_medhold": fr_on.median_hold,
        "on_fills": m_on.n_fills,
    }

    # --- leave-top-k-out demonstration (non-gating, P&L attribution) -----
    closed = _closed_trades(res_base)
    pnl_sorted = sorted((t.net_pnl for t in closed), reverse=True)
    total_net = sum(pnl_sorted)
    years = (pd.Timestamp(DISCOVERY[1]) - pd.Timestamp(DISCOVERY[0])).days / 365.25
    leave_top_k: list[tuple[int, float, float]] = []
    for k in _LEAVE_TOP_K:
        remaining = total_net - sum(pnl_sorted[:k])
        tot_ret = remaining / cap
        cagr = (
            (1.0 + tot_ret) ** (1.0 / years) - 1.0 if tot_ret > -1.0 else float("nan")
        )
        leave_top_k.append((k, remaining, cagr))

    return BatteryResult(
        base_calmar=base_calmar,
        base_sharpe=raw_sharpe,
        base_maxdd=m_base.max_drawdown,
        base_cagr=m_base.cagr,
        base_turnover=m_base.annualized_turnover * 100,
        s61_c_strat=c_strat,
        s61_c_n50=c_n50,
        s61_ratio=ratio,
        s61_pass=s61_pass,
        s62_median_ret=rs.median_retention,
        s62_p5_ret=rs.p5_retention,
        s62_rs_pass=rs.passed,
        s62_n_distinct=rot.n_distinct,
        s62_rot_pass=rot.passed,
        s62_classic_ret=classic_ret,
        s62_pass=s62_pass,
        plateau=plateau,
        s63_neighbors=s63_neighbors,
        s63_pass=s63_pass,
        deploy_strat_calmar=bm.strategy_calmar,
        deploy_bench_calmar=bm.benchmark_calmar,
        deploy_maxdd_ratio=bm.max_dd_ratio,
        deploy_pass=deploy_pass,
        s64=s64,
        s64_n_positive=s64_n_positive,
        dsr=dsr,
        raw_sharpe=raw_sharpe,
        pbo=pbo,
        pbo_n_configs=pbo_nc,
        pbo_n_folds=pbo_nf,
        anti_thrash=anti,
        leave_top_k=leave_top_k,
        k_added=ledger.n_trials,
    )


def _compute_pbo(prices, regimes, signal_store, plateau, cand_cfg, res_base):
    """CSCV PBO over the 6 plateau configs. Each config's full-DISCOVERY daily-return
    series is sliced into _PBO_FOLDS contiguous folds; perf[config, fold] = fold Calmar."""
    configs = [(atr, neu) for atr in _ATR_GRID for neu in _NEUTRAL_GRID]
    # reuse the candidate's already-computed return series; rerun the other 5 once.
    ret_by_cfg: dict[tuple[float, float], np.ndarray] = {}
    for atr, neu in configs:
        if atr == _CAND_ATR and neu == _CAND_NEUTRAL:
            r = res_base
        else:
            r = _run(
                _base_cfg(atr),
                prices=prices,
                regime=regimes[neu],
                signal_store=signal_store,
                cost_level="base",
                whole_shares=True,
            )
        ret_by_cfg[(atr, neu)] = (
            _equity_series(r).pct_change().dropna().to_numpy(dtype=float)
        )

    n_fold = _PBO_FOLDS
    perf = np.full((len(configs), n_fold), np.nan, dtype=float)
    for j, key in enumerate(configs):
        rets = ret_by_cfg[key]
        edges = np.linspace(0, len(rets), n_fold + 1, dtype=int)
        for k in range(n_fold):
            perf[j, k] = _calmar_from_returns(rets[edges[k] : edges[k + 1]])
    perf = np.nan_to_num(perf, nan=0.0)
    pbo = pbo_cscv(perf, higher_is_better=True)
    return pbo, len(configs), n_fold


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _report(r: BatteryResult, ledger: ConfigLedger) -> list[str]:
    L: list[str] = []
    P = lambda b: "PASS" if b else "FAIL"  # noqa: E731
    _emit(L)
    _emit(L, "=" * 100)
    _emit(L, "  V4.8 — FULL §6 acceptance battery on the §6.1 survivor")
    _emit(
        L,
        f"  Survivor: atr 5.0 / daily / neutral 0.75 | DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}",
    )
    _emit(
        L,
        f"  base: Calmar {r.base_calmar:.3f} | Sharpe {r.base_sharpe:.2f} | "
        f"maxDD {r.base_maxdd:.1%} | CAGR {r.base_cagr:.2%} | turnover {r.base_turnover:.0f}%",
    )
    _emit(L, "=" * 100)

    _emit(L)
    _emit(L, f"  §6.1  cost survival (pessimistic) — {P(r.s61_pass)}")
    _emit(
        L,
        f"        C_strat {r.s61_c_strat:.3f} / C_nifty50 {r.s61_c_n50:.3f} = ratio "
        f"{r.s61_ratio:.2f}  (bar ≥ 1.0)",
    )

    _emit(L)
    _emit(L, f"  §6.2  skew-aware concentration — {P(r.s62_pass)}")
    _emit(
        L,
        f"        (a) random-subset retention: median {r.s62_median_ret:.0%} (bar ≥ 70%), "
        f"p5 {r.s62_p5_ret:.0%} (bar ≥ 50%) → {P(r.s62_rs_pass)}",
    )
    _emit(
        L,
        f"        (b) contributor rotation: {r.s62_n_distinct} distinct top-10/yr "
        f"(bar ≥ 25) → {P(r.s62_rot_pass)}",
    )
    _emit(
        L,
        f"        classic drop-top-10 retention {r.s62_classic_ret:.0%} "
        "(DIAGNOSTIC contamination guard, not gating)",
    )

    _emit(L)
    _emit(
        L,
        f"  §6.3  plateau (neighbors ≥ {_PLATEAU_THRESHOLD:.0%} of base {r.base_calmar:.3f}) — {P(r.s63_pass)}",
    )
    _emit(L, "        full grid base Calmar:")
    for atr in _ATR_GRID:
        cells = "  ".join(
            f"n{neu:.2f}={r.plateau[(atr, neu)]:.3f}" for neu in _NEUTRAL_GRID
        )
        _emit(L, f"          atr{atr:.1f}:  {cells}")
    for label, (c, ret) in r.s63_neighbors.items():
        _emit(
            L,
            f"        neighbor {label}: Calmar {c:.3f} = {ret:.0%} of base → "
            f"{P(ret >= _PLATEAU_THRESHOLD)}",
        )

    _emit(L)
    _emit(L, f"  deploy bar (base) — {P(r.deploy_pass)}")
    _emit(
        L,
        f"        strat Calmar {r.deploy_strat_calmar:.3f} vs Nifty50 TRI "
        f"{r.deploy_bench_calmar:.3f}; maxDD ratio {r.deploy_maxdd_ratio:.2f} (bar ≤ 1.0)",
    )

    _emit(L)
    _emit(
        L,
        f"  §6.4  subperiod stability (DIAGNOSTIC) — n_positive {r.s64_n_positive}/{len(r.s64)}",
    )
    for label, c in r.s64.items():
        _emit(L, f"        {label:<24} Calmar {c:.3f}")

    _emit(L)
    _emit(L, "  §7 deflation context (reported, not a gate):")
    _emit(
        L,
        f"        raw Sharpe {r.raw_sharpe:.3f} → DSR: "
        + "  ".join(f"K{k}={r.dsr[k]:+.3f}" for k in _K_BAND)
        + f"  (headline K={_K_HEADLINE})",
    )
    _emit(
        L,
        f"        PBO (CSCV, {r.pbo_n_configs} configs × {r.pbo_n_folds} folds) "
        f"{r.pbo:.2f}  (coarse-fold cross-check)",
    )

    _emit(L)
    _emit(L, "  §5 anti-thrash on the survivor (NON-GATING, 0 to K):")
    a = r.anti_thrash
    _emit(
        L,
        f"        OFF: turn {a['off_turnover']:.0f}% | medHold {a['off_medhold']:.0f}d | "
        f"fills {a['off_fills']:.0f} | Calmar {a['off_calmar']:.3f}",
    )
    _emit(
        L,
        f"        ON : turn {a['on_turnover']:.0f}% | medHold {a['on_medhold']:.0f}d | "
        f"fills {a['on_fills']:.0f} | Calmar {a['on_calmar']:.3f}",
    )

    _emit(L)
    _emit(
        L,
        "  leave-top-k-out fragility DEMONSTRATION (NON-GATING, 0 to K — P&L attribution,",
    )
    _emit(
        L,
        "  not a re-simulation; shows how fast the edge vanishes — Arafat 2026-06-25):",
    )
    _emit(
        L,
        f"        {'remove top-k':>12} | {'remaining net P&L':>18} | {'attrib. CAGR':>12}",
    )
    for k, remaining, cagr in r.leave_top_k:
        tag = "  (full book)" if k == 0 else ""
        cagr_s = f"{cagr:+.2%}" if cagr == cagr else "n/a (≤−100%)"
        _emit(L, f"        {k:>12} | ₹{remaining:>16,.0f} | {cagr_s:>12}{tag}")

    # verdict
    gates = {
        "§6.1": r.s61_pass,
        "§6.2": r.s62_pass,
        "§6.3": r.s63_pass,
        "deploy": r.deploy_pass,
    }
    all_pass = all(gates.values())
    fails = [g for g, ok in gates.items() if not ok]
    _emit(L)
    _emit(L, "=" * 100)
    if all_pass:
        _emit(
            L,
            "  VERDICT: ALL §6 GATES PASS → atr5/daily/0.75 is the single locked OOS candidate.",
        )
        _emit(
            L,
            "  → V4.9 may touch v4-FINAL_OOS EXACTLY ONCE on this config (and only this config).",
        )
    else:
        _emit(
            L,
            f"  VERDICT: NULL — failed {', '.join(fails)}. The turnover lever does NOT rescue the",
        )
        _emit(
            L,
            "  thin trend edge: the §6.1 survivor's edge is a single-name fat tail (pre-V4.8",
        )
        _emit(
            L,
            "  diagnostic: 87% of net P&L = ATGL), which the skew-aware §6.2 / lone-peak §6.3",
        )
        _emit(
            L,
            "  catch by construction. Per `05` §6 pre-accepted null, the v4 family is PERMANENTLY",
        )
        _emit(
            L,
            "  and FINALLY closed; v4-FINAL_OOS is NOT touched; no lever added, no threshold loosened.",
        )
    _emit(
        L,
        f"  K added this run: {ledger.n_trials} (carried v4 K=4 ⇒ K ≈ {4 + ledger.n_trials}). "
        "v4-FINAL_OOS untouched.",
    )
    _emit(L, "=" * 100)
    return L


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # ERROR (not WARNING) — the §6.2 200-draw step drops held names from prices, which
    # makes portfolio.py emit a benign carry-last MTM WARNING per name per day. At 200
    # draws that is millions of log lines: it floods stdout and throttles the run to a
    # crawl (the observed 55-min stall). Silence warnings; keep our INFO progress on root.
    for noisy in (
        "app.backtest_v2.portfolio",
        "app.backtest_v2",
        "app.swing_v4.engine",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    print(
        "v4 / 05 V4.8 — full §6 battery on the atr5/daily/0.75 survivor (DISCOVERY only)"
    )
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]} | FINAL_OOS untouched")
    print()

    print("Loading prices_adjusted...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(f"  rows={len(prices):,} ISINs={prices['isin'].nunique():,}", flush=True)

    print(
        "Loading Nifty 50 price index + market_internals (regime) + Nifty 50 TRI...",
        flush=True,
    )
    px = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    mi = store.read_market_internals()
    if mi.empty:
        print("FAIL: market_internals empty.", file=sys.stderr)
        return 2
    tri_nifty50 = benchmark.load_tri(
        benchmark.TRI_NIFTY_50, _BENCH_FETCH_START, _BENCH_FETCH_END
    )

    print("Precomputing swing signals + regime (neutral 0.75 and 0.5)...", flush=True)
    ref_cfg = _base_cfg(_CAND_ATR)
    signal_store = precompute_swing_signals(prices, ref_cfg)
    regime_075 = RegimeScore(px, mi, ref_cfg, neutral_fraction=0.75)
    regime_05 = RegimeScore(px, mi, ref_cfg, neutral_fraction=0.5)

    ledger = ConfigLedger()
    print(
        "\nRunning the V4.8 battery (this is the expensive 200-draw §6.2 step)...",
        flush=True,
    )
    res = run_battery(prices, regime_075, regime_05, signal_store, tri_nifty50, ledger)

    lines = _report(res, ledger)
    out_path = "reports/v48_battery.txt"
    try:
        with open(out_path, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"\n(report written to backend/{out_path})", flush=True)
    except OSError as e:  # pragma: no cover
        print(f"\n(could not write report: {e})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
