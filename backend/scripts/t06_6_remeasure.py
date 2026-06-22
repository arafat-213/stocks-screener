"""T06.6 — re-measure frozen S3 on identity-continuous (stitched) data.

Runs the byte-for-byte frozen S3 config (s3_config / r10_oos / SU2 candidate) over the
RECORDED DISCOVERY window (2018-02-06 → 2023-06-30, base cost) twice, with identical code:

  * IDENTITY-BROKEN: instrument_id := isin for every row, so
    backtest_v2.identity.collapse_to_instrument_id no-ops everywhere → raw-isin behaviour
    (momentum-blind new legs + frozen succession ghosts) — reproduces the pre-T06 store.
  * STITCHED: the re-derived store as-is (chain-constant instrument_id).

Only difference between the two = identity stitching, so the delta isolates the
ISIN-succession effect (the merger/cancellation ghosts of `07` sit in BOTH runs and cancel).

Replicates SU2's exact methodology (su2_battery.run_survivor lines 381-475):
  base run (cost_level="base") → §6.2 drop-top-10-P&L retention → §6.4 deploy bar
  (Nifty200 Mom30 TRI). NOT a re-validation — FINAL_OOS stays spent (06 §9).
"""

from __future__ import annotations

import logging

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.stable_universe import build_stable_universe_mask
from app.backtest_v2.su2_battery import (
    _BENCH_FETCH_END,
    _BENCH_FETCH_START,
    _N_TOP_CONTRIBUTORS,
    _engine_cfg,
)
from app.backtest_v2.validation import DISCOVERY
from app.data.bhavcopy import store
from app.paper_v2 import s3_config

