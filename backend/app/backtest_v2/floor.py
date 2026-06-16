"""
floor.py — Spec 04 T1: THE FLOOR (the GO/NO-GO gate).

This is the *one* pre-committed config the whole validation layer is built to
judge (`04_VALIDATION_FLOOR.md` §2).  It is NOT a search and NOT a tuning loop:
exactly one `MomentumConfig` (every field at its spec-02 default — see the T0
"Floor → MomentumConfig field map") is run on the FULL usable window, measured
honestly at three cost levels against three real TRI benchmarks, and scored
against the T0 decision predicates.

Two load-bearing honesty requirements (Rule 12 — fail loud):

  1. **Real regime signal.**  The regime overlay reads the *real Nifty 50 price
     index* 200-DMA (`benchmark.load_price_index`), NOT `run_real`'s synthetic
     equal-weight placeholder.  A floor measured on a synthetic regime is not
     the spec's floor (04 §2 / the task file's "load-bearing integration fact").

  2. **Real benchmarks or nothing.**  All three TRIs (primary Momentum 30,
     secondary Midcap Momentum 50, floor Nifty 50) must load from the disk
     cache / network.  A cache miss with no network raises — we never soften a
     missing benchmark into a synthetic fallback, because the verdict is
     meaningless without the real Nifty200 Momentum 30 TRI.

The verdict is computed by `evaluate_decision` from the T0 predicates and
printed plainly.  GO → spec 04 proceeds to T2.  NO-GO → STOP and diagnose
data/costs; do not build T2–T5, do not tune.

Run:
    backend/venv/bin/python -m app.backtest_v2.floor
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, metrics, run_real
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.costs import CostLevel
from app.backtest_v2.signals import precompute_signals
from app.data.bhavcopy import store

# ---------------------------------------------------------------------------
# Frozen T0 constants (see 04_VALIDATION_FLOOR.md "Locked decisions (T0)").
# The floor runs the single pre-committed config over the FULL usable window;
# it spends no OOS budget, so it uses FLOOR_START..FLOOR_END, not DISCOVERY.
# ---------------------------------------------------------------------------

FLOOR_START = date(2018, 2, 6)  # first post-warmup decision date
FLOOR_END = date(2026, 6, 12)  # last date on disk (T0 probe)

# Benchmarks (and the regime price index) are fetched over this wider range so
# the regime 200-DMA has warmup before FLOOR_START and the cache key matches the
# already-warmed parquet files (T1 prep, 2026-06-16).
_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = FLOOR_END

_COST_LEVELS: list[CostLevel] = ["optimistic", "base", "pessimistic"]

# (label, TRI constant) in report order: primary first (it drives the verdict).
_TRI_BENCHMARKS: list[tuple[str, str]] = [
    ("Nifty200 Momentum 30 TRI  [PRIMARY]", benchmark.TRI_MOMENTUM_30),
    ("Nifty Midcap150 Momentum 50 TRI  [secondary]", benchmark.TRI_MIDCAP_MOMENTUM_50),
    ("Nifty 50 TRI  [floor / sanity]", benchmark.TRI_NIFTY_50),
]

# T0 decision-rule thresholds (made numeric in 04 §"Decision-rule predicates").
_GO_FRACTION = 0.80  # GO iff C_strat >= 0.80 * C_primary


# ---------------------------------------------------------------------------
# Floor config + decision rule
# ---------------------------------------------------------------------------


def build_floor_config() -> MomentumConfig:
    """The spec 04 §2 floor: every field at its spec-02 default, full window.

    Per the T0 field map there is zero drift between the §2 prose and the
    `MomentumConfig` defaults, so the floor is just the default config pinned to
    the usable window.
    """
    return MomentumConfig(date_from=FLOOR_START, date_to=FLOOR_END)


@dataclass
class FloorVerdict:
    """Outcome of the T0 GO/NO-GO predicates at base cost level."""

    decision: str  # "GO" | "GO (marginal)" | "NO-GO"
    c_strat: float  # strategy Calmar at base cost over the floor window
    c_primary: float  # Nifty200 Momentum 30 TRI Calmar over the same window
    c_nifty50: float  # Nifty 50 TRI Calmar over the same window
    go_threshold: float  # 0.80 * c_primary
    rationale: str


def evaluate_decision(
    c_strat: float, c_primary: float, c_nifty50: float
) -> FloorVerdict:
    """Apply the T0 predicates.

    GO       : C_strat >= 0.80 * C_primary          (roughly tracks the primary)
    NO-GO    : C_strat <  C_nifty50                  (can't beat even Nifty 50)
    marginal : C_nifty50 <= C_strat < 0.80*C_primary (beats floor, trails primary)

    NO-GO is evaluated first: if the strategy can't clear the Nifty 50 floor the
    foundation is structural, regardless of how close it gets to the primary.
    """
    go_threshold = _GO_FRACTION * c_primary

    if c_strat < c_nifty50:
        decision = "NO-GO"
        rationale = (
            f"C_strat ({c_strat:.3f}) < C_nifty50 ({c_nifty50:.3f}): the floor "
            "config cannot beat even the plain Nifty 50 on risk-adjusted return "
            "after base costs. Per 04 §2 this is a structural failure (universe / "
            "cost model / data) — STOP, diagnose, do not tune, do not build T2–T5."
        )
    elif c_strat >= go_threshold:
        decision = "GO"
        rationale = (
            f"C_strat ({c_strat:.3f}) >= 0.80 * C_primary ({go_threshold:.3f}): "
            "the floor roughly tracks the Nifty200 Momentum 30 TRI on Calmar after "
            "base costs. Real foundation confirmed — proceed to T2."
        )
    else:
        decision = "GO (marginal)"
        rationale = (
            f"C_nifty50 ({c_nifty50:.3f}) <= C_strat ({c_strat:.3f}) < "
            f"0.80 * C_primary ({go_threshold:.3f}): beats the Nifty 50 floor but "
            "trails the primary. Marginal GO — proceed to T2 with heightened "
            "scrutiny; the primary-tracking gap is documented in the session log."
        )

    return FloorVerdict(
        decision=decision,
        c_strat=c_strat,
        c_primary=c_primary,
        c_nifty50=c_nifty50,
        go_threshold=go_threshold,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Benchmark loading (real TRIs — fail loud on miss)
# ---------------------------------------------------------------------------


def _load_aligned_benchmarks(
    config: MomentumConfig, trading_calendar: list[pd.Timestamp]
) -> dict[str, pd.Series]:
    """Load + align all three TRIs to the strategy calendar.

    Raises (does not return None) on any miss: the floor verdict is meaningless
    without the real benchmarks (T1 done-criteria; Rule 12).
    """
    aligned: dict[str, pd.Series] = {}
    for label, tri_name in _TRI_BENCHMARKS:
        tri = benchmark.load_tri(tri_name, _BENCH_FETCH_START, _BENCH_FETCH_END)
        aligned[label] = benchmark.align_benchmark(
            tri, config.date_from, trading_calendar, config.starting_capital
        )
    return aligned


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _strat_equity_series(result: engine.EngineResult) -> pd.Series:
    return pd.Series(
        [s.equity for s in result.snapshots],
        index=pd.DatetimeIndex([pd.Timestamp(s.date) for s in result.snapshots]),
    )


def _print_floor_report(
    results: dict[CostLevel, engine.EngineResult],
    metric_blocks: dict[CostLevel, metrics.BacktestMetrics],
    aligned_benchmarks: dict[str, pd.Series],
) -> dict[CostLevel, dict[str, metrics.BenchmarkMetrics]]:
    """Render 3 cost levels × 3 benchmarks. Returns the benchmark-metric grid."""
    grid: dict[CostLevel, dict[str, metrics.BenchmarkMetrics]] = {}

    print()
    print("=" * 72)
    print("  SPEC 04 T1 — FLOOR REPORT  (3 cost levels × 3 TRI benchmarks)")
    print(
        f"  Window: {FLOOR_START} → {FLOOR_END}   regime: real Nifty 50 price 200-DMA"
    )
    print("=" * 72)

    for level in _COST_LEVELS:
        r = results[level]
        m = metric_blocks[level]
        strat_equity = _strat_equity_series(r)
        grid[level] = {}

        print()
        print("─" * 72)
        print(f"  COST LEVEL: {level.upper()}")
        print("─" * 72)
        print(metrics.summary(m))
        print()

        for label, bench_series in aligned_benchmarks.items():
            bm = metrics.compute_benchmark_metrics(strat_equity, bench_series)
            grid[level][label] = bm
            print(f"  vs {label}")
            print(
                f"      Strat Calmar {bm.strategy_calmar:6.2f}   "
                f"Bench Calmar {bm.benchmark_calmar:6.2f}   "
                f"Calmar Ratio {bm.calmar_ratio:5.2f}"
                f"{'  ✓>1' if bm.calmar_ratio > 1 else '  ✗≤1'}"
            )
            print(
                f"      Strat MaxDD  {bm.strategy_max_dd:6.2%}   "
                f"Bench MaxDD  {bm.benchmark_max_dd:6.2%}   "
                f"Max-DD Ratio {bm.max_dd_ratio:5.2f}"
                f"{'  ✓≤0.70' if bm.max_dd_ratio <= 0.70 else '  ✗>0.70'}"
            )
            print(
                f"      Excess CAGR {bm.excess_cagr:+7.2%}   "
                f"IR {bm.information_ratio:5.2f}   "
                f"beta {bm.beta:4.2f}   up/dn cap {bm.up_capture:.2f}/{bm.down_capture:.2f}"
            )
            print()

    # Headline Calmar-ratio matrix.
    print("=" * 72)
    print("  HEADLINE — Calmar ratio (strategy / benchmark) by cost × benchmark")
    print("=" * 72)
    labels = [lbl for lbl, _ in _TRI_BENCHMARKS]
    short = ["Mom30", "Mid50", "Nifty50"]
    print(f"  {'Cost level':<14}" + "".join(f"{s:>12}" for s in short))
    print(f"  {'─' * 14}" + "".join(f"{'─' * 10:>12}" for _ in short))
    for level in _COST_LEVELS:
        cells = "".join(f"{grid[level][lbl].calmar_ratio:>12.2f}" for lbl in labels)
        print(f"  {level.upper():<14}{cells}")
    print()
    return grid


# ---------------------------------------------------------------------------
# Invariant pre-flight (reuse run_real's 02 §10 checks)
# ---------------------------------------------------------------------------


def _run_invariants(
    prices: pd.DataFrame,
    config: MomentumConfig,
    index_prices: pd.Series,
    base_result: engine.EngineResult,
) -> list[str]:
    """Reuse run_real's cash-conservation / determinism / no-lookahead checks."""
    baseline_equity = run_real._equity_array(base_result)
    run_real._SNAPSHOT_DATES_HOLDER.clear()
    run_real._SNAPSHOT_DATES_HOLDER.extend(base_result.snapshots)

    errs: list[str] = []
    cc = run_real.check_cash_conservation(base_result)
    print(f"  [{'PASS' if not cc else 'FAIL'}] cash conservation + cost accounting")
    errs += cc

    det = run_real.check_determinism(prices, config, index_prices, baseline_equity)
    print(f"  [{'PASS' if not det else 'FAIL'}] determinism (identical re-run)")
    errs += det

    cutoff = pd.Timestamp(FLOOR_END) - pd.DateOffset(years=2)
    la = run_real.check_no_lookahead(
        prices, config, index_prices, baseline_equity, cutoff
    )
    print(f"  [{'PASS' if not la else 'FAIL'}] no-lookahead (cutoff {cutoff.date()})")
    errs += la
    return errs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    config = build_floor_config()

    print("Spec 04 T1 — THE FLOOR")
    print(f"  config: {config}")
    print()

    print("Loading real spec-01 dataset (prices_adjusted) ...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print(
            "FAIL: prices_adjusted is empty — build the data layer first.",
            file=sys.stderr,
        )
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(
        f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}  "
        f"range={prices['date'].min().date()} → {prices['date'].max().date()}",
        flush=True,
    )

    # --- Real regime signal: Nifty 50 price index 200-DMA (NOT synthetic) ---
    print("Loading REAL Nifty 50 price index for regime overlay ...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(
            "FAIL: real Nifty 50 price index unavailable (cache miss + no network): "
            f"{exc}\nThe floor regime MUST be the real price index, not synthetic "
            "(04 §2). Refusing to run a meaningless floor (Rule 12).",
            file=sys.stderr,
        )
        return 2
    print(
        f"  regime index points={len(index_prices):,}  "
        f"level {index_prices.iloc[0]:.0f} → {index_prices.iloc[-1]:.0f}",
        flush=True,
    )

    print("Precomputing signals (per-ISIN indicators) ...", flush=True)
    signal_store = precompute_signals(prices, config)

    # --- Run all three cost levels (single config each) ---
    results: dict[CostLevel, engine.EngineResult] = {}
    metric_blocks: dict[CostLevel, metrics.BacktestMetrics] = {}
    for level in _COST_LEVELS:
        print(f"Running engine — cost level {level.upper()} ...", flush=True)
        r = engine.run(
            prices,
            config,
            index_prices=index_prices,
            cost_level=level,
            signal_store=signal_store,
        )
        results[level] = r
        metric_blocks[level] = metrics.compute_metrics(r)

    base_result = results["base"]
    print(
        f"  base run: snapshots={len(base_result.snapshots):,}  "
        f"fills={len(base_result.fills_log):,}  "
        f"rebalances={len(base_result.rebalance_dates_used)}",
        flush=True,
    )

    # --- Load real benchmarks (fail loud on any miss) ---
    print("Loading real TRI benchmarks (primary / secondary / floor) ...", flush=True)
    trading_calendar = [pd.Timestamp(s.date) for s in base_result.snapshots]
    try:
        aligned_benchmarks = _load_aligned_benchmarks(config, trading_calendar)
    except Exception as exc:
        print(
            "FAIL: a real TRI benchmark is unavailable (cache miss + no network): "
            f"{exc}\nThe floor verdict is meaningless without the real Nifty200 "
            "Momentum 30 TRI. Not falling back to synthetic (Rule 12).",
            file=sys.stderr,
        )
        return 2

    # --- Invariant pre-flight (02 §10) BEFORE judging the floor ---
    print()
    print("=== Real-data invariant checks (02 §10) ===", flush=True)
    inv_errs = _run_invariants(prices, config, index_prices, base_result)
    if inv_errs:
        print("\nFLOOR INVARIANT CHECK FAILED — verdict withheld:", file=sys.stderr)
        for e in inv_errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # --- Report: 3 cost levels × 3 benchmarks ---
    grid = _print_floor_report(results, metric_blocks, aligned_benchmarks)

    # --- Decision: T0 predicates at BASE cost level ---
    primary_label = _TRI_BENCHMARKS[0][0]
    nifty50_label = _TRI_BENCHMARKS[2][0]
    c_strat = metric_blocks["base"].calmar
    c_primary = grid["base"][primary_label].benchmark_calmar
    c_nifty50 = grid["base"][nifty50_label].benchmark_calmar
    verdict = evaluate_decision(c_strat, c_primary, c_nifty50)

    print("=" * 72)
    print(
        f"  GO / NO-GO VERDICT (04 §2, base cost level):   >>> {verdict.decision} <<<"
    )
    print("=" * 72)
    print(f"  C_strat   (strategy Calmar, base)        = {verdict.c_strat:.3f}")
    print(f"  C_primary (Nifty200 Momentum 30 TRI)     = {verdict.c_primary:.3f}")
    print(f"  C_nifty50 (Nifty 50 TRI, floor)          = {verdict.c_nifty50:.3f}")
    print(f"  GO threshold (0.80 × C_primary)          = {verdict.go_threshold:.3f}")
    print()
    print(f"  {verdict.rationale}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
