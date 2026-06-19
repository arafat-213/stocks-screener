"""
md1_cost_screen.py — v3 / 05 MD1: Stage 1 cost screen on the 12-point prereg grid.

Pre-registration: specs/v3/05_MOMENTUM_DEPLOY_PREREG.md §4/MD1.

Grid (all 12 exhaustive, no interpolation):
    sell_rank_buffer M  ∈ {70, 130, 200}
    rank_smoothing      ∈ {0, 3} months
    rebalance_cadence   ∈ {monthly, quarterly}

For each config:
  - Run at base cost → record turnover, Calmar, maxDD.
  - Run at pessimistic cost → compute §6.1 ratio = C_strat / C_nifty50.
  - Log both runs to ConfigLedger.

Output: 12-row table + the §6.1-clearing set (ratio >= 1.0).
DISCOVERY only — FINAL_OOS stays pristine.

Run:
    backend/venv/bin/python -m app.backtest_v2.md1_cost_screen
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date
from itertools import product

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

# §4 grid — fully enumerated per prereg, no additions allowed after seeing results.
_M_GRID: list[int] = [70, 130, 200]
_SMOOTHING_GRID: list[int] = [0, 3]
_CADENCE_GRID: list[str] = ["monthly", "quarterly"]


# ---------------------------------------------------------------------------
# Result row
# ---------------------------------------------------------------------------


@dataclass
class ScreenRow:
    m: int
    smoothing: int
    cadence: str
    base_calmar: float
    base_max_dd: float
    turnover_pct: float
    c_strat_pessimistic: float
    c_nifty50: float
    calmar_ratio: float
    passes_s61: bool

    @property
    def label(self) -> str:
        return f"M={self.m} sm={self.smoothing} {self.cadence[:1].upper()}"


# ---------------------------------------------------------------------------
# Config plumbing (mirrors t6_robustness / t4_turnover patterns)
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


# ---------------------------------------------------------------------------
# Screen one config
# ---------------------------------------------------------------------------


def _screen_config(
    m: int,
    smoothing: int,
    cadence: str,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    tri_nifty50: pd.Series,
    ind,
    composite_cache: dict[int, pd.DataFrame],
    ledger: ConfigLedger,
) -> ScreenRow:
    v3cfg = V3Config(
        active_factors=list(TRACK_A_BASELINE.active_factors),
        rebalance_cadence=cadence,
        sell_rank_buffer=m,
        rank_smoothing_months=smoothing,
        target_positions=TRACK_A_BASELINE.target_positions,
        date_from=DISCOVERY[0],
        date_to=DISCOVERY[1],
    )
    eng = _engine_cfg(v3cfg, *DISCOVERY)

    if smoothing not in composite_cache:
        composite_cache[smoothing] = factors.composite_rank(prices, v3cfg)
    ss = V3SignalStore(ind, composite_cache[smoothing], v3cfg)

    # Base run
    ledger.add(
        {"M": m, "smoothing": smoothing, "cadence": cadence, "cost_level": "base"},
        stage="MD1_base",
    )
    res_base = engine.run(
        prices, eng, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    m_base = metrics.compute_metrics(res_base)

    # Pessimistic run (§6.1 screen)
    ledger.add(
        {
            "M": m,
            "smoothing": smoothing,
            "cadence": cadence,
            "cost_level": "pessimistic",
        },
        stage="MD1_pessimistic",
    )
    res_pess = engine.run(
        prices,
        eng,
        index_prices=index_prices,
        cost_level="pessimistic",
        signal_store=ss,
    )
    trading_cal = [pd.Timestamp(s.date) for s in res_pess.snapshots]
    bench_aligned = benchmark.align_benchmark(
        tri_nifty50, eng.date_from, trading_cal, eng.starting_capital
    )
    bm = metrics.compute_benchmark_metrics(_equity_series(res_pess), bench_aligned)

    log.info(
        "  M=%3d sm=%d %-10s | base calmar=%.3f turn=%4.0f%% | "
        "pess C_strat=%.3f C_n50=%.3f ratio=%.2f %s",
        m,
        smoothing,
        cadence,
        m_base.calmar,
        m_base.annualized_turnover * 100,
        bm.strategy_calmar,
        bm.benchmark_calmar,
        bm.calmar_ratio,
        "PASS" if bm.calmar_ratio >= 1.0 else "FAIL",
    )

    return ScreenRow(
        m=m,
        smoothing=smoothing,
        cadence=cadence,
        base_calmar=m_base.calmar,
        base_max_dd=m_base.max_drawdown,
        turnover_pct=m_base.annualized_turnover * 100,
        c_strat_pessimistic=bm.strategy_calmar,
        c_nifty50=bm.benchmark_calmar,
        calmar_ratio=bm.calmar_ratio,
        passes_s61=bm.calmar_ratio >= 1.0,
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(rows: list[ScreenRow]) -> None:
    print()
    print("=" * 90)
    print(
        "  MD1 Stage 1 — 12-config §6.1 cost screen  (DISCOVERY 2018-02-06 → 2023-06-30)"
    )
    print("  Held constant: 5-factor set, N=20, regime ON, liquidity floor 5cr")
    print("=" * 90)
    print(
        f"  {'Config':>22} | {'Base Calmar':>11} | {'MaxDD':>7} | {'Turnover%':>10} | "
        f"{'C_strat(P)':>10} | {'C_nifty50':>9} | {'Ratio':>6} | §6.1"
    )
    print(
        f"  {'─' * 22} | {'─' * 11} | {'─' * 7} | {'─' * 10} | {'─' * 10} | {'─' * 9} | {'─' * 6} | {'─' * 5}"
    )

    for r in rows:
        cfg_label = f"M={r.m:3d} sm={r.smoothing} {r.cadence}"
        mark = "PASS" if r.passes_s61 else "FAIL"
        print(
            f"  {cfg_label:>22} | {r.base_calmar:>11.3f} | {r.base_max_dd:>7.1%} | "
            f"{r.turnover_pct:>10.0f} | {r.c_strat_pessimistic:>10.3f} | "
            f"{r.c_nifty50:>9.3f} | {r.calmar_ratio:>6.2f} | {mark}"
        )

    survivors = [r for r in rows if r.passes_s61]
    print()
    print("=" * 90)
    print(f"  §6.1 survivors (ratio >= 1.0): {len(survivors)}/{len(rows)} configs")
    if survivors:
        for r in survivors:
            print(
                f"    → M={r.m} sm={r.smoothing} {r.cadence} "
                f"(base Calmar {r.base_calmar:.3f}, ratio {r.calmar_ratio:.2f})"
            )
    else:
        print("    → NULL — no config clears §6.1. Null outcome per prereg §5.")
    print("=" * 90)


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

    print("v3 / 05 MD1 — Stage 1: 12-config §6.1 cost screen on DISCOVERY")
    print("  Grid: M∈{70,130,200} × smoothing∈{0,3} × cadence∈{monthly,quarterly}")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
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

    print("Loading Nifty 50 price index (regime, offline cache)...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(f"FAIL: regime index unavailable: {exc}", file=sys.stderr)
        return 2

    print("Loading Nifty 50 TRI (§6.1 benchmark, offline cache)...", flush=True)
    try:
        tri_nifty50 = benchmark.load_tri(
            benchmark.TRI_NIFTY_50, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
    except Exception as exc:
        print(f"FAIL: Nifty50 TRI unavailable: {exc}", file=sys.stderr)
        return 2

    # Shared v2 indicator cache (gate inputs don't change across grid points).
    ref_cfg = _engine_cfg(TRACK_A_BASELINE, *DISCOVERY)
    print("Precomputing v2 indicator cache on DISCOVERY (shared)...", flush=True)
    gate_store = precompute_signals(prices, ref_cfg)
    ind = gate_store._data

    ledger = ConfigLedger()
    composite_cache: dict[int, pd.DataFrame] = {}

    rows: list[ScreenRow] = []
    total = len(_M_GRID) * len(_SMOOTHING_GRID) * len(_CADENCE_GRID)
    n = 0
    for m, smoothing, cadence in product(_M_GRID, _SMOOTHING_GRID, _CADENCE_GRID):
        n += 1
        print(f"[{n:2d}/{total}] M={m} sm={smoothing} {cadence}...", flush=True)
        row = _screen_config(
            m,
            smoothing,
            cadence,
            prices,
            index_prices,
            tri_nifty50,
            ind,
            composite_cache,
            ledger,
        )
        rows.append(row)

    _print_report(rows)
    print(f"\n  ConfigLedger K (this run): {ledger.n_trials}")
    print(
        "  Note: cumulative K for deflated Sharpe at MD3 = Track-A T1–T6 + TBE3 + these 12 configs (2 runs each = 24 ledger entries)."
    )
    print("  FINAL_OOS untouched — Stage 2 (MD2) next if any survivors found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
