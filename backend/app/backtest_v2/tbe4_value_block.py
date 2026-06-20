"""
tbe4_value_block.py — TBE4: Layer B1 — add the Value block {E/P, B/P}.

Layer B1: holds all Track-A construction knobs at their accepted values (TBE0
TRACK_A_BASELINE), adds the Value block (equal-blend of E/P and B/P, 03 §6 B1)
to active_factors, and runs the engine on TRACK_B_DISCOVERY at base cost.

Fundamental frames are built via compute_fundamental_factor_frame with a bulk
in-memory cache (same PIT logic as read_fundamentals_asof, no per-cell DB query).
All reads go through the injected reader seam — no raw ORM access (03 §4.1).

Acceptance rule (03 §6 / 04 §4):
  ACCEPT  if B1_Calmar >= TBE3_baseline_Calmar  AND  §6.4 spread not worsened.
  DROP    if B1_Calmar < baseline OR §6.4 spread clearly worsens.
  "Plateau" for a binary block add = the block as a whole helps; no within-block
  parameter grid exists (03 §11 item 2). Report honestly either way (Rule 12).

TBE3 baseline anchor (logged 2026-06-19, 4 ledger entries):
  Calmar 1.591 | CAGR 24.1% | MaxDD 15.13% | Sharpe 1.335 | Turnover 1038%
  §6.4 spread: 2.07x (passes_concentration_hard: TRUE — ⚠ unexpected PASS)
  Cumulative ConfigLedger K entering TBE4: 20 (16 Track-A + 4 TBE3)

Run:
    backend/venv/bin/python -m app.backtest_v2.tbe4_value_block
"""

from __future__ import annotations

import datetime
import logging
import math
import sys
from collections import defaultdict
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.engine import _rebalance_dates
from app.backtest_v2.fundamental_factors import compute_fundamental_factor_frame
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.v3_config import (
    TRACK_A_BASELINE,
    TRACK_B_DISCOVERY,
    VALUE_BLOCK,
    V3Config,
    passes_concentration_hard,
)
from app.backtest_v2.validation import ConfigLedger
from app.data.bhavcopy import store
from app.db.session import SessionLocal
from app.fundamentals.models import FundamentalsLineItemVersion
from app.fundamentals.reader import FundamentalsSnapshot, _cutoff, _to_snapshot

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# TBE3 anchor — logged 2026-06-19, not re-run (adds K unnecessarily).
_TBE3_CALMAR = 1.591
_TBE3_SPREAD = 2.07
_TBE3_SEC64_PASSES = True  # baseline unexpectedly passes §6.4 on Track-B window

# Reuse the pre-committed Track-B subperiods from TBE3 (LOCKED, Rule 12).
TRACK_B_SUBPERIODS: list[tuple[str, date, date]] = [
    ("COVID crash + V-recovery", date(2020, 1, 31), date(2021, 3, 31)),
    ("Post-COVID bull", date(2021, 4, 1), date(2022, 1, 31)),
    ("Rate-hike correction", date(2022, 2, 1), date(2023, 6, 30)),
]

LIQ_FLOOR_CR = 5.0  # same as V3Config default


# ---------------------------------------------------------------------------
# Bulk-cache helpers (mirrors tbe2_characterize.py — same PIT logic)
# Not imported from tbe2 to avoid cross-script coupling (Rule 3).
# ---------------------------------------------------------------------------


def _build_bulk_cache(
    session,
    isin_set: set[str],
) -> dict[str, list]:
    """Bulk-load all FundamentalsLineItemVersion rows for isin_set into memory.

    Returns dict[isin → list[FundamentalsLineItemVersion]], all rows included;
    PIT cutoff is applied per-call in the reader returned by _make_cached_reader.
    Chunked to avoid overly long IN clauses.
    """
    if not isin_set:
        return {}
    isins = list(isin_set)
    chunk = 500
    all_rows: list[FundamentalsLineItemVersion] = []
    for i in range(0, len(isins), chunk):
        batch = isins[i : i + chunk]
        rows = (
            session.query(FundamentalsLineItemVersion)
            .filter(FundamentalsLineItemVersion.isin.in_(batch))
            .all()
        )
        all_rows.extend(rows)
    cache: dict[str, list] = defaultdict(list)
    for row in all_rows:
        cache[row.isin].append(row)
    return dict(cache)


