"""
su1_cost_screen.py — v3 / 08 SU1: Stage 1 cost + membership-churn screen.

Pre-registration: specs/v3/08_STABLE_UNIVERSE_PREREG.md §5 (Stage 1) / §13 SU1.

Grid (4 coarse points, fully enumerated — the universe is the ONLY variable;
momentum held constant at the `06` MD1 §6.1 survivor M=130 sm=0 monthly N=20,
5-factor, regime ON, ₹5cr floor as safety):

    C0  floor (status quo, re-floored daily)          — anchor, must reproduce
                                                          MD1 M=130 (base Calmar 0.523)
    S1  stable  U=200  B=1.25  semi-annual            — primary treatment
    S2  stable  U=200  B=1.00  semi-annual            — isolates buffer vs slow-review
    S3  stable  U=350  B=1.25  semi-annual            — universe-breadth sensitivity

For each config:
  - Run at base cost      → record base Calmar, base maxDD, realized turnover,
                            realized membership churn (the hypothesis metric).
  - Run at pessimistic    → §6.1 ratio = C_strat / C_nifty50 (≥ 1.0 clears §6.1).
  - Log both runs to ConfigLedger (K carries — a fresh objective does NOT reset K).

Membership churn is measured with the SAME fill decomposition used by the T3
turnover study (diag_turnover_decomp._decompose_fills): entry+exit Δweight as a
fraction of total Σ|Δw|, applied to annualized turnover. All four configs run
regime ON, so the regime full-book-toggle contribution to "churn" is a CONSTANT
confound across the grid — the C0→S* DELTA isolates the universe effect, which is
exactly the §08 hypothesis ([[turnover-decomp-churn-dominant]]).

DISCOVERY only — FINAL_OOS stays pristine. No §6.2/§6.3/§6.4 here (that is SU2).

Run:
    backend/venv/bin/python -m app.backtest_v2.su1_cost_screen
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.diag_turnover_decomp import _decompose_fills
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.stable_universe import build_stable_universe_mask
from app.backtest_v2.v3_config import TRACK_A_BASELINE, V3Config
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Held-constant momentum construction (08 §3) — the MD1 §6.1 survivor, NOT searched.
_M = 130
_SMOOTHING = 0
_CADENCE = "monthly"


@dataclass
class SU1Config:
    """One §5 grid point — the universe is the only thing that varies."""

    name: str
    universe_mode: str
    universe_size_U: int
    universe_buffer_B: float
    role: str

    @property
    def universe_label(self) -> str:
        if self.universe_mode == "floor":
            return "₹5cr floor (daily)"
        return f"stable U={self.universe_size_U} B={self.universe_buffer_B:g}"


# §5 grid — 4 coarse points, fully enumerated. No level added/removed after results.
_GRID: list[SU1Config] = [
    SU1Config("C0", "floor", 0, 0.0, "anchor (reproduce MD1 M=130, Calmar 0.523)"),
    SU1Config("S1", "stable", 200, 1.25, "primary treatment"),
    SU1Config("S2", "stable", 200, 1.00, "isolate buffer vs slow-review"),
    SU1Config("S3", "stable", 350, 1.25, "universe-breadth sensitivity"),
]


@dataclass
class ScreenRow:
    name: str
    universe_label: str
    base_calmar: float
    base_max_dd: float
    turnover_pct: float
    churn_pct: float
    churn_frac: float
    universe_sizes: str
    c_strat_pessimistic: float
    c_nifty50: float
    calmar_ratio: float
    passes_s61: bool


# ---------------------------------------------------------------------------
# Config plumbing (mirrors md1_cost_screen)
# ---------------------------------------------------------------------------


def _v3_config(cfg: SU1Config) -> V3Config:
    return V3Config(
        active_factors=list(TRACK_A_BASELINE.active_factors),
        rebalance_cadence=_CADENCE,
        sell_rank_buffer=_M,
        rank_smoothing_months=_SMOOTHING,
        target_positions=TRACK_A_BASELINE.target_positions,
        use_regime_overlay=True,
        catastrophic_stop_pct=25.0,
        liquidity_floor_cr=5.0,
        universe_mode=cfg.universe_mode,
        universe_size_U=cfg.universe_size_U if cfg.universe_mode == "stable" else 200,
        universe_buffer_B=cfg.universe_buffer_B
        if cfg.universe_mode == "stable"
        else 1.25,
        date_from=DISCOVERY[0],
        date_to=DISCOVERY[1],
    )


def _engine_cfg(v3cfg: V3Config) -> MomentumConfig:
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
        date_from=v3cfg.date_from,
        date_to=v3cfg.date_to,
    )


def _equity_series(result: engine.EngineResult) -> pd.Series:
    return pd.Series(
        [s.equity for s in result.snapshots],
        index=pd.DatetimeIndex([pd.Timestamp(s.date) for s in result.snapshots]),
    )


def _churn(result: engine.EngineResult, turnover: float) -> tuple[float, float]:
    """
    Realized membership churn from the fill decomposition (entry+exit Δweight).

    Returns (churn_annualized, churn_fraction_of_total). churn_annualized =
    churn_frac × annualized turnover, so it is directly comparable to the
    turnover column and to the [[turnover-decomp-churn-dominant]] 90% baseline.
    """
    dec = _decompose_fills(result)
    total = dec["total"]
    if total <= 0:
        return 0.0, 0.0
    churn_frac = (dec["entry"] + dec["exit"]) / total
    return churn_frac * turnover, churn_frac


# ---------------------------------------------------------------------------
# Screen one config
# ---------------------------------------------------------------------------


def _screen_config(
    cfg: SU1Config,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    tri_nifty50: pd.Series,
    ind: dict[str, pd.DataFrame],
    composite: pd.DataFrame,
    ledger: ConfigLedger,
) -> ScreenRow:
    v3cfg = _v3_config(cfg)
    eng = _engine_cfg(v3cfg)

    mask = None
    universe_sizes = "—"
    if v3cfg.universe_mode == "stable":
        mask = build_stable_universe_mask(
            prices,
            v3cfg.universe_size_U,
            v3cfg.universe_buffer_B,
            v3cfg.universe_rank_lookback_td,
            v3cfg.universe_review_cadence,
        )
        sizes = [n for _, n in mask.size_history()]
        if sizes:
            universe_sizes = f"{min(sizes)}–{max(sizes)} (n={len(sizes)})"
    ss = V3SignalStore(ind, composite, v3cfg, universe_mask=mask)

    ledger_payload = {
        "config": cfg.name,
        "universe_mode": v3cfg.universe_mode,
        "U": v3cfg.universe_size_U if v3cfg.universe_mode == "stable" else None,
        "B": v3cfg.universe_buffer_B if v3cfg.universe_mode == "stable" else None,
        "M": _M,
        "smoothing": _SMOOTHING,
        "cadence": _CADENCE,
    }

    # Base run → Calmar, maxDD, turnover, churn.
    ledger.add({**ledger_payload, "cost_level": "base"}, stage="SU1_base")
    res_base = engine.run(
        prices, eng, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    m_base = metrics.compute_metrics(res_base)
    turnover_pct = m_base.annualized_turnover * 100
    churn_ann, churn_frac = _churn(res_base, m_base.annualized_turnover)

    # Pessimistic run → §6.1 ratio vs Nifty50 TRI.
    ledger.add({**ledger_payload, "cost_level": "pessimistic"}, stage="SU1_pessimistic")
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
        "  %-3s %-22s | base calmar=%.3f maxdd=%.1f%% turn=%4.0f%% churn=%4.0f%%(%.0f%%) "
        "| pess C_strat=%.3f C_n50=%.3f ratio=%.2f %s",
        cfg.name,
        cfg.universe_label,
        m_base.calmar,
        m_base.max_drawdown * 100,
        turnover_pct,
        churn_ann * 100,
        churn_frac * 100,
        bm.strategy_calmar,
        bm.benchmark_calmar,
        bm.calmar_ratio,
        "PASS" if bm.calmar_ratio >= 1.0 else "FAIL",
    )

    return ScreenRow(
        name=cfg.name,
        universe_label=cfg.universe_label,
        base_calmar=m_base.calmar,
        base_max_dd=m_base.max_drawdown,
        turnover_pct=turnover_pct,
        churn_pct=churn_ann * 100,
        churn_frac=churn_frac,
        universe_sizes=universe_sizes,
        c_strat_pessimistic=bm.strategy_calmar,
        c_nifty50=bm.benchmark_calmar,
        calmar_ratio=bm.calmar_ratio,
        passes_s61=bm.calmar_ratio >= 1.0,
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(rows: list[ScreenRow], anchor_ok: bool | None) -> None:
    print()
    print("=" * 104)
    print(
        "  SU1 Stage 1 — 4-config §6.1 cost + membership-churn screen  (DISCOVERY 2018-02-06 → 2023-06-30)"
    )
    print(
        f"  Momentum held constant: 5-factor, N=20, M={_M}, sm={_SMOOTHING}, {_CADENCE}, regime ON, ₹5cr floor"
    )
    print("=" * 104)
    print(
        f"  {'Cfg':>3} | {'Universe':>20} | {'Calmar':>7} | {'MaxDD':>7} | "
        f"{'Turn%':>6} | {'Churn%':>7} | {'C_strat(P)':>10} | {'C_n50':>6} | {'Ratio':>6} | §6.1"
    )
    print(
        f"  {'─' * 3} | {'─' * 20} | {'─' * 7} | {'─' * 7} | {'─' * 6} | {'─' * 7} | "
        f"{'─' * 10} | {'─' * 6} | {'─' * 6} | {'─' * 5}"
    )
    for r in rows:
        mark = "PASS" if r.passes_s61 else "FAIL"
        print(
            f"  {r.name:>3} | {r.universe_label:>20} | {r.base_calmar:>7.3f} | "
            f"{r.base_max_dd:>7.1%} | {r.turnover_pct:>6.0f} | "
            f"{r.churn_pct:>6.0f}% | {r.c_strat_pessimistic:>10.3f} | "
            f"{r.c_nifty50:>6.3f} | {r.calmar_ratio:>6.2f} | {mark}"
        )

    print("\n  Stable-universe realized membership sizes (per semi-annual review):")
    for r in rows:
        if r.universe_sizes != "—":
            print(f"    {r.name}: {r.universe_sizes}")

    survivors = [r for r in rows if r.passes_s61]
    print()
    print("=" * 104)
    if anchor_ok is not None:
        print(
            f"  C0 anchor (base Calmar ≈ 0.523): {'REPRODUCED' if anchor_ok else 'MISMATCH — FAIL LOUD'}"
        )
    print(f"  §6.1 survivors (ratio ≥ 1.0): {len(survivors)}/{len(rows)} configs")
    if survivors:
        for r in survivors:
            print(
                f"    → {r.name} {r.universe_label} "
                f"(base Calmar {r.base_calmar:.3f}, ratio {r.calmar_ratio:.2f}, churn {r.churn_pct:.0f}%)"
            )
    else:
        print(
            "    → NULL — no config clears §6.1. Carry the churn diagnostic to SU2 close (08 §6)."
        )

    # The §08 hypothesis: did stabilizing the universe move the churn mechanism?
    c0 = next((r for r in rows if r.name == "C0"), None)
    if c0 is not None:
        print("\n  Churn-mechanism check (the §08 hypothesis — C0 vs stable):")
        for r in rows:
            if r.name == "C0":
                continue
            delta = r.churn_pct - c0.churn_pct
            print(
                f"    {r.name}: churn {c0.churn_pct:.0f}% → {r.churn_pct:.0f}% "
                f"(Δ {delta:+.0f} pp), turnover {c0.turnover_pct:.0f}% → {r.turnover_pct:.0f}%"
            )
    print("=" * 104)


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

    print("v3 / 08 SU1 — Stage 1: 4-config §6.1 cost + churn screen on DISCOVERY")
    print("  Grid: C0 floor | S1 U=200 B=1.25 | S2 U=200 B=1.0 | S3 U=350 B=1.25")
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

    # Shared gate indicator cache + composite (momentum is identical across the
    # grid: 5-factor sm=0 — only the universe mask differs per config).
    ref_v3 = _v3_config(_GRID[0])
    print(
        "Precomputing v2 indicator cache + composite on DISCOVERY (shared)...",
        flush=True,
    )
    gate_store = precompute_signals(prices, _engine_cfg(ref_v3))
    ind = gate_store._data
    composite = factors.composite_rank(prices, ref_v3)

    ledger = ConfigLedger()
    rows: list[ScreenRow] = []
    for i, cfg in enumerate(_GRID, 1):
        print(
            f"[{i}/{len(_GRID)}] {cfg.name} — {cfg.universe_label} ({cfg.role})...",
            flush=True,
        )
        rows.append(
            _screen_config(
                cfg, prices, index_prices, tri_nifty50, ind, composite, ledger
            )
        )

    c0 = next((r for r in rows if r.name == "C0"), None)
    anchor_ok = None if c0 is None else (abs(c0.base_calmar - 0.523) <= 0.01)

    _print_report(rows, anchor_ok)
    print(f"\n  ConfigLedger K (this run): {ledger.n_trials}")
    print(
        "  Cumulative K for deflated Sharpe at SU3 = ledger (≥46 at TBE7) + these 8 entries (08 §8)."
    )
    print("  FINAL_OOS untouched — SU2 (full battery) next on the §6.1-clearing set.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
