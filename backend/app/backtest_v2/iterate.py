"""
iterate.py — Spec 04 T3: single-layer coarse-grid harness + plateau detector.

One layer at a time, on DISCOVERY only.  Every config hits the ConfigLedger
so the K-trial count is always accurate for deflated-Sharpe discounting.
The plateau rule — not the peak — determines acceptability (04 §4).

Layer 1 (this session): regime-overlay calibration (debounce_days × risk_off_floor).
Layers 2–5 are subsequent calls with different axes; they are not pre-built (Rule 2).

Run layer 1:
    backend/venv/bin/python -m app.backtest_v2.iterate
"""

from __future__ import annotations

import dataclasses
import itertools
import logging
import sys
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from app.backtest_v2 import benchmark, engine, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.regime import RegimeConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer 1 coarse grids — regime overlay (spec 04 §4 priority 1)
# Debounce window: 7 values; risk-off floor: 3 values → 21 combos total.
# No 1700-combo sweeps: coarse grids only (04 §4).
# ---------------------------------------------------------------------------

REGIME_DEBOUNCE_GRID: list[int] = [1, 3, 5, 7, 10, 15, 20]
REGIME_RISK_OFF_GRID: list[float] = [0.0, 0.25, 0.50]

# Reuse the cached range from T1 to avoid re-downloading benchmark data.
_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class GridPoint:
    """Outcome of one (params, config) run on DISCOVERY."""

    params: dict[
        str, Any
    ]  # swept params, e.g. {"debounce_days": 3, "risk_off_floor": 0.0}
    trial_id: int
    calmar: float
    sharpe: float
    cagr: float
    max_dd: float


@dataclass
class PlateauVerdict:
    """Output of plateau_check: whether the winner sits on a plateau or is a lone spike."""

    has_plateau: bool
    winner: GridPoint
    neighbors: list[GridPoint]  # all immediate grid neighbors that were checked
    tolerance: float
    explanation: str


# ---------------------------------------------------------------------------
# Plateau detector — the core anti-overfit primitive (04 §4)
# ---------------------------------------------------------------------------


def plateau_check(
    points: list[GridPoint],
    axes: list[tuple[str, list]],
    tolerance: float = 0.85,
) -> PlateauVerdict:
    """
    Detect whether the winning GridPoint has a genuine plateau or is a lone spike.

    A plateau exists iff every immediate neighbor (distance-1 step in any
    parameter dimension) achieves calmar >= tolerance × winner.calmar.
    A lone peak surrounded by poor values → has_plateau=False → reject.

    WHY this is the primary overfit defense: a parameter that only works at
    an exact value and collapses on either side is a curve-fit artifact.  The
    plateau rule rejects it without needing a held-out OOS block, so it is
    cheap and can be applied during discovery iteration (04 §4).

    Parameters
    ----------
    points : list[GridPoint]
        All grid results for one layer run on DISCOVERY.
    axes : list[tuple[str, list]]
        [(param_name, sorted_values)] defining each grid dimension.
        Values must be sorted ascending so that ±1 index = adjacent step.
    tolerance : float
        Fraction of winner calmar a neighbor must achieve (default 0.85).

    Returns
    -------
    PlateauVerdict
        has_plateau=True only if all available immediate neighbors pass.
        A winner at a grid boundary with zero neighbors is conservatively
        treated as has_plateau=False (no evidence of robustness).
    """
    if not points:
        raise ValueError("points list is empty — nothing to check.")

    winner = max(points, key=lambda p: p.calmar)

    if winner.calmar <= 0.0:
        return PlateauVerdict(
            has_plateau=False,
            winner=winner,
            neighbors=[],
            tolerance=tolerance,
            explanation=(
                f"Winner calmar={winner.calmar:.3f} <= 0 — the best config loses money "
                "on discovery.  No plateau is meaningful here; reject the layer."
            ),
        )

    def _indices(pt: GridPoint) -> tuple:
        return tuple(ax_vals.index(pt.params[ax_name]) for ax_name, ax_vals in axes)

    index_to_pt: dict[tuple, GridPoint] = {_indices(p): p for p in points}
    winner_idx = _indices(winner)

    neighbors: list[GridPoint] = []
    for dim, (_, ax_vals) in enumerate(axes):
        for delta in (-1, +1):
            nbr = list(winner_idx)
            nbr[dim] += delta
            key = tuple(nbr)
            if key in index_to_pt:
                neighbors.append(index_to_pt[key])

    if not neighbors:
        return PlateauVerdict(
            has_plateau=False,
            winner=winner,
            neighbors=[],
            tolerance=tolerance,
            explanation=(
                f"Winner {winner.params} has no neighbors in the grid. "
                "Cannot confirm a plateau — treating as spike (conservative)."
            ),
        )

    threshold = tolerance * winner.calmar
    failing = [n for n in neighbors if n.calmar < threshold]

    if failing:
        failing_desc = ";  ".join(f"{n.params} calmar={n.calmar:.3f}" for n in failing)
        return PlateauVerdict(
            has_plateau=False,
            winner=winner,
            neighbors=neighbors,
            tolerance=tolerance,
            explanation=(
                f"SPIKE — {len(failing)}/{len(neighbors)} neighbor(s) below "
                f"{tolerance:.0%} × {winner.calmar:.3f} = {threshold:.3f}: "
                f"{failing_desc}.  "
                f"Winner {winner.params} is a lone peak — reject (04 §4)."
            ),
        )

    min_nbr_calmar = min(n.calmar for n in neighbors)
    return PlateauVerdict(
        has_plateau=True,
        winner=winner,
        neighbors=neighbors,
        tolerance=tolerance,
        explanation=(
            f"PLATEAU — all {len(neighbors)} neighbor(s) >= {tolerance:.0%} × "
            f"{winner.calmar:.3f} = {threshold:.3f}.  "
            f"Min neighbor calmar = {min_nbr_calmar:.3f}.  "
            f"Winner {winner.params} sits on a genuine plateau (04 §4)."
        ),
    )


