"""
t4_turnover.py — v3 / Track-A T4: parity check + turnover layers on DISCOVERY (H1).

Two parts (specs/v3/01_TRACK_A_TASKS.md → T4):

  1. PARITY (like-for-like wiring test — prereg Erratum T1→T2). The v3 momentum-only
     floor ranks names by the composite *percentile* of raw 12-1 momentum — a strictly
     monotone transform of raw momentum, so the ORDER the engine consumes is identical
     to a raw-momentum v2 reference ranker (v2 `entry_gate` + raw `momentum_12_1`
     ordering, NOT the deployed vol-adjusted `mom/vol` candidate). Run BOTH through the
     UNCHANGED engine on DISCOVERY; Calmar / realized turnover / final equity must match
     to float noise. A mismatch is a wiring bug — fail loud (Rule 12). The historical
     `Calmar ~0.265 / turnover ~934%` are a SANITY BAND only (same order of magnitude),
     NOT an equality target.

  2. TURNOVER LAYERS (prereg §6, H1). One layer at a time, coarse grids (v3_config),
     log every config to the ConfigLedger, plateau-select (tol 0.85), chain the
     accepted knob forward (04 §4):
        Layer 1  cadence    {monthly, quarterly, semi-annual}
        Layer 2  buffer M   {35, 50, 70}          (N=20 fixed)
        Layer 3  smoothing  {0, 2, 3} months
     Report REALIZED turnover (annualized Σ|Δw| from executed rebalances — the
     authoritative magnitude `diag_turnover_decomp` reconciles against executed fills)
     + Calmar for every setting. H1: a coarser knob cuts realized turnover without
     wrecking Calmar (stays within tolerance of the grid best).

DISCOVERY only — FINAL_OOS stays pristine for T5+. Offline: prices and the regime index
load from the local cache; never live yfinance/NSE (Rule 5).

Run:
    backend/venv/bin/python -m app.backtest_v2.t4_turnover
"""

from __future__ import annotations

import dataclasses
import logging
import sys
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.iterate import GridPoint, plateau_check
from app.backtest_v2.signals import SignalStore, precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.v3_config import (
    BUFFER_M_GRID,
    CADENCE_GRID,
    SMOOTHING_GRID,
    V3Config,
)
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

# Regime index fetched over the wider range (warmup before DISCOVERY[0]); same
# cache key as floor.py / iterate.py / diag — an offline cache hit, no network.
_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Plateau tolerance — the same 0.85 fraction the regime layer and the T0 GO
# predicate use (04 §4): a neighbor/alternative must hold >= 85% of the best Calmar.
_TOL = 0.85

# Parity is selection-order equality fed through a deterministic engine, so the
# two runs should be bit-identical; allow only float-formatting noise.
_PARITY_RTOL = 1e-6


# ---------------------------------------------------------------------------
# Config mapping + parity reference store
# ---------------------------------------------------------------------------


def _engine_cfg(v3cfg: V3Config, date_from: date, date_to: date) -> MomentumConfig:
    """Project the V3Config knobs the engine consumes for selection/sizing onto a
    MomentumConfig (cadence → `rebalance`, buffer → `sell_rank_buffer`). Mirrors the
    T2 test's `_engine_cfg`; the multi-factor ordering rides in via the signal_store."""
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


class RawMomentumStore(SignalStore):
    """v2 SignalStore with the ranker swapped to RAW `momentum_12_1` (the prereg
    Erratum T1→T2 parity target). `entry_gate` and all sizing are v2's, unchanged;
    only the ordering differs from the deployed `mom/vol` candidate. Gated names
    always have a non-NaN momentum (the gate requires it), so the raw value is a
    safe sort key. This is the exact reference the v3 momentum-only floor must
    reproduce to numerical tolerance."""

    def ranker(self, day, isin) -> float:  # type: ignore[override]
        row = self._get_row(day, isin)
        if row is None:
            return float("nan")
        return float(row["momentum_12_1"])


# ---------------------------------------------------------------------------
# Single run → (calmar, realized turnover)
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


