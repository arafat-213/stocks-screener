"""
tbe3_baseline.py — TBE3: Track-A baseline backtest on the Track-B window.

Produces the H3 comparison anchor: the accepted Track-A construction + price-factor
composite, run on TRACK_B_DISCOVERY (2020-01-31 → 2023-06-30), with its §6.4
subperiod Calmar profile.  Expected to FAIL passes_concentration_hard — that failure
is what value/quality (TBE4/TBE5) must fix.

Deliverables (written to this script's Session log in 04_TRACK_B_EXEC_TASKS.md):
  - Calmar, maxDD, turnover, Sharpe on TRACK_B_DISCOVERY at base cost
  - Benchmark-relative context (Nifty200 Momentum 30 TRI)
  - Per-subperiod Calmar + passes_concentration_hard verdict
  - ConfigLedger K after this task (= 1 main + 3 subperiod = 4 entries)
  - §6.4 spread recorded as the H3 anchor for TBE4/TBE5

Track-B subperiods (PRE-COMMITTED before running — do NOT move to make a check pass,
Rule 12).  Three distinct Indian equity market regimes within the Track-B window:
  1. "COVID crash + V-recovery"  2020-01-31 → 2021-03-31  (~14 months)
  2. "Post-COVID bull"           2021-04-01 → 2022-01-31  (~10 months)
  3. "Rate-hike correction"      2022-02-01 → 2023-06-30  (~17 months)

One run, no grid.  FINAL_OOS untouched.

Run:
    backend/venv/bin/python -m app.backtest_v2.tbe3_baseline
"""

from __future__ import annotations

import logging
import math
import sys
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.v3_config import (
    TRACK_A_BASELINE,
    TRACK_B_DISCOVERY,
    V3Config,
    passes_concentration_hard,
)
from app.backtest_v2.validation import ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# ---------------------------------------------------------------------------
# Track-B subperiods — PRE-COMMITTED (do not change after first run, Rule 12)
# Three distinct Indian equity market regimes within TRACK_B_DISCOVERY.
# ---------------------------------------------------------------------------
TRACK_B_SUBPERIODS: list[tuple[str, date, date]] = [
    # COVID crash (Feb-Mar 2020) and V-shaped recovery
    ("COVID crash + V-recovery", date(2020, 1, 31), date(2021, 3, 31)),
    # Post-COVID bull market run into the Nifty50 peak
    ("Post-COVID bull", date(2021, 4, 1), date(2022, 1, 31)),
    # RBI hikes + Russia-Ukraine + mid/smallcap correction and partial recovery
    ("Rate-hike correction", date(2022, 2, 1), date(2023, 6, 30)),
]


# ---------------------------------------------------------------------------
# Config plumbing
# ---------------------------------------------------------------------------


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