# ---------------------------------------------------------------------------
# Regime-layer runner
# ---------------------------------------------------------------------------


def run_regime_layer(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    ledger: ConfigLedger,
    debounce_grid: list[int] = REGIME_DEBOUNCE_GRID,
    risk_off_grid: list[float] = REGIME_RISK_OFF_GRID,
    floor_config: MomentumConfig | None = None,
) -> list[GridPoint]:
    """
    Run the regime coarse grid on DISCOVERY only; log every combo to ledger.

    Sweeps RegimeConfig.debounce_days × RegimeConfig.risk_off_floor while
    holding all MomentumConfig knobs at floor values (04 §4 — one layer at a time).
    Signals are precomputed once and reused across all regime combos.

    WHY DISCOVERY only: FINAL_OOS must be pristine for T5.  The function
    pins date_from/date_to to DISCOVERY so it is structurally impossible
    to accidentally consume the held-out OOS block.

    Parameters
    ----------
    prices : pd.DataFrame
        Full prices_adjusted dataset (unfiltered — includes warmup data before
        DISCOVERY so signal precompute has enough history at DISCOVERY[0]).
    index_prices : pd.Series
        Real Nifty 50 price index from benchmark.load_price_index.
    ledger : ConfigLedger
        Every combo is registered here before its engine run.
    debounce_grid, risk_off_grid : lists
        Coarse parameter grids to sweep.
    floor_config : MomentumConfig | None
        All non-regime knobs; defaults to MomentumConfig() (floor defaults).
    """
    if floor_config is None:
        floor_config = MomentumConfig()

    disc_config = dataclasses.replace(
        floor_config,
        date_from=DISCOVERY[0],
        date_to=DISCOVERY[1],
    )

    log.info(
        "Precomputing signals on DISCOVERY (%s → %s)...", DISCOVERY[0], DISCOVERY[1]
    )
    signal_store = precompute_signals(prices, disc_config)

    combos = list(itertools.product(debounce_grid, risk_off_grid))
    log.info("Running %d regime combos on DISCOVERY...", len(combos))

    results: list[GridPoint] = []
    for debounce, risk_off in combos:
        params: dict[str, Any] = {
            "debounce_days": debounce,
            "risk_off_floor": risk_off,
        }
        trial_id = ledger.add(params, layer="regime_layer1")

        regime_cfg = RegimeConfig(debounce_days=debounce, risk_off_floor=risk_off)
        result = engine.run(
            prices,
            disc_config,
            index_prices=index_prices,
            regime_config=regime_cfg,
            cost_level="base",
            signal_store=signal_store,
        )
        m = metrics.compute_metrics(result)
        gp = GridPoint(
            params=params,
            trial_id=trial_id,
            calmar=m.calmar,
            sharpe=m.sharpe,
            cagr=m.cagr,
            max_dd=m.max_drawdown,
        )
        results.append(gp)
        log.info(
            "  #%d  debounce=%2d  risk_off=%.2f → calmar=%.3f  sharpe=%.3f  cagr=%.2f%%",
            trial_id,
            debounce,
            risk_off,
            m.calmar,
            m.sharpe,
            m.cagr * 100,
        )

    return results


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------