def _run(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    eng_cfg: MomentumConfig,
    signal_store,
) -> RunStats:
    res = engine.run(
        prices,
        eng_cfg,
        index_prices=index_prices,
        cost_level="base",
        signal_store=signal_store,
    )
    m = metrics.compute_metrics(res)
    return RunStats(
        calmar=m.calmar,
        turnover=m.annualized_turnover,
        sharpe=m.sharpe,
        cagr=m.cagr,
        max_dd=m.max_drawdown,
        final_equity=res.snapshots[-1].equity if res.snapshots else float("nan"),
        n_fills=len(res.fills_log),
    )


# ---------------------------------------------------------------------------
# Plateau-select: among settings within tolerance of the best Calmar, pick the
# one that cuts realized turnover the most (the H1-aligned choice).
# ---------------------------------------------------------------------------


@dataclass
class LayerVerdict:
    selected: object  # the chosen knob setting
    selected_stats: RunStats
    points: list[tuple[object, RunStats]]
    plateau_ok: bool
    explanation: str


def _select_layer(
    knob_name: str,
    grid: list,
    points: list[tuple[object, RunStats]],
    ledger: ConfigLedger,
) -> LayerVerdict:
    """Pick the lowest-turnover setting whose Calmar holds >= tol × best-grid-Calmar
    (H1: cut turnover without wrecking Calmar). The formal plateau_check verdict on
    the Calmar winner is reported alongside as the robustness signal (04 §4)."""
    best_calmar = max(s.calmar for _, s in points)
    threshold = _TOL * best_calmar

    within = [(g, s) for g, s in points if s.calmar >= threshold]
    # Lowest realized turnover among the Calmar-acceptable settings; tie → coarser
    # (later in grid) by preferring the higher grid index.
    selected, sel_stats = min(
        within, key=lambda gs: (gs[1].turnover, -grid.index(gs[0]))
    )

    # Formal plateau check (iterate.plateau_check) on the Calmar winner — uses the
    # ordered grid as the single axis so ±1-step neighbors are adjacent settings.
    gps = [
        GridPoint(
            params={knob_name: g},
            trial_id=0,
            calmar=s.calmar,
            sharpe=s.sharpe,
            cagr=s.cagr,
            max_dd=s.max_dd,
        )
        for g, s in points
    ]
    verdict = plateau_check(gps, axes=[(knob_name, grid)], tolerance=_TOL)

    base_stats = dict(points)[grid[0]]  # grid[0] = finest setting = the floor base
    turnover_cut = (
        (1.0 - sel_stats.turnover / base_stats.turnover) * 100
        if base_stats.turnover > 0
        else 0.0
    )
    explanation = (
        f"selected {knob_name}={selected!r}: Calmar {sel_stats.calmar:.3f} "
        f"(>= {_TOL:.0%}×best {best_calmar:.3f}={threshold:.3f}), realized turnover "
        f"{sel_stats.turnover * 100:.0f}% vs base {base_stats.turnover * 100:.0f}% "
        f"({turnover_cut:+.0f}% turnover). Calmar-winner plateau: "
        f"{'PLATEAU' if verdict.has_plateau else 'SPIKE'} — {verdict.explanation}"
    )
    return LayerVerdict(
        selected=selected,
        selected_stats=sel_stats,
        points=points,
        plateau_ok=verdict.has_plateau,
        explanation=explanation,
    )


