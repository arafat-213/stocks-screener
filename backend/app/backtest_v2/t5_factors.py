"""
t5_factors.py — v3 / Track-A T5: factor layers on DISCOVERY (H2).

Adds the four Track-A price/volume factors ONE AT A TIME on top of the T4
turnover-stable base, testing prereg H2: a blended multi-factor score selects a
broader, more stable set than single-factor momentum → the §6.2 top-10-drop
retention rises (toward the 70% bar v2 failed).

Two pre-registered ingredients (specs/v3/00_PREREGISTRATION.md → §5, §6, §9):

  1. GATE — §6 plateau (04 §4). Each layer holds all prior-accepted knobs fixed,
     runs on DISCOVERY only, logs to the ledger, and a factor is ACCEPTED iff
     adding it does NOT wreck Calmar: Calmar(base+F) >= 0.85 × Calmar(base).
     (Improving Calmar is never penalised.) The formal `iterate.plateau_check`
     verdict on the 2-point {without, with} grid is reported alongside as the
     neighbourhood signal. A factor that drops Calmar below tolerance is a SPIKE
     → rejected, honestly stated (Rule 12); accepted factors chain forward.

  2. DIAGNOSTIC — §6.2 top-10-drop retention (prereg line 56: "the signal we care
     about", NOT the final gate). Computed by robustness.py's exact method: drop
     the top-10 realized-P&L names, re-run, retention = perturbed_calmar /
     base_calmar. Tracked per layer so the concentration TREND is visible — the
     H2 story is whether the blend lifts retention toward 0.70.

Base = T4's plateau-selected turnover-stable config: cadence=monthly, M=70,
smoothing=0, active={mom_12_1}. The momentum-only base must reproduce T4's L3
selected run (Calmar 0.250 / turnover 800% / 1265 fills) — a wiring sanity check.

DISCOVERY only — FINAL_OOS stays pristine for T6/T7. Offline: prices and the
regime index load from the local cache; never live yfinance/NSE (Rule 5).

Run:
    backend/venv/bin/python -m app.backtest_v2.t5_factors
"""

from __future__ import annotations

import dataclasses
import logging
import math
import sys
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.iterate import GridPoint, plateau_check
from app.backtest_v2.robustness import (
    N_TOP_CONTRIBUTORS,
    UNIVERSE_PERTURB_THRESHOLD,
)
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.v3_config import FACTOR_LAYERS, V3Config
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

# Regime index range — same cache key as floor.py / iterate.py / t4 (offline hit).
_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Plateau tolerance — the same 0.85 fraction T4 / the regime layer / the T0 GO
# predicate use (04 §4): the with-factor Calmar must hold >= 85% of the base.
_TOL = 0.85

# T4 plateau-selected turnover-stable base (specs/v3/01 → T4 session log).
_BASE_CADENCE = "monthly"
_BASE_BUFFER_M = 70
_BASE_SMOOTHING = 0

# T4 L3 selected-run fingerprint — the momentum-only base on this config must
# reproduce these to confirm no wiring drift from T4 (sanity, not a re-search).
_T4_BASE_CALMAR = 0.250
_T4_BASE_TURNOVER = 8.00  # fraction (800%)
_T4_BASE_FILLS = 1265


# ---------------------------------------------------------------------------
# Config mapping (mirrors t4_turnover._engine_cfg — run scripts stay independent)
# ---------------------------------------------------------------------------


def _engine_cfg(v3cfg: V3Config, date_from: date, date_to: date) -> MomentumConfig:
    """Project the V3Config knobs the engine consumes for selection/sizing onto a
    MomentumConfig (cadence → `rebalance`, buffer → `sell_rank_buffer`). The
    multi-factor ordering rides in via the signal_store, not this config."""
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


# ---------------------------------------------------------------------------
# Single run → stats; and the §6.2 retention re-run
# ---------------------------------------------------------------------------


@dataclass
class RunStats:
    calmar: float
    turnover: float  # annualized realized Σ|Δw| (executed rebalances)
    sharpe: float
    cagr: float
    max_dd: float
    final_equity: float
    n_fills: int


