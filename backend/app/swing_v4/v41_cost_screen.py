"""
v41_cost_screen.py — v4 / 00 V4.1: Stage 1 cost screen on full DISCOVERY.

Pre-registration: specs/v4/00_SWING_PREREG.md §5 (Stage 1) / §6 / §13 (V4.1).

What this runs (DISCOVERY only — FINAL_OOS stays pristine; no §6.2/§6.3/§6.4 here,
that is V4.2):

  Grid (§5 Stage 1 — the candidate + the two exit-rule alternatives, NOTHING else;
  every other axis frozen at the Amendment-1 candidate: target_positions=15, 5-factor
  regime, stable U=200, ₹3.5L, whole-share):
      T3  exit_type=3  ATR 3× trail   — the registered candidate
      T1  exit_type=1  MACD cross-down — exit-choice comparator (NOT a silent swap)
      T2  exit_type=2  close < EMA50   — exit-choice comparator

  For each config:
    - base cost       → base Calmar, maxDD, turnover, win rate (hit rate), avg hold.
    - pessimistic cost → §6.1 ratio = C_strat / C_nifty50  (≥ 1.0 clears §6.1).
    - both logged to ConfigLedger (K accrues — 00 §7; the v4 ledger starts at 0).

  Selection-quality diagnostic (§6, pre-registered 2026-06-24 — NON-GATING, adds 0 to K;
  candidate engine only, base cost, full DISCOVERY; only the cap+selector differ):
      B_liquid  top-15 by adv_20 (the candidate)        — reuses the T3 base run.
      B_random  random 15 when oversubscribed × N seeds  — median + p5 Calmar over seeds.
      B_all     no cap (target_positions ≫ footprint)    — capital-blind, whole_shares OFF.
  Pre-committed read (00 §6, ≥85% reuses the §6.3 plateau tolerance — no new number):
      neutral       B_liquid ≥ 85% of B_random median  ⇒ creaming costs ~nothing.
      favorable     B_liquid ≥ B_random median         ⇒ creaming mildly helps.
      edge-discard  B_liquid < 85% of B_random median AND materially below B_all
                    ⇒ authorizes a SEPARATE future amendment (never a swap this run).

Whole-share fidelity (Rule 12, surfaced): the deployable grid books (T1/T2/T3) and
B_liquid/B_random run whole_shares=True — the deployment-honest ₹3.5L screen Amendment 1
§14 E asks for (integer-share rounding drag is part of the cost the §6.1 gate must clear).
B_all runs whole_shares=False per 00 §6 (a capital-blind return-only reference; its sizes
are sub-tradeable at ₹3.5L, so Calmar/Sharpe are read scale-invariantly, NAV ignored).

Run:
    backend/venv/bin/python -m app.swing_v4.v41_cost_screen
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2 import benchmark, metrics
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store
from app.swing_v4 import engine
from app.swing_v4.config import SwingConfig
from app.swing_v4.regime import RegimeScore
from app.swing_v4.signals import precompute_swing_signals

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# §6 diagnostic: seeds for the B_random reference book. 20 gives a stable median and a
# meaningful 5th-percentile (p5) over the seed distribution. Each seed is a full engine
# run; the day-level draw is also seeded (engine.py) so the whole run is reproducible.
_N_RANDOM_SEEDS = 20
# B_all "no cap": a slot cap far above the U=200 stable-universe footprint (V4.0c re-run:
# max 167 concurrent) so the cap NEVER binds ⇒ the unconstrained ~46-name book.
_B_ALL_CAP = 250
# §6 / §6.3 plateau tolerance reused as the diagnostic read threshold (no new number).
_DIAG_TOL = 0.85


# §5 Stage-1 grid — candidate + the two exit-rule comparators. NOTHING else varies.
@dataclass
class GridConfig:
    name: str
    exit_type: int
    role: str


_GRID: list[GridConfig] = [
    GridConfig("T3", 3, "candidate — ATR 3× trail"),
    GridConfig("T1", 1, "comparator — MACD cross-down"),
    GridConfig("T2", 2, "comparator — close < EMA50"),
]


@dataclass
class ScreenRow:
    name: str
    role: str
    base_calmar: float
    base_max_dd: float
    base_sharpe: float
    turnover_pct: float
    win_rate: float
    avg_hold_days: float
    n_fills: int
    c_strat_pessimistic: float
    c_nifty50: float
    calmar_ratio: float
    passes_s61: bool


# ---------------------------------------------------------------------------
# Engine run + metric helpers
# ---------------------------------------------------------------------------


def _candidate_config(exit_type: int = 3, **overrides) -> SwingConfig:
    """The frozen Amendment-1 candidate (00 §3/§4/§14) scoped to DISCOVERY.

    Only exit_type (and, for the diagnostic, target_positions/selector/selector_seed)
    is ever overridden — every other field is the locked default in SwingConfig.
    """
    return SwingConfig(
        exit_type=exit_type,
        date_from=DISCOVERY[0],
        date_to=DISCOVERY[1],
        **overrides,
    )


def _run(
    cfg: SwingConfig,
    *,
    prices: pd.DataFrame,
    regime: RegimeScore,
    signal_store,
    cost_level: str,
    whole_shares: bool,
) -> engine.SwingEngineResult:
    return engine.run(
        prices,
        cfg,
        regime=regime,
        signal_store=signal_store,
        cost_level=cost_level,
        whole_shares=whole_shares,
    )


def _equity_series(result: engine.SwingEngineResult) -> pd.Series:
    return pd.Series(
        [s.equity for s in result.snapshots],
        index=pd.DatetimeIndex([pd.Timestamp(s.date) for s in result.snapshots]),
    )


def _avg_hold(m: metrics.BacktestMetrics) -> float:
    """Mean realized hold (calendar days) over CLOSED positions only."""
    holds = [
        s.hold_days
        for s in m.per_name_stats
        if s.is_closed and s.hold_days == s.hold_days
    ]
    return float(np.mean(holds)) if holds else float("nan")


def _s61_ratio(
    result_pess: engine.SwingEngineResult,
    tri_nifty50: pd.Series,
    starting_capital: float,
) -> tuple[float, float, float]:
    """§6.1: (C_strat, C_nifty50, ratio) at pessimistic cost vs Nifty 50 TRI."""
    trading_cal = [pd.Timestamp(s.date) for s in result_pess.snapshots]
    bench = benchmark.align_benchmark(
        tri_nifty50, DISCOVERY[0], trading_cal, starting_capital
    )
    bm = metrics.compute_benchmark_metrics(_equity_series(result_pess), bench)
    return bm.strategy_calmar, bm.benchmark_calmar, bm.calmar_ratio


# ---------------------------------------------------------------------------
# Grid screen
# ---------------------------------------------------------------------------


def _screen_grid(
    prices: pd.DataFrame,
    regime: RegimeScore,
    signal_store,
    tri_nifty50: pd.Series,
    ledger: ConfigLedger,
) -> tuple[list[ScreenRow], engine.SwingEngineResult]:
    rows: list[ScreenRow] = []
    candidate_base: engine.SwingEngineResult | None = None

    for i, gc in enumerate(_GRID, 1):
        log.info("[%d/%d] %s (%s)...", i, len(_GRID), gc.name, gc.role)
        cfg = _candidate_config(exit_type=gc.exit_type)
        payload = {"config": gc.name, "exit_type": gc.exit_type, "target_positions": 15}

        ledger.add({**payload, "cost_level": "base"}, stage="V4.1_base")
        res_base = _run(
            cfg,
            prices=prices,
            regime=regime,
            signal_store=signal_store,
            cost_level="base",
            whole_shares=True,
        )
        m = metrics.compute_metrics(res_base)
        if gc.exit_type == 3:
            candidate_base = res_base

        ledger.add({**payload, "cost_level": "pessimistic"}, stage="V4.1_pessimistic")
        res_pess = _run(
            cfg,
            prices=prices,
            regime=regime,
            signal_store=signal_store,
            cost_level="pessimistic",
            whole_shares=True,
        )
        c_strat, c_n50, ratio = _s61_ratio(res_pess, tri_nifty50, cfg.starting_capital)

        rows.append(
            ScreenRow(
                name=gc.name,
                role=gc.role,
                base_calmar=m.calmar,
                base_max_dd=m.max_drawdown,
                base_sharpe=m.sharpe,
                turnover_pct=m.annualized_turnover * 100,
                win_rate=m.hit_rate,
                avg_hold_days=_avg_hold(m),
                n_fills=m.n_fills,
                c_strat_pessimistic=c_strat,
                c_nifty50=c_n50,
                calmar_ratio=ratio,
                passes_s61=ratio >= 1.0,
            )
        )
        log.info(
            "    base calmar=%.3f maxdd=%.1f%% turn=%.0f%% win=%.0f%% hold=%.0fd "
            "| pess C_strat=%.3f C_n50=%.3f ratio=%.2f %s",
            m.calmar,
            m.max_drawdown * 100,
            m.annualized_turnover * 100,
            (m.hit_rate * 100) if m.hit_rate == m.hit_rate else float("nan"),
            rows[-1].avg_hold_days,
            c_strat,
            c_n50,
            ratio,
            "PASS" if ratio >= 1.0 else "FAIL",
        )

    assert candidate_base is not None  # T3 is always in the grid
    return rows, candidate_base


# ---------------------------------------------------------------------------
# Selection-quality diagnostic (00 §6 — non-gating, adds 0 to K)
# ---------------------------------------------------------------------------


@dataclass
class DiagnosticResult:
    b_liquid_calmar: float
    b_random_median: float
    b_random_p5: float
    b_random_calmars: list[float]
    b_all_calmar: float
    read: str  # "neutral" | "favorable" | "edge-discarding"


def _diagnostic_read(b_liquid: float, b_random_median: float, b_all: float) -> str:
    """The pre-committed §6 read (00 §6 — decided before any number; ≥85% reuses the
    §6.3 plateau tolerance, no new magic number):

      favorable       B_liquid ≥ B_random median.
      neutral         B_liquid ≥ 85% of B_random median (but below it).
      edge-discarding B_liquid < 85% of B_random median AND materially below B_all
                      (BOTH required — below-85% alone but not below B_all is NOT it).
    """
    if b_liquid >= b_random_median:
        return "favorable"
    if b_liquid >= _DIAG_TOL * b_random_median:
        return "neutral"
    if b_liquid < b_all:
        return "edge-discarding"
    return "neutral"


def _run_diagnostic(
    prices: pd.DataFrame,
    regime: RegimeScore,
    signal_store,
    candidate_base: engine.SwingEngineResult,
) -> DiagnosticResult:
    # B_liquid = the candidate (T3 base run) — reuse, no re-run.
    b_liquid = metrics.compute_metrics(candidate_base).calmar

    # B_random = random 15-of-oversubscribed × seeds (base cost, whole-share — matches
    # B_liquid; only the SELECTOR differs, 00 §6).
    random_calmars: list[float] = []
    for seed in range(_N_RANDOM_SEEDS):
        cfg = _candidate_config(exit_type=3, selector="random", selector_seed=seed)
        res = _run(
            cfg,
            prices=prices,
            regime=regime,
            signal_store=signal_store,
            cost_level="base",
            whole_shares=True,
        )
        random_calmars.append(metrics.compute_metrics(res).calmar)
        log.info("    B_random seed=%d calmar=%.3f", seed, random_calmars[-1])
    b_random_median = float(np.nanmedian(random_calmars))
    b_random_p5 = float(np.nanpercentile(random_calmars, 5))

    # B_all = no cap (slot cap ≫ footprint), capital-blind, whole_shares OFF (00 §6).
    cfg_all = _candidate_config(exit_type=3, target_positions=_B_ALL_CAP)
    res_all = _run(
        cfg_all,
        prices=prices,
        regime=regime,
        signal_store=signal_store,
        cost_level="base",
        whole_shares=False,
    )
    b_all = metrics.compute_metrics(res_all).calmar
    log.info("    B_all (no cap) calmar=%.3f", b_all)

    read = _diagnostic_read(b_liquid, b_random_median, b_all)

    return DiagnosticResult(
        b_liquid_calmar=b_liquid,
        b_random_median=b_random_median,
        b_random_p5=b_random_p5,
        b_random_calmars=random_calmars,
        b_all_calmar=b_all,
        read=read,
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(
    rows: list[ScreenRow], diag: DiagnosticResult, ledger: ConfigLedger
) -> None:
    print()
    print("=" * 104)
    print(
        "  V4.1 Stage 1 — exit-choice §6.1 cost screen  (DISCOVERY 2018-02-06 → 2023-06-30)"
    )
    print(
        "  Frozen: entry 4-cond, 5-factor regime, stable U=200, target_positions=15, "
        "₹3.5L, whole-share"
    )
    print("=" * 104)
    print(
        f"  {'Cfg':>3} | {'Calmar':>7} | {'MaxDD':>6} | {'Sharpe':>6} | {'Turn%':>6} | "
        f"{'Win%':>5} | {'Hold':>5} | {'Fills':>5} | {'C_strat(P)':>10} | {'C_n50':>6} | "
        f"{'Ratio':>6} | §6.1"
    )
    print("  " + "─" * 100)
    for r in rows:
        win = f"{r.win_rate * 100:.0f}" if r.win_rate == r.win_rate else "n/a"
        hold = f"{r.avg_hold_days:.0f}" if r.avg_hold_days == r.avg_hold_days else "n/a"
        print(
            f"  {r.name:>3} | {r.base_calmar:>7.3f} | {r.base_max_dd:>5.1%} | "
            f"{r.base_sharpe:>6.2f} | {r.turnover_pct:>6.0f} | {win:>5} | {hold:>5} | "
            f"{r.n_fills:>5} | {r.c_strat_pessimistic:>10.3f} | {r.c_nifty50:>6.3f} | "
            f"{r.calmar_ratio:>6.2f} | {'PASS' if r.passes_s61 else 'FAIL'}"
        )
    print("  (roles: " + "; ".join(f"{r.name}={r.role}" for r in rows) + ")")

    print()
    print("-" * 104)
    print("  §6 selection-quality diagnostic (NON-GATING, adds 0 to K — 00 §6)")
    print("-" * 104)
    print(
        f"    B_liquid (candidate, top-15 adv_20) base Calmar : {diag.b_liquid_calmar:.3f}"
    )
    print(
        f"    B_random (random 15, N={_N_RANDOM_SEEDS} seeds)      "
        f": median {diag.b_random_median:.3f}  p5 {diag.b_random_p5:.3f}"
    )
    print(
        f"    B_all    (no cap, capital-blind)                 : {diag.b_all_calmar:.3f}"
    )
    ratio_vs_rand = (
        diag.b_liquid_calmar / diag.b_random_median
        if diag.b_random_median not in (0.0, float("nan"))
        else float("nan")
    )
    print(
        f"    B_liquid / B_random-median = {ratio_vs_rand:.2f}  "
        f"(threshold {_DIAG_TOL:g}) → READ: {diag.read.upper()}"
    )
    if diag.read == "edge-discarding":
        print(
            "    ⇒ authorizes a SEPARATE future amendment (return-informed selector, own K);"
            " NOT a swap this run (00 §6)."
        )
    else:
        print("    ⇒ keep the engine as-is; the cap is just a cap (00 §6).")

    survivors = [r for r in rows if r.passes_s61]
    print()
    print("=" * 104)
    print(
        f"  §6.1 survivors (pessimistic Calmar ratio ≥ 1.0): {len(survivors)}/{len(rows)}"
    )
    if survivors:
        for r in survivors:
            print(
                f"    → {r.name} ({r.role}) base Calmar {r.base_calmar:.3f}, "
                f"ratio {r.calmar_ratio:.2f} — carries to V4.2 battery"
            )
        print("  V4.2 (full §6 battery) runs next on the §6.1-clearing set.")
    else:
        print(
            "    → NULL — no config clears §6.1. Per 00 §6 pre-accepted null: the v4 swing\n"
            "      strategy is a RESEARCH NOTE; FINAL_OOS is NOT touched; no grid level added,\n"
            "      no threshold loosened. (Exit-choice rule 00 §6: a comparator beating the\n"
            "      candidate would be a reported finding, not a silent swap — moot here if all fail.)"
        )
    print(f"  v4 ConfigLedger K (this run): {ledger.n_trials}  (diagnostic added 0)")
    print("  FINAL_OOS untouched.")
    print("=" * 104)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Silence the per-day MTM carry-forward chatter from the reused v2 Portfolio.
    for noisy in (
        "app.backtest_v2.portfolio",
        "app.backtest_v2",
        "app.swing_v4.engine",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    print("v4 / 00 V4.1 — Stage 1 exit-choice §6.1 cost screen on DISCOVERY")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    print("  Grid: T3 (candidate, ATR 3×) | T1 (MACD cross) | T2 (EMA50)")
    print()

    print(
        "Loading prices_adjusted (offline cache, full history for warmup)...",
        flush=True,
    )
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(
        f"  rows={len(prices):,} ISINs={prices['isin'].nunique():,} "
        f"range={prices['date'].min().date()} → {prices['date'].max().date()}",
        flush=True,
    )

    print("Loading Nifty 50 price index + market_internals (regime)...", flush=True)
    px = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    mi = store.read_market_internals()
    if mi.empty:
        print("FAIL: market_internals empty.", file=sys.stderr)
        return 2

    print("Loading Nifty 50 TRI (§6.1 benchmark)...", flush=True)
    tri_nifty50 = benchmark.load_tri(
        benchmark.TRI_NIFTY_50, _BENCH_FETCH_START, _BENCH_FETCH_END
    )

    # Indicators are frozen across the whole grid (00 §3.2) ⇒ precompute ONCE and reuse.
    print(
        "Precomputing swing signals on full history (shared across grid)...", flush=True
    )
    ref_cfg = _candidate_config(exit_type=3)
    signal_store = precompute_swing_signals(prices, ref_cfg)
    regime = RegimeScore(px, mi, ref_cfg)

    ledger = ConfigLedger()
    print(
        "\nScreening the §5 grid (base + pessimistic, whole-share, ₹3.5L)...",
        flush=True,
    )
    rows, candidate_base = _screen_grid(
        prices, regime, signal_store, tri_nifty50, ledger
    )

    print(
        f"\nRunning the §6 selection-quality diagnostic "
        f"(B_liquid / B_random×{_N_RANDOM_SEEDS} / B_all)...",
        flush=True,
    )
    diag = _run_diagnostic(prices, regime, signal_store, candidate_base)

    _print_report(rows, diag, ledger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