for noisy in ("app.backtest_v2", "app.core.strategy", "pandas_ta_classic", "pandas_ta"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

# Recorded identity-broken baseline (08 §13 SU1/SU2 + 10 R10.2) — for cross-check only.
RECORDED = {
    "calmar": 0.575,
    "sharpe": 0.788,
    "max_dd": 0.237,
    "retention": 0.35,
}


def _measure(prices: pd.DataFrame, index_prices, tri_momentum30) -> dict:
    """Frozen-S3 base + §6.2 retention + §6.4 deploy bar on `prices` over DISCOVERY."""
    v3cfg = s3_config.make_s3_v3config(*DISCOVERY)
    eng = _engine_cfg(v3cfg, *DISCOVERY)
    mask = build_stable_universe_mask(
        prices,
        v3cfg.universe_size_U,
        v3cfg.universe_buffer_B,
        v3cfg.universe_rank_lookback_td,
        v3cfg.universe_review_cadence,
    )
    gate_ind = precompute_signals(prices, eng)._data
    composite = factors.composite_rank(prices, v3cfg)
    ss = V3SignalStore(gate_ind, composite, v3cfg, universe_mask=mask)

    # -- Base run (base cost) --
    res_base = engine.run(
        prices, eng, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    m_base = metrics.compute_metrics(res_base)

    # -- §6.2 drop-top-10-P&L retention (same signal store, names removed from prices) --
    top = sorted(m_base.per_name_stats, key=lambda ns: ns.realized_pnl, reverse=True)[
        :_N_TOP_CONTRIBUTORS
    ]
    top_isins = {ns.isin for ns in top}
    prices_perturbed = prices[~prices["isin"].isin(top_isins)].copy()
    res_perturb = engine.run(
        prices_perturbed,
        eng,
        index_prices=index_prices,
        cost_level="base",
        signal_store=ss,
    )
    m_perturb = metrics.compute_metrics(res_perturb)
    retention = (
        m_perturb.calmar / m_base.calmar
        if (m_base.calmar > 0 and m_base.calmar == m_base.calmar)
        else float("nan")
    )

    # -- §6.4 deployment bar (Nifty200 Mom30 TRI, base cost) --
    trading_cal = [pd.Timestamp(s.date) for s in res_base.snapshots]
    bench_aligned = benchmark.align_benchmark(
        tri_momentum30, eng.date_from, trading_cal, eng.starting_capital
    )
    eq = pd.Series(
        [s.equity for s in res_base.snapshots],
        index=pd.DatetimeIndex([pd.Timestamp(s.date) for s in res_base.snapshots]),
    )
    bm = metrics.compute_benchmark_metrics(eq, bench_aligned)

    return {
        "calmar": m_base.calmar,
        "sharpe": m_base.sharpe,
        "max_dd": m_base.max_drawdown,
        "cagr": m_base.cagr,
        "turnover": m_base.annualized_turnover,
        "retention": retention,
        "perturbed_calmar": m_perturb.calmar,
        "top_symbols": [ns.symbol for ns in top],
        "dep_strat_calmar": bm.strategy_calmar,
        "dep_bench_calmar": bm.benchmark_calmar,
        "dep_dd_ratio": bm.max_dd_ratio,
        "n_final_pos": res_base.snapshots[-1].n_positions,
        "n_ghosts": len(res_base.suspension_log),
    }


def main() -> None:
    print(f"T06.6 re-measure — frozen S3, DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}\n")
    prices = store.read_prices_adjusted()
    prices["date"] = pd.to_datetime(prices["date"])
    print(
        f"  store: rows={len(prices):,}  isins={prices['isin'].nunique():,}  "
        f"instrument_ids={prices['instrument_id'].nunique():,}\n",
        flush=True,
    )
    index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    tri_momentum30 = benchmark.load_tri(
        benchmark.TRI_MOMENTUM_30, _BENCH_FETCH_START, _BENCH_FETCH_END
    )

    # identity-broken = collapse no-ops (instrument_id == isin everywhere)
    broken = prices.copy()
    broken["instrument_id"] = broken["isin"].values

    print("[1/2] IDENTITY-BROKEN (instrument_id := isin) ...", flush=True)
    r_broken = _measure(broken, index_prices, tri_momentum30)
    print("[2/2] STITCHED (re-derived instrument_id) ...", flush=True)
    r_stitched = _measure(prices, index_prices, tri_momentum30)

    def row(label, key, fmt, scale=1.0):
        b, s = r_broken[key] * scale, r_stitched[key] * scale
        rec = RECORDED.get(key)
        rec_s = f"{rec * scale:{fmt}}" if rec is not None else "  —  "
        sign = "→" if abs(s - b) < 1e-9 else ("▲" if s > b else "▼")
        return f"  {label:<22} {rec_s:>9}  {b:{fmt}}  {s:{fmt}}   {sign}"

    print("\n" + "=" * 70)
    print("  metric                  recorded    broken  stitched   move")
    print("  " + "-" * 66)
    print(row("Calmar", "calmar", "9.3f"))
    print(row("Sharpe", "sharpe", "9.3f"))
    print(row("max drawdown %", "max_dd", "9.1f", 100.0))
    print(row("§6.2 retention %", "retention", "9.0f", 100.0))
    print("  " + "-" * 66)
    for k, lbl, fmt, sc in [
        ("cagr", "CAGR %", "9.1f", 100.0),
        ("turnover", "turnover %", "9.0f", 100.0),
        ("perturbed_calmar", "§6.2 perturbed Calmar", "9.3f", 1.0),
        ("dep_strat_calmar", "deploy: strat Calmar", "9.3f", 1.0),
        ("dep_bench_calmar", "deploy: bench Calmar", "9.3f", 1.0),
        ("dep_dd_ratio", "deploy: maxDD ratio", "9.2f", 1.0),
        ("n_final_pos", "final n_positions", "9.0f", 1.0),
        ("n_ghosts", "carried ghosts (susp)", "9.0f", 1.0),
    ]:
        b, s = r_broken[k] * sc, r_stitched[k] * sc
        sign = "→" if abs(s - b) < 1e-9 else ("▲" if s > b else "▼")
        print(f"  {lbl:<22} {'  —  ':>9}  {b:{fmt}}  {s:{fmt}}   {sign}")
    print("=" * 70)
    print(f"\n  broken top-10 dropped:   {r_broken['top_symbols']}")
    print(f"  stitched top-10 dropped: {r_stitched['top_symbols']}")
    dep_b = (
        "PASS"
        if r_broken["dep_strat_calmar"] > r_broken["dep_bench_calmar"]
        else "FAIL"
    )
    dep_s = (
        "PASS"
        if r_stitched["dep_strat_calmar"] > r_stitched["dep_bench_calmar"]
        else "FAIL"
    )
    print(f"\n  deploy bar (strat Calmar > bench): broken={dep_b}  stitched={dep_s}")


if __name__ == "__main__":
    main()