def _stats(res: engine.EngineResult, m: metrics.BacktestMetrics) -> RunStats:
    return RunStats(
        calmar=m.calmar,
        turnover=m.annualized_turnover,
        sharpe=m.sharpe,
        cagr=m.cagr,
        max_dd=m.max_drawdown,
        final_equity=res.snapshots[-1].equity if res.snapshots else float("nan"),
        n_fills=len(res.fills_log),
    )


def _run(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    eng_cfg: MomentumConfig,
    signal_store,
) -> tuple[RunStats, metrics.BacktestMetrics]:
    res = engine.run(
        prices,
        eng_cfg,
        index_prices=index_prices,
        cost_level="base",
        signal_store=signal_store,
    )
    m = metrics.compute_metrics(res)
    return _stats(res, m), m


def _top10_retention(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    eng_cfg: MomentumConfig,
    signal_store,
    base_m: metrics.BacktestMetrics,
) -> tuple[float, list[str]]:
    """§6.2 diagnostic (robustness.check_universe_perturbation method): drop the
    top-N realized-P&L names, re-run with the SAME signal_store on perturbed
    prices (the engine derives its universe from prices, so dropped ISINs are
    structurally excluded from ranking), retention = perturbed_calmar/base_calmar.
    Higher retention = edge is LESS name-concentrated = broader selection (H2)."""
    sorted_names = sorted(
        base_m.per_name_stats, key=lambda ns: ns.realized_pnl, reverse=True
    )
    top = sorted_names[:N_TOP_CONTRIBUTORS]
    top_isins = {ns.isin for ns in top}
    top_symbols = [ns.symbol for ns in top]

    prices_perturbed = prices[~prices["isin"].isin(top_isins)].copy()
    res = engine.run(
        prices_perturbed,
        eng_cfg,
        index_prices=index_prices,
        cost_level="base",
        signal_store=signal_store,
    )
    m_pert = metrics.compute_metrics(res)

    base_calmar = base_m.calmar
    if base_calmar > 0 and not math.isnan(base_calmar):
        retention = m_pert.calmar / base_calmar
    else:
        retention = float("nan")
    return retention, top_symbols


# ---------------------------------------------------------------------------
# Per-factor accept/reject verdict (Calmar plateau gate + retention diagnostic)
# ---------------------------------------------------------------------------


@dataclass
class FactorVerdict:
    factor: str
    accepted: bool
    base_stats: RunStats
    base_ret: float
    cand_stats: RunStats
    cand_ret: float
    plateau_ok: bool
    explanation: str


def _fmt_ret(r: float) -> str:
    return "n/a" if math.isnan(r) else f"{r:.0%}"