def _print_grid_report(
    points: list[GridPoint],
    debounce_grid: list[int],
    risk_off_grid: list[float],
) -> None:
    ranked = sorted(points, key=lambda p: p.calmar, reverse=True)
    print()
    print("=" * 72)
    print("  LAYER 1 — REGIME CALIBRATION  (Calmar on DISCOVERY at base cost)")
    print(f"  DISCOVERY window: {DISCOVERY[0]} → {DISCOVERY[1]}")
    print("=" * 72)
    print(
        f"\n  {'Rank':<5} {'debounce':>9} {'risk_off':>10}"
        f" {'Calmar':>8} {'Sharpe':>8} {'CAGR%':>8} {'MaxDD%':>8}"
    )
    print(f"  {'─' * 5} {'─' * 9} {'─' * 10} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8}")
    for rank, gp in enumerate(ranked, 1):
        d = gp.params["debounce_days"]
        r = gp.params["risk_off_floor"]
        marker = "  ← winner" if rank == 1 else ""
        print(
            f"  {rank:<5} {d:>9} {r:>10.2f}"
            f" {gp.calmar:>8.3f} {gp.sharpe:>8.3f}"
            f" {gp.cagr * 100:>8.2f} {gp.max_dd * 100:>8.2f}{marker}"
        )

    print()
    print("  Calmar grid (rows=debounce_days, cols=risk_off_floor):")
    pt_map = {
        (p.params["debounce_days"], p.params["risk_off_floor"]): p.calmar
        for p in points
    }
    header = " " * 14 + "".join(f"  rof={r:.2f}" for r in risk_off_grid)
    print(f"  {header}")
    for d in debounce_grid:
        row = f"  deb={d:>3d}     "
        for r in risk_off_grid:
            c = pt_map.get((d, r), float("nan"))
            row += f"  {c:7.3f}"
        print(row)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Suppress all expected-noise loggers so only grid progress lines appear.
    # These messages (MTM carry, no-open-price fill drops, cat-stop triggers,
    # buy-scaling, short-ISIN indicator skips) are all normal engine behaviour
    # during a sweep; they are not errors and drown the meaningful output.
    for _noisy in (
        "app.backtest_v2.portfolio",
        "app.backtest_v2.engine",
        "app.core.strategy",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(_noisy).setLevel(logging.ERROR)

    print("Spec 04 T3 — Layer 1: Regime Overlay Calibration")
    print(f"  Grid: debounce={REGIME_DEBOUNCE_GRID}")
    print(f"        risk_off={REGIME_RISK_OFF_GRID}")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    print()

    print("Loading prices_adjusted...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(
        f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}  "
        f"range={prices['date'].min().date()} → {prices['date'].max().date()}",
        flush=True,
    )

    print("Loading real Nifty 50 price index (cached from T1)...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(f"FAIL: regime index unavailable: {exc}", file=sys.stderr)
        return 2
    print(
        f"  index points={len(index_prices):,}  "
        f"level {index_prices.iloc[0]:.0f} → {index_prices.iloc[-1]:.0f}",
        flush=True,
    )

    ledger = ConfigLedger()

    print(
        f"\nRunning {len(REGIME_DEBOUNCE_GRID) * len(REGIME_RISK_OFF_GRID)}"
        " regime combos on DISCOVERY...",
        flush=True,
    )
    points = run_regime_layer(prices, index_prices, ledger)

    _print_grid_report(points, REGIME_DEBOUNCE_GRID, REGIME_RISK_OFF_GRID)

    # Plateau check (tolerance=0.85 — same fraction as the T0 GO predicate)
    axes: list[tuple[str, list]] = [
        ("debounce_days", REGIME_DEBOUNCE_GRID),
        ("risk_off_floor", REGIME_RISK_OFF_GRID),
    ]
    verdict = plateau_check(points, axes, tolerance=0.85)

    print("=" * 72)
    label = (
        "PLATEAU  (04 §4 ACCEPTED)"
        if verdict.has_plateau
        else "SPIKE — REJECTED (04 §4)"
    )
    print(f"  PLATEAU VERDICT:  {label}")
    print("=" * 72)
    print(f"  {verdict.explanation}")

    # Floor baseline comparison (debounce=3, risk_off=0.0 = the T1 floor config)
    floor_pt = next(
        (
            p
            for p in points
            if p.params["debounce_days"] == 3 and p.params["risk_off_floor"] == 0.0
        ),
        None,
    )
    if floor_pt:
        winner = verdict.winner
        print()
        print("  Floor config on DISCOVERY (debounce=3, risk_off=0.0):")
        print(
            f"    calmar={floor_pt.calmar:.3f}  sharpe={floor_pt.sharpe:.3f}"
            f"  cagr={floor_pt.cagr * 100:.2f}%"
        )
        if winner.trial_id != floor_pt.trial_id:
            delta_pct = (winner.calmar / floor_pt.calmar - 1) * 100
            print(
                f"  Winner vs floor: calmar {winner.calmar:.3f} vs {floor_pt.calmar:.3f}"
                f"  ({delta_pct:+.1f}%)"
            )
        else:
            print("  Floor config IS the winner — regime defaults are already optimal.")

    print()
    print(f"  Total trials in ledger: K = {ledger.n_trials}")
    print("  (K feeds deflated_sharpe in T4/T5 — report raw Sharpe and K together.)")

    print()
    if not verdict.has_plateau:
        print("  LAYER 1 RESULT: NO parameter change accepted.")
        print("  Retain floor regime config (debounce=3, risk_off=0.0) for T4.")
    else:
        w = verdict.winner
        print(f"  LAYER 1 RESULT: Accepted — {w.params}  calmar={w.calmar:.3f}")
        print("  Proceed to T4 robustness checks with this regime config.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
