"""T07.6 — re-measure frozen S3 on fully identity-continuous data.

The final `07` re-measure. Runs the byte-for-byte frozen S3 config over the RECORDED
DISCOVERY window (2018-02-06 → 2023-06-30, base cost) twice, with identical code, on the
**same stitched store** (`06`'s chain-constant instrument_id) — the ONLY difference is the
`07` merger/cancellation force-exit (Approach A, §6):

  * MERGER-DIRTY: terminate_after_silent_days=0 → force-exit OFF. A held company that
    terminates with no instrument_id successor (merger/cancellation) goes price-silent and
    is carried as an MTM-frozen ghost forever. Reproduces T06.6's `stitched` run
    (succession-clean, merger-dirty).
  * IDENTITY-CONTINUOUS: terminate_after_silent_days=15 (the live S3 default,
    s3_config.S3_TERMINATE_AFTER_SILENT_DAYS) → force-exit ON. Every termination is
    liquidated to cash at its flat last price (§6.2, no haircut) once it is silent ≥ K
    trading days. Succession-clean AND merger-clean = fully identity-continuous.

Only difference between the two = the merger force-exit, so the delta isolates the
merger/cancellation ghost effect (the ISIN-succession stitching of `06` sits in BOTH runs
and cancels). NOT a re-validation — FINAL_OOS stays spent (06 §9, 07 §6.1). Pre-accepted
null on metrics: this is a CORRECTNESS re-measure, not an edge claim.

Replicates SU2 / T06.6's exact methodology (su2_battery.run_survivor lines 381-475):
  base run (cost_level="base") → §6.2 drop-top-10-P&L retention → §6.4 deploy bar
  (Nifty200 Mom30 TRI).

Honest bias carried forward (§6.2, §11): the force-exit prices insolvencies at their flat
last-traded close (optimistic vs the realisable ~0 for names that gapped to zero), so the
identity-continuous numbers may slightly over-state realised value on that sub-type.
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

# T06.6's STITCHED run (succession-clean, merger-dirty; 06 §16 / commit dd226efb) — the
# merger-dirty anchor this script's force-exit-OFF leg must reproduce exactly (same store,
# same config, K=0). NOTE: 0.575 was T06.6's *broken* (raw-isin) leg; its *stitched* leg —
# the correct anchor here — was Calmar 0.496 / Sharpe 0.722 / maxDD 24.8%.
RECORDED = {
    "calmar": 0.496,
    "sharpe": 0.722,
    "max_dd": 0.248,
}

# 07 §6 / §11 — live S3 force-exit horizon (trading days of silence before liquidation).
K = s3_config.S3_TERMINATE_AFTER_SILENT_DAYS


def _measure(
    prices: pd.DataFrame,
    index_prices,
    tri_momentum30,
    *,
    terminate_after_silent_days: int,
) -> dict:
    """Frozen-S3 base + §6.2 retention + §6.4 deploy bar on `prices` over DISCOVERY.

    `terminate_after_silent_days` is threaded into BOTH the base and the §6.2-perturbed
    runs so the force-exit fires identically in each (0 = OFF = merger-dirty).
    """
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
        prices,
        eng,
        index_prices=index_prices,
        cost_level="base",
        signal_store=ss,
        terminate_after_silent_days=terminate_after_silent_days,
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
        terminate_after_silent_days=terminate_after_silent_days,
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
    print(
        f"T07.6 re-measure — frozen S3, DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}  "
        f"(force-exit K={K})\n"
    )
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

    # Both runs use the SAME stitched store (06's instrument_id); only K differs.
    print("[1/2] MERGER-DIRTY (force-exit OFF, K=0) ...", flush=True)
    r_dirty = _measure(
        prices, index_prices, tri_momentum30, terminate_after_silent_days=0
    )
    print(f"[2/2] IDENTITY-CONTINUOUS (force-exit ON, K={K}) ...", flush=True)
    r_clean = _measure(
        prices, index_prices, tri_momentum30, terminate_after_silent_days=K
    )

    def row(label, key, fmt, scale=1.0):
        d, c = r_dirty[key] * scale, r_clean[key] * scale
        rec = RECORDED.get(key)
        rec_s = f"{rec * scale:{fmt}}" if rec is not None else "  —  "
        sign = "→" if abs(c - d) < 1e-9 else ("▲" if c > d else "▼")
        return f"  {label:<22} {rec_s:>9}  {d:{fmt}}  {c:{fmt}}   {sign}"

    print("\n" + "=" * 72)
    print("  metric                  T06.6st    dirty    clean    move")
    print("  " + "-" * 68)
    print(row("Calmar", "calmar", "9.3f"))
    print(row("Sharpe", "sharpe", "9.3f"))
    print(row("max drawdown %", "max_dd", "9.1f", 100.0))
    print(row("§6.2 retention %", "retention", "9.0f", 100.0))
    print("  " + "-" * 68)
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
        d, c = r_dirty[k] * sc, r_clean[k] * sc
        sign = "→" if abs(c - d) < 1e-9 else ("▲" if c > d else "▼")
        print(f"  {lbl:<22} {'  —  ':>9}  {d:{fmt}}  {c:{fmt}}   {sign}")
    print("=" * 72)
    print(f"\n  dirty top-10 dropped: {r_dirty['top_symbols']}")
    print(f"  clean top-10 dropped: {r_clean['top_symbols']}")
    dep_d = (
        "PASS" if r_dirty["dep_strat_calmar"] > r_dirty["dep_bench_calmar"] else "FAIL"
    )
    dep_c = (
        "PASS" if r_clean["dep_strat_calmar"] > r_clean["dep_bench_calmar"] else "FAIL"
    )
    print(f"\n  deploy bar (strat Calmar > bench): dirty={dep_d}  clean={dep_c}")


if __name__ == "__main__":
    main()
