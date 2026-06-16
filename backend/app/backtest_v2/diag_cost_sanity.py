"""
diag_cost_sanity.py — Spec 04 §3.1 cost-model preset sanity (READ-ONLY diagnosis).

This changes NO parameter. It runs the SAME pre-committed floor config
(build_floor_config) at the three cost levels and decomposes, per level:

  - final book equity                (book-size mechanism)
  - total_cost_paid  (statutory+DP)  (== the reported "total cost" line)
  - reconstructed slippage rupees    (the component the cost counter omits)
  - true total cost  (statutory+slip)
  - avg statutory bps (cost/notional) (smoking-gun: should be ~equal across levels)

Goal: prove the reported rupee-cost inversion (opt > base > pess) is a
book-size effect on the *statutory-only* slice, not a preset bug, and that the
*true* economic cost is ordered opt < base < pess. Diagnosis only — if a real
bug surfaces, fix it and re-run floor once (same config); otherwise the NO-GO
stands and is not a cost artifact.

Run:
    backend/venv/bin/python -m app.backtest_v2.diag_cost_sanity
"""

from __future__ import annotations

import logging

import pandas as pd

from app.backtest_v2 import benchmark, engine
from app.backtest_v2.costs import CostLevel
from app.backtest_v2.floor import (
    _BENCH_FETCH_END,
    _BENCH_FETCH_START,
    _COST_LEVELS,
    build_floor_config,
)
from app.backtest_v2.signals import precompute_signals
from app.data.bhavcopy import store

# Silence the per-day MTM / dropped-fill warnings (data-quality noise, already
# diagnosed in §3.3) so the decomposition table is the only output.
logging.getLogger("app.backtest_v2.engine").setLevel(logging.ERROR)
logging.getLogger("app.backtest_v2.portfolio").setLevel(logging.ERROR)


def _open_lookup(prices: pd.DataFrame) -> dict[tuple[str, pd.Timestamp], float]:
    """{(isin, date) -> raw open} to reconstruct slippage = qty*|eff_price-open|."""
    out: dict[tuple[str, pd.Timestamp], float] = {}
    for isin, d, o in zip(prices["isin"], prices["date"], prices["open"]):
        out[(isin, pd.Timestamp(d))] = o
    return out


def _decompose(
    result: engine.EngineResult,
    opens: dict[tuple[str, pd.Timestamp], float],
) -> dict[str, float]:
    total_notional = 0.0
    statutory = 0.0
    slippage = 0.0
    n_sells = 0
    for f in result.fills_log:
        notional = f.qty * f.price  # f.price is slippage-adjusted effective price
        total_notional += notional
        statutory += f.cost_rupees  # statutory + DP only
        if f.side in ("sell", "trim"):
            n_sells += 1
        raw_open = opens.get((f.isin, pd.Timestamp(f.date)))
        if raw_open is not None:
            slippage += f.qty * abs(f.price - raw_open)
    final_equity = result.snapshots[-1].equity if result.snapshots else 0.0
    avg_bps = (statutory / total_notional * 10_000.0) if total_notional else 0.0
    return {
        "final_equity": final_equity,
        "total_notional": total_notional,
        "statutory": statutory,
        "slippage": slippage,
        "true_cost": statutory + slippage,
        "avg_stat_bps": avg_bps,
        "n_fills": float(len(result.fills_log)),
        "n_sells": float(n_sells),
    }


def main() -> int:
    config = build_floor_config()
    print("Spec 04 §3.1 — cost-model preset sanity (read-only, same floor config)")
    print(f"  config: {config}\n")

    prices = store.read_prices_adjusted()
    prices["date"] = pd.to_datetime(prices["date"])
    opens = _open_lookup(prices)
    signal_store = precompute_signals(prices, config)

    # Real regime index, exactly as floor.py uses — required to reproduce the
    # floor's actual fills/costs (risk-on default would change every trade).
    index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)

    rows: dict[CostLevel, dict[str, float]] = {}
    for level in _COST_LEVELS:
        print(f"  running {level} ...", flush=True)
        r = engine.run(
            prices,
            config,
            index_prices=index_prices,
            cost_level=level,
            signal_store=signal_store,
        )
        rows[level] = _decompose(r, opens)

    print()
    print("=" * 88)
    print("  COST DECOMPOSITION — same config, 3 cost levels  (₹)")
    print("=" * 88)
    hdr = (
        f"  {'level':<12}{'final_equity':>15}{'notional':>15}"
        f"{'statutory':>12}{'slippage':>12}{'true_cost':>12}{'stat_bps':>10}"
    )
    print(hdr)
    print("  " + "─" * 86)
    for level in _COST_LEVELS:
        d = rows[level]
        print(
            f"  {level:<12}{d['final_equity']:>15,.0f}{d['total_notional']:>15,.0f}"
            f"{d['statutory']:>12,.0f}{d['slippage']:>12,.0f}"
            f"{d['true_cost']:>12,.0f}{d['avg_stat_bps']:>10.2f}"
        )
    print()
    print("  Reads:")
    print("   - 'statutory' == the reported floor 'total cost' (slippage excluded).")
    print("   - inversion is book-size iff avg stat_bps ~equal across levels.")
    print("   - true_cost (statutory+slippage) is the real economic cost ordering.")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