def _make_cached_reader(cache: dict[str, list]):
    """Return a read_fundamentals_asof-compatible callable backed by the in-memory cache.

    Applies the same PIT + restatement logic as the real reader (TB5 contract preserved).
    """

    def _reader(
        session,
        isin: str,
        as_of_date: datetime.date,
    ) -> list[FundamentalsSnapshot]:
        cutoff = _cutoff(as_of_date)
        rows = [r for r in cache.get(isin, []) if r.available_date <= cutoff]
        if not rows:
            return []
        best: dict[datetime.date, FundamentalsLineItemVersion] = {}
        for row in rows:
            prev = best.get(row.period_end)
            if prev is None or row.available_date > prev.available_date:
                best[row.period_end] = row
        return [
            _to_snapshot(r)
            for r in sorted(best.values(), key=lambda r: r.period_end, reverse=True)
        ]

    return _reader


# ---------------------------------------------------------------------------
# Config plumbing (mirrors tbe3_baseline.py)
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
# Fundamental frame builder
# ---------------------------------------------------------------------------


def _build_fund_frames(
    prices: pd.DataFrame,
    rebalance_dates: list[date],
    session,
) -> dict[str, pd.DataFrame]:
    """Build E/P and B/P raw-value frames (date × isin) for all DISCOVERY rebalances.

    Uses a bulk-preloaded in-memory cache for performance (single DB query per
    ISIN batch rather than one query per (isin, date) cell). The cached reader
    applies the same PIT + restatement logic as read_fundamentals_asof (TB5).

    Financial ISINs are passed as frozenset() (empty) — E/P and B/P include
    financials per 03 §3 (only accruals/leverage exclude them).
    """
    all_isins: set[str] = set(prices["isin"].unique().tolist())
    print(
        f"  Bulk-loading fundamentals for {len(all_isins):,} ISINs from DB...",
        flush=True,
    )
    cache = _build_bulk_cache(session, all_isins)
    reader = _make_cached_reader(cache)
    print(
        f"  Loaded {sum(len(v) for v in cache.values()):,} rows "
        f"for {len(cache):,} ISINs",
        flush=True,
    )

    frames: dict[str, pd.DataFrame] = {}
    for factor_name in sorted(VALUE_BLOCK):  # earnings_yield, book_to_price
        print(
            f"  Computing {factor_name} frame ({len(rebalance_dates)} dates)...",
            flush=True,
        )
        frame = compute_fundamental_factor_frame(
            factor_name,
            session,
            prices,
            rebalance_dates,
            financial_isins=frozenset(),  # E/P + B/P include financials (03 §3)
            reader=reader,
        )
        n_non_null = int(frame.notna().sum().sum())
        total_cells = frame.shape[0] * frame.shape[1]
        coverage = n_non_null / total_cells * 100 if total_cells > 0 else 0.0
        print(
            f"    {factor_name}: {n_non_null:,}/{total_cells:,} cells non-null "
            f"({coverage:.1f}%)",
            flush=True,
        )
        frames[factor_name] = frame

    return frames


# ---------------------------------------------------------------------------
# §6.4 helpers
# ---------------------------------------------------------------------------


