"""
run_real.py — end-to-end v2 simulation-core run on the REAL spec-01 dataset.

This is the spec-02 module exit-criteria harness (see
`specs/v2/02_SIMULATION_CORE_TASKS.md` → "Exit criteria for the whole
Simulation Core"). It is NOT a unit test: it depends on the built bhavcopy
parquet dataset (`backend/data/bhavcopy/`, ~505M) and so must stay out of the
offline pytest suite (CLAUDE.md Rule 5 — tests don't touch the big real data).

What it does:
  1. Loads adjusted prices for the full dataset range via `store`.
  2. Builds an INJECTED **synthetic** broad-market price index for the regime
     overlay.  This is a deliberate placeholder: the real Nifty200 Momentum 30
     TRI loader is spec 03 (`03_COST_AND_BENCHMARK.md`).  The seam is the
     `index_prices=` parameter on `engine.run`, so swapping the real series in
     is a one-line change (Rule 12 — flagged, not pretend-real).
  3. Runs the engine with the placeholder cost model (also a spec-03 seam).
  4. Computes daily-MTM metrics and prints the summary.
  5. Asserts the three real-data invariants the exit criteria require:
       - cash conservation every day + total cost == Σ per-fill costs
       - determinism (same config + data → identical equity curve)
       - no-lookahead (corrupting post-cutoff rows leaves pre-cutoff curve identical)
     Fails loud (non-zero exit) on any violation.

Run:
    backend/venv/bin/python -m app.backtest_v2.run_real
"""

from __future__ import annotations

import sys
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2 import engine, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.signals import precompute_signals
from app.data.bhavcopy import store

# Daily return clip for the synthetic index proxy: the survivorship-free
# universe contains microcaps with absurd single-day moves; clip so a handful
# of names cannot dominate the broad-market level the regime 200-DMA reads.
_INDEX_RET_CLIP = 0.20
# Only reasonably liquid names contribute to the synthetic index proxy.
_INDEX_LIQ_FLOOR_RUPEES = 5e7  # ₹5 crore adv_20


def build_synthetic_index(prices: pd.DataFrame) -> pd.Series:
    """
    Build a synthetic broad-market PRICE index from the dataset itself.

    PLACEHOLDER for spec 03's real benchmark loader.  Method: equal-weighted
    cross-sectional mean of daily `close` returns across liquid names each day,
    clipped to ±20% to suppress microcap noise, cumulated to a level starting
    at 100.  Uses `close` (split/bonus-adjusted, ex-dividend) — a price index,
    not total-return — which is what the regime overlay's 200-DMA expects.

    Returns a pd.Series indexed by trading date (UTC-naive Timestamp).
    """
    liquid = prices[prices["adv_20"] >= _INDEX_LIQ_FLOOR_RUPEES].copy()
    liquid = liquid.sort_values(["isin", "date"])
    # per-ISIN daily return on adjusted close
    liquid["ret"] = liquid.groupby("isin")["close"].pct_change()
    liquid["ret"] = liquid["ret"].clip(-_INDEX_RET_CLIP, _INDEX_RET_CLIP)
    # cross-sectional equal-weighted mean return per date
    daily = liquid.groupby("date")["ret"].mean().sort_index()
    daily = daily.fillna(0.0)
    level = 100.0 * (1.0 + daily).cumprod()
    level.index = pd.to_datetime(level.index)
    return level


def _equity_array(result: engine.EngineResult) -> np.ndarray:
    return np.array([s.equity for s in result.snapshots], dtype=float)


def check_cash_conservation(result: engine.EngineResult) -> list[str]:
    """equity == cash + invested_value every day; total cost == Σ per-fill cost."""
    errs: list[str] = []
    for s in result.snapshots:
        recomposed = s.cash + s.invested_value
        if abs(s.equity - recomposed) > 1e-6 * max(1.0, abs(s.equity)):
            errs.append(
                f"cash-conservation broken on {s.date}: "
                f"equity={s.equity:.6f} != cash+invested={recomposed:.6f}"
            )
            break
    sum_fill_costs = sum(f.cost_rupees for f in result.fills_log)
    if abs(result.total_cost_paid - sum_fill_costs) > 1e-3:
        errs.append(
            f"cost mismatch: total_cost_paid={result.total_cost_paid:.4f} "
            f"!= Σ per-fill cost={sum_fill_costs:.4f}"
        )
    return errs


def check_determinism(
    prices: pd.DataFrame,
    config: MomentumConfig,
    index_prices: pd.Series,
    first_equity: np.ndarray,
) -> list[str]:
    """Re-run identically; equity curve must be byte-identical."""
    rerun = engine.run(prices, config, index_prices=index_prices)
    second = _equity_array(rerun)
    if first_equity.shape != second.shape:
        return [
            f"determinism broken: curve length differs "
            f"({first_equity.shape} vs {second.shape})"
        ]
    if not np.array_equal(first_equity, second):
        diff = int(np.sum(first_equity != second))
        return [f"determinism broken: {diff} equity points differ on identical re-run"]
    return []