def _eval_factor(
    fac: str,
    base_stats: RunStats,
    base_ret: float,
    cand_stats: RunStats,
    cand_ret: float,
) -> FactorVerdict:
    """ACCEPT iff adding `fac` keeps Calmar on the plateau (>= _TOL × base). The
    §6.2 retention move is reported as the H2 diagnostic, not the gate."""
    threshold = _TOL * base_stats.calmar
    accept = cand_stats.calmar >= threshold

    # Formal plateau verdict on the 2-point {without, with} grid (neighbourhood).
    gps = [
        GridPoint(
            params={f"+{fac}": False},
            trial_id=0,
            calmar=base_stats.calmar,
            sharpe=base_stats.sharpe,
            cagr=base_stats.cagr,
            max_dd=base_stats.max_dd,
        ),
        GridPoint(
            params={f"+{fac}": True},
            trial_id=0,
            calmar=cand_stats.calmar,
            sharpe=cand_stats.sharpe,
            cagr=cand_stats.cagr,
            max_dd=cand_stats.max_dd,
        ),
    ]
    verdict = plateau_check(gps, axes=[(f"+{fac}", [False, True])], tolerance=_TOL)

    if math.isnan(base_ret) or math.isnan(cand_ret):
        h2 = "retention n/a"
    elif cand_ret > base_ret + 1e-9:
        h2 = "broadens (retention up)"
    elif cand_ret < base_ret - 1e-9:
        h2 = "narrows (retention down)"
    else:
        h2 = "retention flat"

    explanation = (
        f"+{fac}: Calmar {base_stats.calmar:.3f} → {cand_stats.calmar:.3f} "
        f"({'ACCEPT' if accept else 'REJECT'} — "
        f"{'>=' if accept else '<'} {_TOL:.0%}×base {threshold:.3f}); "
        f"§6.2 retention {_fmt_ret(base_ret)} → {_fmt_ret(cand_ret)} ({h2}); "
        f"turnover {base_stats.turnover * 100:.0f}% → {cand_stats.turnover * 100:.0f}%; "
        f"neighbourhood: {'PLATEAU' if verdict.has_plateau else 'SPIKE'}"
    )
    return FactorVerdict(
        factor=fac,
        accepted=accept,
        base_stats=base_stats,
        base_ret=base_ret,
        cand_stats=cand_stats,
        cand_ret=cand_ret,
        plateau_ok=verdict.has_plateau,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_layers(
    base_stats: RunStats,
    base_ret: float,
    verdicts: list[FactorVerdict],
) -> None:
    print("\n" + "=" * 78)
    print("  T5 — FACTOR LAYERS (one at a time on the T4 base; H2 = §6.2 retention)")
    print("=" * 78)
    print(
        f"  {'step':>22} {'Calmar':>8} {'Turnover%':>10}"
        f" {'Retention':>10} {'decision':>9}"
    )
    print(f"  {'─' * 22} {'─' * 8} {'─' * 10} {'─' * 10} {'─' * 9}")
    print(
        f"  {'base {mom_12_1}':>22} {base_stats.calmar:>8.3f}"
        f" {base_stats.turnover * 100:>10.0f} {_fmt_ret(base_ret):>10} {'(base)':>9}"
    )
    for v in verdicts:
        decision = "ACCEPT" if v.accepted else "REJECT"
        print(
            f"  {'+' + v.factor:>22} {v.cand_stats.calmar:>8.3f}"
            f" {v.cand_stats.turnover * 100:>10.0f} {_fmt_ret(v.cand_ret):>10}"
            f" {decision:>9}"
        )
    print()
    for v in verdicts:
        print(f"  {v.explanation}")


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

    print("v3 / T5 — Factor layers on DISCOVERY (H2)")
    print(
        f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}  (base cost, regime ON)"
    )
    print(
        f"  T4 base: cadence={_BASE_CADENCE}  M={_BASE_BUFFER_M}  "
        f"smoothing={_BASE_SMOOTHING}  N=20"
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

    # T4 turnover-stable base config (momentum-only floor on it).
    base_cfg = V3Config(
        sell_rank_buffer=_BASE_BUFFER_M,
        rebalance_cadence=_BASE_CADENCE,
        rank_smoothing_months=_BASE_SMOOTHING,
        active_factors=["mom_12_1"],
        date_from=DISCOVERY[0],
        date_to=DISCOVERY[1],
    )

    # v2 indicator cache (gate inputs) — built ONCE, reused for every store. The
    # momentum-positive gate stays active throughout (mom_12_1 is in every blend).
    print("Precomputing v2 indicator cache on DISCOVERY (shared gate)...", flush=True)
    gate_store = precompute_signals(prices, _engine_cfg(base_cfg, *DISCOVERY))
    ind = gate_store._data

    ledger = ConfigLedger()

    # ----------------------------------------------------------------------- #
    # BASE — momentum-only on the T4 turnover-stable config (Calmar + retention)
    # ----------------------------------------------------------------------- #
    print("\nBase — momentum-only floor on the T4 base...", flush=True)
    base_eng = _engine_cfg(base_cfg, *DISCOVERY)
    base_comp = factors.composite_rank(prices, base_cfg)
    base_store = V3SignalStore(ind, base_comp, base_cfg)
    ledger.add(
        {"active_factors": list(base_cfg.active_factors), "base": "t4"},
        layer="t5_base",
    )
    base_stats, base_m = _run(prices, index_prices, base_eng, base_store)
    base_ret, base_dropped = _top10_retention(
        prices, index_prices, base_eng, base_store, base_m
    )
    print(
        f"  Calmar={base_stats.calmar:.3f}  turnover={base_stats.turnover * 100:.0f}%"
        f"  fills={base_stats.n_fills}  §6.2 retention={_fmt_ret(base_ret)}",
        flush=True,
    )

    # Wiring sanity vs T4 L3 selected run (Calmar 0.250 / 800% / 1265 fills).
    calmar_ok = abs(base_stats.calmar - _T4_BASE_CALMAR) < 0.002
    turnover_ok = abs(base_stats.turnover - _T4_BASE_TURNOVER) < 0.02
    fills_ok = base_stats.n_fills == _T4_BASE_FILLS
    if calmar_ok and turnover_ok and fills_ok:
        print("  ✓ reproduces T4 L3 selected base (0.250 / 800% / 1265) — no drift.")
    else:
        print(
            f"  ⚠ WARNING: base differs from T4 L3 record "
            f"(0.250 / 800% / 1265). Calmar_ok={calmar_ok} "
            f"turnover_ok={turnover_ok} fills_ok={fills_ok}. "
            "Investigate wiring drift before trusting T5 (Rule 12).",
            file=sys.stderr,
        )

    # ----------------------------------------------------------------------- #
    # FACTOR LAYERS — add one at a time, chain accepted forward (04 §4)
    # ----------------------------------------------------------------------- #
    accepted_factors = list(base_cfg.active_factors)
    cur_stats, cur_ret = base_stats, base_ret
    verdicts: list[FactorVerdict] = []

    for fac in FACTOR_LAYERS:
        trial_factors = accepted_factors + [fac]
        print(
            f"\nLayer — +{fac}  (active={trial_factors})...",
            flush=True,
        )
        cfg = dataclasses.replace(base_cfg, active_factors=trial_factors)
        comp = factors.composite_rank(prices, cfg)
        store_ = V3SignalStore(ind, comp, cfg)
        eng_c = _engine_cfg(cfg, *DISCOVERY)
        ledger.add({"active_factors": trial_factors}, layer=f"t5_add_{fac}")

        cand_stats, cand_m = _run(prices, index_prices, eng_c, store_)
        cand_ret, _ = _top10_retention(prices, index_prices, eng_c, store_, cand_m)

        v = _eval_factor(fac, cur_stats, cur_ret, cand_stats, cand_ret)
        verdicts.append(v)
        print(f"  {v.explanation}", flush=True)

        if v.accepted:
            accepted_factors = trial_factors
            cur_stats, cur_ret = cand_stats, cand_ret

    # ----------------------------------------------------------------------- #
    # Reports + the single v3 candidate config for T6
    # ----------------------------------------------------------------------- #
    _print_layers(base_stats, base_ret, verdicts)

    print("\n" + "=" * 78)
    print("  T5 SUMMARY — v3 candidate config")
    print("=" * 78)
    print(f"  Active factors : {accepted_factors}")
    print(f"  Cadence        : {_BASE_CADENCE}   M={_BASE_BUFFER_M}   N=20", flush=True)
    print(f"  Smoothing      : {_BASE_SMOOTHING} months")
    print(
        f"  Calmar         : {base_stats.calmar:.3f} (base) → {cur_stats.calmar:.3f} "
        "(candidate)"
    )
    print(
        f"  Realized turn. : {base_stats.turnover * 100:.0f}% → "
        f"{cur_stats.turnover * 100:.0f}%"
    )
    print(
        f"  §6.2 retention : {_fmt_ret(base_ret)} (base) → {_fmt_ret(cur_ret)} "
        f"(candidate)   [§9 bar: >= {UNIVERSE_PERTURB_THRESHOLD:.0%}]"
    )
    # H2 verdict — honest, no softening (Rule 12).
    if math.isnan(cur_ret):
        h2_verdict = "INCONCLUSIVE — retention undefined (non-positive base Calmar)"
    elif cur_ret >= UNIVERSE_PERTURB_THRESHOLD:
        h2_verdict = (
            f"SUPPORTED — candidate retention {cur_ret:.0%} clears the §9 "
            f"{UNIVERSE_PERTURB_THRESHOLD:.0%} bar (v2 failed this)"
        )
    elif cur_ret > base_ret + 1e-9:
        h2_verdict = (
            f"PARTIAL — retention rose {base_ret:.0%} → {cur_ret:.0%} but is still "
            f"below the §9 {UNIVERSE_PERTURB_THRESHOLD:.0%} bar"
        )
    else:
        h2_verdict = (
            f"NOT SUPPORTED — retention did not rise above base ({base_ret:.0%}); "
            "the blend did not broaden selection on DISCOVERY"
        )
    print(f"  H2 (§6.2)      : {h2_verdict}")
    print(f"  ConfigLedger trials: K = {ledger.n_trials}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