def _sec64_analysis(
    calmars_finite: list[float],
) -> tuple[bool, float, float, float]:
    """Returns (passes, spread_ratio, best, others_mean)."""
    positives = sorted([c for c in calmars_finite if c > 0], reverse=True)
    if len(positives) >= 2:
        best = positives[0]
        others_mean = sum(positives[1:]) / len(positives[1:])
        spread = best / others_mean if others_mean > 0 else float("inf")
    else:
        best = positives[0] if positives else float("nan")
        others_mean = float("nan")
        spread = float("nan")
    n_positive = sum(1 for c in calmars_finite if c > 0)
    positivity_ok = n_positive >= 2
    conc_ok = passes_concentration_hard(calmars_finite)
    return positivity_ok and conc_ok, spread, best, others_mean


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

    # B1 config: Track-A knobs + value block (E/P + B/P)
    b1_active = list(TRACK_A_BASELINE.active_factors) + sorted(VALUE_BLOCK)
    b1_cfg = V3Config(
        active_factors=b1_active,
        rebalance_cadence=TRACK_A_BASELINE.rebalance_cadence,
        sell_rank_buffer=TRACK_A_BASELINE.sell_rank_buffer,
        rank_smoothing_months=TRACK_A_BASELINE.rank_smoothing_months,
        target_positions=TRACK_A_BASELINE.target_positions,
        date_from=tb_start,
        date_to=tb_end,
    )

    print("=" * 78)
    print("  v3 / TBE4 — Layer B1: add Value block {E/P, B/P}")
    print(f"  Window:   {tb_start} → {tb_end}")
    print(f"  B1 factors: {b1_cfg.active_factors}")
    print(
        f"  Construction: cadence={b1_cfg.rebalance_cadence}  "
        f"M={b1_cfg.sell_rank_buffer}  smoothing={b1_cfg.rank_smoothing_months}  N=20"
    )
    print(f"  TBE3 baseline anchor: Calmar={_TBE3_CALMAR}  spread={_TBE3_SPREAD}x")
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

    # ------------------------------------------------------------------
    # Compute rebalance dates for TRACK_B_DISCOVERY
    # ------------------------------------------------------------------
    tb_prices = prices[
        (prices["date"] >= pd.Timestamp(tb_start))
        & (prices["date"] <= pd.Timestamp(tb_end))
    ]
    calendar = sorted(tb_prices["date"].unique().tolist())
    rebalance_timestamps = sorted(_rebalance_dates(calendar, "monthly"))
    rebalance_dates_plain: list[date] = [ts.date() for ts in rebalance_timestamps]
    print(
        f"\nTrack-B DISCOVERY rebalance dates: {len(rebalance_dates_plain)} "
        f"({rebalance_dates_plain[0]} → {rebalance_dates_plain[-1]})",
        flush=True,
    )

    # ------------------------------------------------------------------
    # Build fundamental frames via bulk-cache (E/P, B/P)
    # ------------------------------------------------------------------
    print("\nBuilding fundamental factor frames for Value block...", flush=True)
    session = SessionLocal()
    try:
        fund_frames = _build_fund_frames(prices, rebalance_dates_plain, session)
    finally:
        session.close()

    # ------------------------------------------------------------------
    # Build composite signal store for B1
    # ------------------------------------------------------------------
    print("\nPrecomputing v2 indicator cache (gate inputs)...", flush=True)
    ind = precompute_signals(prices, _engine_cfg(b1_cfg, tb_start, tb_end))._data

    print("Building Track-B composite rank (Track-A + Value block)...", flush=True)
    composite = factors.composite_rank(prices, b1_cfg, extra_raw_frames=fund_frames)
    signal_store = V3SignalStore(ind, composite, b1_cfg)

    ledger = ConfigLedger()
    eng_cfg_full = _engine_cfg(b1_cfg, tb_start, tb_end)

    # ------------------------------------------------------------------
    # Main B1 run — TRACK_B_DISCOVERY, base cost
    # ------------------------------------------------------------------
    print("\nMain B1 run (base cost, TRACK_B_DISCOVERY)...", flush=True)
    ledger.add(
        {
            "task": "TBE4",
            "layer": "B1",
            "active_factors": b1_active,
            "cadence": b1_cfg.rebalance_cadence,
            "M": b1_cfg.sell_rank_buffer,
            "smoothing": b1_cfg.rank_smoothing_months,
            "window": f"{tb_start}→{tb_end}",
            "cost_level": "base",
        },
        check="TBE4_B1_full",
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
                tri_nm30, tb_start, trading_cal, b1_cfg.starting_capital
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

    # ------------------------------------------------------------------
    # Subperiod runs — same pre-committed dates as TBE3 (LOCKED, Rule 12)
    # ------------------------------------------------------------------
    print("\nSubperiod analysis (§6.4)...", flush=True)
    subresults: list[tuple[str, metrics.BacktestMetrics]] = []
    for label, s_start, s_end in TRACK_B_SUBPERIODS:
        ledger.add(
            {
                "task": "TBE4",
                "layer": "B1",
                "subperiod": label,
                "start": str(s_start),
                "end": str(s_end),
                "cost_level": "base",
            },
            check="TBE4_B1_subperiod",
        )
        eng_sub = _engine_cfg(b1_cfg, s_start, s_end)
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
    sec64_passes, spread_ratio, best_calmar, others_mean = _sec64_analysis(
        calmars_finite
    )
    n_positive = sum(1 for c in calmars_finite if c > 0)

    # ------------------------------------------------------------------
    # Accept / Drop verdict (03 §6 / 04 §4)
    # ------------------------------------------------------------------
    calmar_delta = main_m.calmar - _TBE3_CALMAR
    spread_delta = spread_ratio - _TBE3_SPREAD
    calmar_improved = main_m.calmar >= _TBE3_CALMAR
    sec64_not_worse = (
        not math.isnan(spread_ratio) and spread_ratio <= _TBE3_SPREAD * 1.10
    )  # allow 10% tolerance — report honestly regardless

    # Per 04 §4: accept if clear improvement + §6.4 not worsened.
    # For a binary add (no parameter grid), "plateau" = the block helps.
    layer_accepted = calmar_improved and sec64_not_worse

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    print()
    print("=" * 78)
    print("  TBE4 RESULTS — Layer B1: Value block {E/P, B/P}")
    print("=" * 78)

    print(f"\n  Window:     {tb_start} → {tb_end}")
    print(f"  B1 factors: {b1_active}")
    print(
        f"  Construction: cadence={b1_cfg.rebalance_cadence}  "
        f"M={b1_cfg.sell_rank_buffer}  smoothing={b1_cfg.rank_smoothing_months}"
    )

    print("\n  Full-window B1 (base cost):")
    print(f"    Calmar:           {main_m.calmar:.3f}  (TBE3 baseline: {_TBE3_CALMAR})")
    print(f"    Calmar delta:     {calmar_delta:+.3f}")
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

    print("\n  §6.4 Subperiod Calmars (B1 vs TBE3 baseline):")
    baseline_sub_calmars = [4.963, 4.530, 0.274]  # TBE3 logged values
    for (label, sub_m), base_c in zip(subresults, baseline_sub_calmars):
        marker = "  ✓" if sub_m.calmar > 0 else "  ✗"
        delta = sub_m.calmar - base_c
        print(
            f"    {marker} '{label}':"
            f"  B1={sub_m.calmar:.3f}  baseline={base_c:.3f}  delta={delta:+.3f}"
            f"  cagr={sub_m.cagr * 100:.1f}%"
            f"  maxdd={sub_m.max_drawdown:.2%}"
        )

    print("\n  §6.4 Concentration analysis (B1):")
    print(f"    n_positive subperiods:     {n_positive}/3  (need >= 2)")
    print(f"    best positive Calmar:      {best_calmar:.3f}  (baseline best: {4.963})")
    print(
        f"    mean of other positives:   {others_mean:.3f}  "
        f"(baseline mean: {(4.530 + 0.274) / 2:.3f})"
    )
    print(
        f"    spread ratio (best/mean):  {spread_ratio:.2f}x  "
        f"(baseline: {_TBE3_SPREAD}x  threshold: 5.0x)"
    )
    print(f"    spread delta vs baseline:  {spread_delta:+.2f}x")
    print(f"    passes_concentration_hard: {sec64_passes}")
    result_str = "PASS" if sec64_passes else "FAIL"
    print(f"\n  §6.4 overall:  >>> {result_str} <<<")

    print("\n  Layer B1 acceptance criteria:")
    print(f"    Calmar improved vs baseline: {calmar_improved}  ({calmar_delta:+.3f})")
    print(
        f"    §6.4 spread not worsened:    {sec64_not_worse}  (delta {spread_delta:+.2f}x)"
    )
    verdict_str = "ACCEPT" if layer_accepted else "DROP"
    print(f"\n  Layer B1 verdict:  >>> {verdict_str} <<<")

    if layer_accepted:
        print("\n  Value block accepted — composite advances to TBE5 with B1 active.")
        print(f"  Accepted config active_factors: {b1_active}")
    else:
        print("\n  Value block DROPPED — TBE5 proceeds from the prior accepted config")
        print("  (baseline = Track-A only, per 03 §6 honest-drop rule).")

    print(
        f"\n  ConfigLedger K this session: {ledger.n_trials}  (1 main + 3 subperiods)"
    )
    print(f"  Cumulative K (20 prior + {ledger.n_trials} TBE4): {20 + ledger.n_trials}")
    print("\n  FINAL_OOS: UNTOUCHED (TBE8 only, on TBE7 PASS + H3 confirmed)")
    print("=" * 78)

    return 0


if __name__ == "__main__":
    sys.exit(main())