def _print_layer(title: str, knob: str, verdict: LayerVerdict) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)
    print(
        f"  {'setting':>14} {'Calmar':>8} {'Turnover%':>10} {'CAGR%':>8} {'fills':>7}"
    )
    print(f"  {'─' * 14} {'─' * 8} {'─' * 10} {'─' * 8} {'─' * 7}")
    for g, s in verdict.points:
        mark = "  ← selected" if g == verdict.selected else ""
        print(
            f"  {str(g):>14} {s.calmar:>8.3f} {s.turnover * 100:>10.0f}"
            f" {s.cagr * 100:>8.2f} {s.n_fills:>7d}{mark}"
        )
    print(f"\n  {verdict.explanation}")


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

    print("v3 / T4 — Parity + turnover layers on DISCOVERY (H1)")
    print(
        f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}  (base cost, regime ON)"
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

    # --- v2 indicator cache: built ONCE, reused for the reference store and every
    #     v3 store (gate inputs don't change with cadence/buffer/smoothing). ---
    floor = V3Config(date_from=DISCOVERY[0], date_to=DISCOVERY[1])
    base_eng = _engine_cfg(floor, DISCOVERY[0], DISCOVERY[1])
    print("Precomputing v2 indicator cache on DISCOVERY (shared)...", flush=True)
    gate_store = precompute_signals(prices, base_eng)
    ind = gate_store._data

    # Momentum-only composite (no smoothing) — reused for parity + Layers 1 & 2.
    composite0 = factors.composite_rank(prices, floor)

    # ----------------------------------------------------------------------- #
    # PART 1 — PARITY: v3 floor  vs  raw-momentum v2 reference
    # ----------------------------------------------------------------------- #
    print("\nPart 1 — parity (v3 momentum-only floor vs raw-momentum v2 reference)...")
    v3_floor_store = V3SignalStore(ind, composite0, floor)
    ref_store = RawMomentumStore(ind, base_eng)

    s_v3 = _run(prices, index_prices, base_eng, v3_floor_store)
    s_ref = _run(prices, index_prices, base_eng, ref_store)

    calmar_match = abs(s_v3.calmar - s_ref.calmar) <= _PARITY_RTOL * max(
        abs(s_ref.calmar), 1e-9
    )
    equity_match = abs(s_v3.final_equity - s_ref.final_equity) <= _PARITY_RTOL * max(
        abs(s_ref.final_equity), 1e-9
    )
    turnover_match = abs(s_v3.turnover - s_ref.turnover) <= _PARITY_RTOL * max(
        abs(s_ref.turnover), 1e-9
    )

    print("=" * 72)
    print("  PARITY CHECK")
    print("=" * 72)
    print(f"  {'metric':>16} {'v3 floor':>14} {'raw-mom ref':>14} {'match':>8}")
    print(f"  {'─' * 16} {'─' * 14} {'─' * 14} {'─' * 8}")
    print(
        f"  {'Calmar':>16} {s_v3.calmar:>14.6f} {s_ref.calmar:>14.6f} {str(calmar_match):>8}"
    )
    print(
        f"  {'Turnover%':>16} {s_v3.turnover * 100:>14.2f}"
        f" {s_ref.turnover * 100:>14.2f} {str(turnover_match):>8}"
    )
    print(
        f"  {'Final equity':>16} {s_v3.final_equity:>14.2f}"
        f" {s_ref.final_equity:>14.2f} {str(equity_match):>8}"
    )
    print(
        f"  {'Fills':>16} {s_v3.n_fills:>14d} {s_ref.n_fills:>14d}"
        f" {str(s_v3.n_fills == s_ref.n_fills):>8}"
    )

    if not (calmar_match and equity_match and turnover_match):
        print(
            "\nFAIL: v3 floor does NOT reproduce the raw-momentum v2 reference. "
            "Per prereg Erratum T1→T2 this is a WIRING BUG — fix before the turnover "
            "layers (Rule 12). Layers NOT run.",
            file=sys.stderr,
        )
        return 1

    # Sanity band only (order of magnitude — NOT an equality target).
    print("\n  Sanity band (historical v2 candidate, order-of-magnitude only):")
    print(f"    Calmar ~0.265 (band)   vs floor {s_v3.calmar:.3f}")
    print(f"    Turnover ~900% (band)  vs floor {s_v3.turnover * 100:.0f}%")
    print(
        "  PARITY: PASS — v3 floor reproduces the raw-momentum reference to tolerance."
    )

    # ----------------------------------------------------------------------- #
    # PART 2 — TURNOVER LAYERS (chained, plateau-selected)
    # ----------------------------------------------------------------------- #
    ledger = ConfigLedger()

    # Layer 1 — cadence. Composite fixed (no smoothing); vary the engine rebalance.
    print("\nPart 2 — Layer 1: rebalance cadence...", flush=True)
    l1_points: list[tuple[object, RunStats]] = []
    for cad in CADENCE_GRID:
        cfg = dataclasses.replace(floor, rebalance_cadence=cad)
        ledger.add({"cadence": cad}, layer="t4_layer1_cadence")
        stats = _run(
            prices,
            index_prices,
            _engine_cfg(cfg, *DISCOVERY),
            V3SignalStore(ind, composite0, cfg),
        )
        l1_points.append((cad, stats))
        print(
            f"  {cad:>14}: calmar={stats.calmar:.3f} turnover={stats.turnover * 100:.0f}%",
            flush=True,
        )
    l1 = _select_layer("cadence", CADENCE_GRID, l1_points, ledger)
    cadence_star = l1.selected

    # Layer 2 — buffer M. cadence=cadence*; composite fixed.
    print("\nPart 2 — Layer 2: sell buffer M...", flush=True)
    l2_points: list[tuple[object, RunStats]] = []
    for m in BUFFER_M_GRID:
        cfg = dataclasses.replace(
            floor, rebalance_cadence=cadence_star, sell_rank_buffer=m
        )
        ledger.add({"cadence": cadence_star, "buffer_M": m}, layer="t4_layer2_buffer")
        stats = _run(
            prices,
            index_prices,
            _engine_cfg(cfg, *DISCOVERY),
            V3SignalStore(ind, composite0, cfg),
        )
        l2_points.append((m, stats))
        print(
            f"  M={m:>3}: calmar={stats.calmar:.3f} turnover={stats.turnover * 100:.0f}%",
            flush=True,
        )
    l2 = _select_layer("buffer_M", BUFFER_M_GRID, l2_points, ledger)
    buffer_star = l2.selected

    # Layer 3 — rank smoothing. cadence*, M*; composite varies (recompute per smoothing).
    print("\nPart 2 — Layer 3: rank smoothing (months)...", flush=True)
    l3_points: list[tuple[object, RunStats]] = []
    composite_cache: dict[int, pd.DataFrame] = {0: composite0}
    for sm in SMOOTHING_GRID:
        cfg = dataclasses.replace(
            floor,
            rebalance_cadence=cadence_star,
            sell_rank_buffer=buffer_star,
            rank_smoothing_months=sm,
        )
        if sm not in composite_cache:
            composite_cache[sm] = factors.composite_rank(prices, cfg)
        ledger.add(
            {"cadence": cadence_star, "buffer_M": buffer_star, "smoothing": sm},
            layer="t4_layer3_smoothing",
        )
        stats = _run(
            prices,
            index_prices,
            _engine_cfg(cfg, *DISCOVERY),
            V3SignalStore(ind, composite_cache[sm], cfg),
        )
        l3_points.append((sm, stats))
        print(
            f"  smoothing={sm}: calmar={stats.calmar:.3f} turnover={stats.turnover * 100:.0f}%",
            flush=True,
        )
    l3 = _select_layer("smoothing", SMOOTHING_GRID, l3_points, ledger)
    smoothing_star = l3.selected

    # --- Reports ---
    _print_layer("LAYER 1 — REBALANCE CADENCE", "cadence", l1)
    _print_layer(
        "LAYER 2 — SELL BUFFER M (cadence=%s)" % (cadence_star,), "buffer_M", l2
    )
    _print_layer(
        "LAYER 3 — RANK SMOOTHING (cadence=%s, M=%s)" % (cadence_star, buffer_star),
        "smoothing",
        l3,
    )

    print("\n" + "=" * 72)
    print("  T4 SUMMARY")
    print("=" * 72)
    print(f"  Parity: PASS (v3 floor == raw-momentum reference to {_PARITY_RTOL:g}).")
    print("  Plateau-selected base config for T5:")
    print(f"    cadence   = {cadence_star}")
    print(f"    buffer M  = {buffer_star}   (N=20 fixed)")
    print(f"    smoothing = {smoothing_star} months")
    print(
        f"  Realized turnover: floor {l1_points[0][1].turnover * 100:.0f}%  →  "
        f"selected base {l3.selected_stats.turnover * 100:.0f}%  "
        f"(Calmar {l1_points[0][1].calmar:.3f} → {l3.selected_stats.calmar:.3f})"
    )
    print(f"  ConfigLedger trials: K = {ledger.n_trials}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