def check_no_lookahead(
    prices: pd.DataFrame,
    config: MomentumConfig,
    index_prices: pd.Series,
    baseline_equity: np.ndarray,
    cutoff: pd.Timestamp,
) -> list[str]:
    """
    Corrupt every price row strictly AFTER `cutoff` (multiply by 5, etc.) and
    rerun.  Decisions/fills up to `cutoff` use only data ≤ decision date and
    fill at the next open, so the equity curve up to `cutoff` must be unchanged.
    """
    corrupt = prices.copy()
    mask = corrupt["date"] > cutoff
    if mask.sum() == 0:
        return [f"no-lookahead test ineffective: no rows after cutoff {cutoff.date()}"]
    for col in ("open", "high", "low", "close", "close_tr"):
        corrupt.loc[mask, col] = corrupt.loc[mask, col] * 5.0
    corrupt.loc[mask, "adv_20"] = corrupt.loc[mask, "adv_20"] * 5.0

    # Corrupt the injected index after the cutoff too (regime must not peek).
    corrupt_index = index_prices.copy()
    corrupt_index.loc[corrupt_index.index > cutoff] *= 5.0

    rerun = engine.run(corrupt, config, index_prices=corrupt_index)
    corrupt_equity = _equity_array(rerun)

    # Compare the prefix up to and including the cutoff date.
    base_dates = [s.date for s in _SNAPSHOT_DATES_HOLDER]
    cutoff_d = cutoff.date()
    n_prefix = sum(1 for d in base_dates if d <= cutoff_d)
    if n_prefix < 2:
        return [f"no-lookahead test ineffective: only {n_prefix} pre-cutoff days"]
    if len(corrupt_equity) < n_prefix:
        return ["no-lookahead broken: corrupt run produced fewer snapshots"]

    base_prefix = baseline_equity[:n_prefix]
    corrupt_prefix = corrupt_equity[:n_prefix]
    if not np.array_equal(base_prefix, corrupt_prefix):
        diff = int(np.sum(base_prefix != corrupt_prefix))
        first_bad = int(np.argmax(base_prefix != corrupt_prefix))
        return [
            f"no-lookahead broken: {diff}/{n_prefix} pre-cutoff equity points "
            f"changed when post-cutoff data was corrupted "
            f"(first divergence at index {first_bad}, date {base_dates[first_bad]})"
        ]
    return []


# Module-level holder so check_no_lookahead can see the baseline snapshot dates
# without re-threading them through every signature.
_SNAPSHOT_DATES_HOLDER: list = []


def main() -> int:
    print("Loading real spec-01 dataset (prices_adjusted) ...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print(
            "FAIL: prices_adjusted is empty — the spec-01 dataset is not built. "
            "Build the data layer first (see 01_DATA_LAYER).",
            file=sys.stderr,
        )
        return 2

    prices["date"] = pd.to_datetime(prices["date"])
    n_isins = prices["isin"].nunique()
    d_min, d_max = prices["date"].min(), prices["date"].max()
    print(
        f"  rows={len(prices):,}  ISINs={n_isins:,}  "
        f"range={d_min.date()} → {d_max.date()}",
        flush=True,
    )

    config = MomentumConfig(
        date_from=date(2017, 1, 1),
        date_to=d_max.date(),
    )

    print(
        "Building synthetic market index (regime overlay placeholder) ...", flush=True
    )
    index_prices = build_synthetic_index(prices)
    print(
        f"  index points={len(index_prices):,}  "
        f"level {index_prices.iloc[0]:.1f} → {index_prices.iloc[-1]:.1f}",
        flush=True,
    )

    print("Precomputing signals (per-ISIN indicators) ...", flush=True)
    signal_store = precompute_signals(prices, config)

    print(
        "Running engine (placeholder costs, injected synthetic index) ...", flush=True
    )
    result = engine.run(
        prices,
        config,
        index_prices=index_prices,
        signal_store=signal_store,
    )

    baseline_equity = _equity_array(result)
    _SNAPSHOT_DATES_HOLDER.clear()
    _SNAPSHOT_DATES_HOLDER.extend(result.snapshots)

    print()
    print(metrics.summary(metrics.compute_metrics(result)))
    print()
    print(
        f"  Snapshots       : {len(result.snapshots):,}\n"
        f"  Fills logged    : {len(result.fills_log):,}\n"
        f"  Rebalances      : {len(result.rebalance_dates_used)}\n"
        f"  Suspensions     : {len(result.suspension_log)} names flagged"
    )
    print()

    # ---- Invariant checks (fail loud) --------------------------------------
    print("=== Real-data invariant checks ===", flush=True)
    all_errs: list[str] = []

    cc = check_cash_conservation(result)
    print(f"  [{'PASS' if not cc else 'FAIL'}] cash conservation + cost accounting")
    all_errs += cc

    det = check_determinism(prices, config, index_prices, baseline_equity)
    print(f"  [{'PASS' if not det else 'FAIL'}] determinism (identical re-run)")
    all_errs += det

    # Cutoff ~2 years before the end so there is a substantial pre-cutoff prefix
    # AND meaningful post-cutoff data to corrupt.
    cutoff = pd.Timestamp(d_max) - pd.DateOffset(years=2)
    la = check_no_lookahead(prices, config, index_prices, baseline_equity, cutoff)
    print(f"  [{'PASS' if not la else 'FAIL'}] no-lookahead (cutoff {cutoff.date()})")
    all_errs += la

    print()
    if all_errs:
        print("EXIT-CRITERIA CHECK FAILED:", file=sys.stderr)
        for e in all_errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("All real-data exit-criteria invariants hold. ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
