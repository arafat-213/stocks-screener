"""
vt0_scaffold.py — 09 VT0 step (a): value-block orthogonality reconfirm on DISCOVERY.

Reconfirms the TBE2b finding that the value block (E/P + B/P) is momentum-orthogonal
(|ρ| < 0.3) on the FULL DISCOVERY window, before any value-tilt run (09 §3, §5 Stage 1).
This is the gate that makes the tilt potentially ADDITIVE rather than dilutive (09 §2a):
a small overlay can only add return without adding momentum's own concentration if it
is orthogonal to momentum. Fail loud (non-zero exit) if |ρ| has drifted to >= 0.30 — a
drifted block would invalidate the tilt rationale (Rule 12).

NO BACKTEST, NO FINAL_OOS (VT0 constraint): builds only the momentum composite and the
value_rank frame, then correlates them cell-by-cell on the DISCOVERY rebalance dates.

Reuses the TBE4 bulk-cache fundamentals path (no per-cell DB query) and the 09 §3
momentum base [mom_12_1, low_vol].

Run:
    backend/venv/bin/python -m app.backtest_v2.vt0_scaffold
"""

from __future__ import annotations

import logging
import sys
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2 import factors
from app.backtest_v2.engine import _rebalance_dates
from app.backtest_v2.signals_v3 import build_value_rank
from app.backtest_v2.tbe4_value_block import _build_fund_frames
from app.backtest_v2.v3_config import V3Config
from app.backtest_v2.validation import DISCOVERY
from app.data.bhavcopy import store
from app.db.session import SessionLocal

log = logging.getLogger(__name__)

# 09 §3 momentum base (retention-first, §12.2): price-only 2-factor.
MOMENTUM_BASE_FACTORS = ["mom_12_1", "low_vol"]
ORTHOGONALITY_THRESHOLD = 0.30  # |ρ| must stay below this (TBE2b / 09 §2a)


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    for noisy in (
        "app.backtest_v2",
        "app.core.strategy",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    d_start, d_end = DISCOVERY
    print("=" * 78)
    print("  v3 / VT0 (a) — value-block orthogonality reconfirm on DISCOVERY")
    print(f"  Window:        {d_start} → {d_end}")
    print(f"  Momentum base: {MOMENTUM_BASE_FACTORS}  (09 §3, retention-first)")
    print(f"  Bar:           |ρ| < {ORTHOGONALITY_THRESHOLD}  (TBE2b / 09 §2a)")
    print("=" * 78)

    print("\nLoading prices_adjusted (offline cache)...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}", flush=True)

    # Momentum composite for the 2-factor base on the full daily grid.
    base_cfg = V3Config(
        active_factors=MOMENTUM_BASE_FACTORS, date_from=d_start, date_to=d_end
    )
    print("\nBuilding momentum composite (2-factor base)...", flush=True)
    mom_composite = factors.composite_rank(prices, base_cfg)

    # DISCOVERY monthly rebalance dates (where value frames live).
    disc_prices = prices[
        (prices["date"] >= pd.Timestamp(d_start))
        & (prices["date"] <= pd.Timestamp(d_end))
    ]
    calendar = sorted(disc_prices["date"].unique().tolist())
    rebalance_ts = sorted(_rebalance_dates(calendar, "monthly"))
    rebalance_dates: list[date] = [ts.date() for ts in rebalance_ts]
    print(
        f"  rebalance dates: {len(rebalance_dates)} "
        f"({rebalance_dates[0]} → {rebalance_dates[-1]})",
        flush=True,
    )

    # Value block (E/P, B/P) on DISCOVERY rebalances via the TBE4 bulk-cache path.
    print("\nBuilding value block (E/P, B/P) — bulk-cache fundamentals...", flush=True)
    session = SessionLocal()
    try:
        fund_frames = _build_fund_frames(prices, rebalance_dates, session)
    finally:
        session.close()
    value_rank = build_value_rank(fund_frames)

    # Align momentum composite onto the rebalance dates × value ISINs, then
    # correlate cell-by-cell over names present in BOTH.
    common_cols = mom_composite.columns.intersection(value_rank.columns)
    mom_on_rebal = mom_composite.reindex(index=value_rank.index, columns=common_cols)
    val_on_rebal = value_rank.reindex(columns=common_cols)

    mom_flat = mom_on_rebal.to_numpy().ravel()
    val_flat = val_on_rebal.to_numpy().ravel()
    both = ~(np.isnan(mom_flat) | np.isnan(val_flat))
    n_pairs = int(both.sum())
    if n_pairs < 2:
        print(
            "FAIL: <2 overlapping (momentum, value) cells — cannot correlate.",
            file=sys.stderr,
        )
        return 2
    rho = float(np.corrcoef(mom_flat[both], val_flat[both])[0, 1])

    print("\n" + "=" * 78)
    print("  VT0 (a) RESULT — orthogonality of value block vs momentum composite")
    print("=" * 78)
    print(f"  overlapping cells (both non-NaN): {n_pairs:,}")
    print(f"  Pearson rho(momentum_rank, value_rank): {rho:+.4f}")
    print(f"  |rho| = {abs(rho):.4f}   bar |rho| < {ORTHOGONALITY_THRESHOLD}")

    if abs(rho) >= ORTHOGONALITY_THRESHOLD:
        print(
            f"\n  >>> FAIL — value block DRIFTED: |rho| {abs(rho):.4f} >= "
            f"{ORTHOGONALITY_THRESHOLD}. Tilt rationale (09 §2a) invalidated. <<<"
        )
        print("=" * 78)
        return 1

    print(
        f"\n  >>> PASS — value block momentum-orthogonal (|rho| {abs(rho):.4f} < "
        f"{ORTHOGONALITY_THRESHOLD}). Tilt rationale holds. <<<"
    )
    print("  NO BACKTEST RUN · FINAL_OOS UNTOUCHED (VT0 constraint).")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