def _run(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    eng_cfg: MomentumConfig,
    signal_store: V3SignalStore,
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
    print("  v3 / TBE3 — Track-A baseline on TRACK_B_DISCOVERY")
    print(f"  Window:    {tb_start} → {tb_end}")
    print(f"  Config:    TRACK_A_BASELINE  {TRACK_A_BASELINE.active_factors}")
    print(
        f"             cadence={TRACK_A_BASELINE.rebalance_cadence}  "
        f"M={TRACK_A_BASELINE.sell_rank_buffer}  "
        f"smoothing={TRACK_A_BASELINE.rank_smoothing_months}  N=20"
    )
    print("  Purpose:   H3 anchor — expected to FAIL passes_concentration_hard")
    print("=" * 78)

    print("\nLoading prices_adjusted (offline cache)...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}", flush=True)

    print("Loading regime price index (cached)...", flush=True)
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

    # Build V3SignalStore once on the full prices (subperiod runs reuse it —
    # the engine filters by date_from/date_to in MomentumConfig).
    baseline_cfg = V3Config(
        active_factors=list(TRACK_A_BASELINE.active_factors),
        rebalance_cadence=TRACK_A_BASELINE.rebalance_cadence,
        sell_rank_buffer=TRACK_A_BASELINE.sell_rank_buffer,
        rank_smoothing_months=TRACK_A_BASELINE.rank_smoothing_months,
        target_positions=TRACK_A_BASELINE.target_positions,
        date_from=tb_start,
        date_to=tb_end,
    )

    print("Precomputing v2 indicator cache (shared gate)...", flush=True)
    ind = precompute_signals(prices, _engine_cfg(baseline_cfg, tb_start, tb_end))._data

    print("Building composite signal store...", flush=True)
    composite = factors.composite_rank(prices, baseline_cfg)
    signal_store = V3SignalStore(ind, composite, baseline_cfg)

    ledger = ConfigLedger()
    eng_cfg_full = _engine_cfg(baseline_cfg, tb_start, tb_end)

    # -----------------------------------------------------------------------
    # Main run — TRACK_B_DISCOVERY, base cost
    # -----------------------------------------------------------------------
    print("\nMain run (base cost, TRACK_B_DISCOVERY)...", flush=True)
    ledger.add(
        {
            "task": "TBE3",
            "active_factors": list(TRACK_A_BASELINE.active_factors),
            "cadence": TRACK_A_BASELINE.rebalance_cadence,
            "M": TRACK_A_BASELINE.sell_rank_buffer,
            "smoothing": TRACK_A_BASELINE.rank_smoothing_months,
            "window": f"{tb_start}→{tb_end}",
            "cost_level": "base",
        },
        check="TBE3_baseline_full",
    )
    main_res, main_m = _run(prices, index_prices, eng_cfg_full, signal_store)

    print(
        f"  calmar={main_m.calmar:.3f}  cagr={main_m.cagr * 100:.1f}%"
        f"  maxdd={main_m.max_drawdown:.2%}  sharpe={main_m.sharpe:.3f}"
        f"  turnover={main_m.annualized_turnover * 100:.0f}%"
        f"  fills={main_m.n_fills}",
        flush=True,
    )

    # Benchmark-relative context
    trading_cal = [pd.Timestamp(s.date) for s in main_res.snapshots]
    bm_nm30 = None
    if tri_nm30 is not None:
        try:
            bench_aligned = benchmark.align_benchmark(
                tri_nm30, tb_start, trading_cal, baseline_cfg.starting_capital
            )
            bm_nm30 = metrics.compute_benchmark_metrics(
                _equity_series(main_res), bench_aligned
            )
            print(
                f"  vs NM30 TRI: c_strat={bm_nm30.strategy_calmar:.3f}"
                f"  c_bench={bm_nm30.benchmark_calmar:.3f}"
                f"  calmar_ratio={bm_nm30.calmar_ratio:.2f}"
                f"  excess_cagr={bm_nm30.excess_cagr * 100:+.1f}%",
                flush=True,
            )
        except Exception as exc:
            print(f"  WARNING: benchmark alignment failed: {exc}", file=sys.stderr)

    # -----------------------------------------------------------------------
    # Subperiod runs — evaluate passes_concentration_hard (the §6.4 stick)
    # -----------------------------------------------------------------------
    print("\nSubperiod analysis (§6.4 anchor)...", flush=True)
    print("  Pre-committed subperiods (LOCKED before running, Rule 12):")
    for label, s, e in TRACK_B_SUBPERIODS:
        print(f"    '{label}': {s} → {e}")

    subresults: list[tuple[str, metrics.BacktestMetrics]] = []
    for label, s_start, s_end in TRACK_B_SUBPERIODS:
        ledger.add(
            {
                "task": "TBE3",
                "subperiod": label,
                "start": str(s_start),
                "end": str(s_end),
                "cost_level": "base",
            },
            check="TBE3_baseline_subperiod",
        )
        eng_sub = _engine_cfg(baseline_cfg, s_start, s_end)
        _, sub_m = _run(prices, index_prices, eng_sub, signal_store)
        subresults.append((label, sub_m))
        print(
            f"  '{label}': calmar={sub_m.calmar:.3f}"
            f"  cagr={sub_m.cagr * 100:.1f}%"
            f"  maxdd={sub_m.max_drawdown:.2%}",
            flush=True,
        )

    calmars_raw = [m.calmar for _, m in subresults]
    calmars_finite = [c for c in calmars_raw if not math.isnan(c)]
    n_positive = sum(1 for c in calmars_finite if c > 0)
    positivity_ok = n_positive >= 2
    concentration_ok = passes_concentration_hard(calmars_finite)
    sec64_passes = positivity_ok and concentration_ok

    # §6.4 spread = max(positive Calmars) / mean(other positive Calmars)
    # (the same ratio that passes_concentration_hard evaluates)
    positives = sorted([c for c in calmars_finite if c > 0], reverse=True)
    if len(positives) >= 2:
        best = positives[0]
        others_mean = sum(positives[1:]) / len(positives[1:])
        spread_ratio = best / others_mean if others_mean > 0 else float("inf")
    else:
        best = positives[0] if positives else float("nan")
        others_mean = float("nan")
        spread_ratio = float("nan")

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    print()
    print("=" * 78)
    print("  TBE3 RESULTS — TRACK_B_DISCOVERY baseline (H3 anchor)")
    print("=" * 78)

    print(f"\n  Window:    {tb_start} → {tb_end}")
    print(f"  Config:    TRACK_A_BASELINE  factors={TRACK_A_BASELINE.active_factors}")
    print(
        f"             cadence={TRACK_A_BASELINE.rebalance_cadence}  "
        f"M={TRACK_A_BASELINE.sell_rank_buffer}  smoothing={TRACK_A_BASELINE.rank_smoothing_months}"
    )

    print("\n  Full-window (base cost):")
    print(f"    Calmar:           {main_m.calmar:.3f}")
    print(f"    CAGR:             {main_m.cagr * 100:.1f}%")
    print(f"    Max DD:           {main_m.max_drawdown:.2%}")
    print(f"    Sharpe:           {main_m.sharpe:.3f}")
    print(f"    Turnover:         {main_m.annualized_turnover * 100:.0f}%")
    print(f"    Fills:            {main_m.n_fills}")
    if bm_nm30 is not None:
        print("\n  vs Nifty200 Momentum 30 TRI:")
        print(f"    Strategy Calmar:  {bm_nm30.strategy_calmar:.3f}")
        print(f"    Benchmark Calmar: {bm_nm30.benchmark_calmar:.3f}")
        print(f"    Calmar ratio:     {bm_nm30.calmar_ratio:.2f}")
        print(f"    Excess CAGR:      {bm_nm30.excess_cagr * 100:+.1f}%")
        print(f"    Max-DD ratio:     {bm_nm30.max_dd_ratio:.2f}")

    print("\n  §6.4 Subperiod Calmars:")
    for label, sub_m in subresults:
        marker = "  ✓" if sub_m.calmar > 0 else "  ✗"
        print(
            f"    {marker} '{label}': calmar={sub_m.calmar:.3f}"
            f"  cagr={sub_m.cagr * 100:.1f}%"
            f"  maxdd={sub_m.max_drawdown:.2%}"
        )

    print("\n  §6.4 Concentration analysis:")
    print(f"    n_positive subperiods:      {n_positive}/3  (need >= 2)")
    print(f"    positivity_ok:              {positivity_ok}")
    print(f"    concentration_ok:           {concentration_ok}")
    print(f"    best positive Calmar:       {best:.3f}")
    print(f"    mean of other positives:    {others_mean:.3f}")
    print(f"    spread ratio (best/mean):   {spread_ratio:.2f}x  (threshold: 5.0x)")
    print(f"    passes_concentration_hard:  {sec64_passes}")
    result_str = "PASS" if sec64_passes else "FAIL"
    print(f"\n  §6.4 overall:  >>> {result_str} <<<")

    if not concentration_ok:
        print(
            f"\n  NOTE: §6.4 FAILS concentration — spread ratio {spread_ratio:.1f}x > 5.0x."
        )
        print("  This is the EXPECTED outcome for the Track-A baseline on this window.")
        print(
            "  The spread ratio is the H3 anchor: TBE4/TBE5 must bring it below 5.0x."
        )

    print(f"\n  ConfigLedger K after TBE3: {ledger.n_trials}")
    print("  (1 main run + 3 subperiod runs = 4 entries)")
    print("  NOTE: Track-A T1-T6 contributed K=10+6=16 entries before Track-B.")
    print("  Cumulative K for deflated Sharpe in TBE7: 16 + 4 + TBE4/5/6 trials.")

    print("\n  FINAL_OOS: UNTOUCHED (TBE8 only, on TBE7 PASS + H3 confirmed)")
    print("=" * 78)

    return 0


if __name__ == "__main__":
    sys.exit(main())
