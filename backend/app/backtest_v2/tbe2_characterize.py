"""
tbe2_characterize.py — TBE2: Factor characterization on DISCOVERY (coverage + momentum ρ).

Computes:
  1. Per-factor + per-block name coverage across TRACK_B_DISCOVERY rebalances.
  2. Cross-sectional Spearman rank correlation of each value/quality factor (and blocks)
     to mom_12_1 at each rebalance. Expectation (03 §2): |ρ| < 0.3.

This is a REPORT, not a gate. No engine.run, no returns, no FINAL_OOS touched (04 §TBE2).

Run: backend/venv/bin/python -m app.backtest_v2.tbe2_characterize
"""

from __future__ import annotations

import datetime
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats

from app.backtest_v2.engine import _rebalance_dates
from app.backtest_v2.factors import compute_factor
from app.backtest_v2.fundamental_factors import _compute_one
from app.backtest_v2.v3_config import (
    FUNDAMENTAL_FACTOR_NAMES,
    QUALITY_BLOCK,
    TRACK_B_DISCOVERY,
    VALUE_BLOCK,
    V3Config,
)
from app.data.bhavcopy.store import read_prices_adjusted
from app.db.session import SessionLocal
from app.fundamentals.models import FundamentalsLineItemVersion
from app.fundamentals.reader import FundamentalsSnapshot, _cutoff, _to_snapshot

LIQ_FLOOR_CR = 5.0  # ₹ crore, same as V3Config default


# ---------------------------------------------------------------------------
# Bulk-preload reader (avoids N×M individual DB queries — same PIT logic)
# ---------------------------------------------------------------------------


def _build_bulk_cache(
    session,
    isin_set: set[str],
) -> dict[str, list]:
    """Bulk-load all FundamentalsLineItemVersion rows for isin_set into memory.

    Returns dict[isin → list[FundamentalsLineItemVersion]], all rows included;
    the PIT cutoff is applied per-call in _cached_reader, same as the real reader.
    """
    if not isin_set:
        return {}
    isins = list(isin_set)
    # Chunked query to avoid overly long IN clauses
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
        session, isin: str, as_of_date: datetime.date
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
# Core characterization
# ---------------------------------------------------------------------------


def _block_value(
    isin_factor_values: dict[str, dict[str, float | None]],
    isin: str,
    block_factors: frozenset[str],
) -> float | None:
    """Mean of non-None factor values in the block (equal-weight blend, 03 §5)."""
    vals = [
        isin_factor_values[isin][f]
        for f in block_factors
        if isin_factor_values.get(isin, {}).get(f) is not None
    ]
    return float(np.mean(vals)) if vals else None


def run_characterization() -> None:
    print("=== TBE2 — Track-B Factor Characterization ===\n")

    # ------------------------------------------------------------------
    # 1. Load prices for DISCOVERY window
    # ------------------------------------------------------------------
    start, end = TRACK_B_DISCOVERY
    prices = read_prices_adjusted(start=str(start), end=str(end))
    print(f"Prices loaded: {len(prices):,} rows, {start} → {end}")

    calendar = sorted(prices["date"].unique().tolist())
    reb_dates = sorted(_rebalance_dates(calendar, "monthly"))
    print(f"Monthly rebalance dates: {len(reb_dates)}")

    liq_floor = LIQ_FLOOR_CR * 1e7
    fund_factor_names = sorted(FUNDAMENTAL_FACTOR_NAMES)

    # ------------------------------------------------------------------
    # 2. Compute mom_12_1 wide frame (price factor; no DB needed)
    # ------------------------------------------------------------------
    cfg = V3Config(active_factors=["mom_12_1"])
    print("\nComputing mom_12_1 ranks...")
    mom_raw = compute_factor("mom_12_1", prices, cfg)  # wide: date × isin

    # ------------------------------------------------------------------
    # 3. Build liquidity-eligible ISIN set per rebalance date
    # ------------------------------------------------------------------
    eligible_by_date: dict[pd.Timestamp, list[str]] = {}
    price_lookup: dict[pd.Timestamp, pd.DataFrame] = {}
    for d in reb_dates:
        day_df = prices[prices["date"] == d]
        eligible = sorted(
            day_df.loc[
                day_df["adv_20"].notna() & (day_df["adv_20"] >= liq_floor), "isin"
            ]
            .unique()
            .tolist()
        )
        eligible_by_date[d] = eligible
        price_lookup[d] = day_df.set_index("isin")

    all_eligible = set(isin for isins in eligible_by_date.values() for isin in isins)
    print(f"Union of eligible ISINs across all dates: {len(all_eligible):,}")
    print(
        f"Eligible per date — min: {min(len(v) for v in eligible_by_date.values())}, "
        f"max: {max(len(v) for v in eligible_by_date.values())}, "
        f"mean: {np.mean([len(v) for v in eligible_by_date.values()]):.0f}"
    )

    # ------------------------------------------------------------------
    # 4. Bulk-load fundamentals for all eligible ISINs
    # ------------------------------------------------------------------
    session = SessionLocal()
    try:
        print("\nBulk-loading fundamentals from DB...")
        cache = _build_bulk_cache(session, all_eligible)
        reader = _make_cached_reader(cache)
        print(
            f"  Loaded fundamentals for {len(cache):,} ISINs ({sum(len(v) for v in cache.values()):,} rows)"
        )

        # ------------------------------------------------------------------
        # 5. Per-rebalance: compute factor values + coverage + ρ
        # ------------------------------------------------------------------
        # Accumulators
        coverage_records: list[dict] = []  # per (date, factor): coverage fraction
        rho_records: list[dict] = []  # per (date, factor): Spearman ρ

        for d in reb_dates:
            eligible = eligible_by_date[d]
            day_price_df = price_lookup[d]
            d_date = d.date()

            # mom_12_1 values for this date
            mom_row = mom_raw.loc[d] if d in mom_raw.index else pd.Series(dtype=float)

            # For each eligible ISIN: compute all fundamental factor values
            isin_values: dict[str, dict[str, float | None]] = {}
            for isin in eligible:
                snaps = reader(session, isin, d_date)
                cr_row = day_price_df.loc[isin] if isin in day_price_df.index else None
                cr = (
                    float(cr_row["close_raw"])
                    if cr_row is not None and pd.notna(cr_row.get("close_raw"))
                    else None
                )
                vals: dict[str, float | None] = {}
                for fname in fund_factor_names:
                    vals[fname] = _compute_one(fname, snaps, cr, is_financial=False)
                isin_values[isin] = vals

            # Compute block values
            for isin in eligible:
                isin_values[isin]["value_block"] = _block_value(
                    isin_values, isin, VALUE_BLOCK
                )
                isin_values[isin]["quality_block"] = _block_value(
                    isin_values, isin, QUALITY_BLOCK
                )

            all_factors = fund_factor_names + ["value_block", "quality_block"]

            for fname in all_factors:
                # Coverage: fraction of eligible ISINs with non-None value
                n_covered = sum(
                    1 for isin in eligible if isin_values[isin].get(fname) is not None
                )
                cov_frac = n_covered / len(eligible) if eligible else 0.0
                coverage_records.append(
                    {
                        "date": d_date,
                        "factor": fname,
                        "n_eligible": len(eligible),
                        "n_covered": n_covered,
                        "coverage": cov_frac,
                    }
                )

                # Spearman ρ vs mom_12_1: need matched pairs
                paired_mom = []
                paired_fund = []
                for isin in eligible:
                    fval = isin_values[isin].get(fname)
                    mval = mom_row.get(isin, float("nan"))
                    if fval is not None and pd.notna(mval):
                        paired_fund.append(fval)
                        paired_mom.append(mval)

                if len(paired_fund) >= 5:
                    rho, _ = stats.spearmanr(paired_fund, paired_mom)
                else:
                    rho = float("nan")
                rho_records.append(
                    {
                        "date": d_date,
                        "factor": fname,
                        "n_pairs": len(paired_fund),
                        "rho": rho,
                    }
                )

        # ------------------------------------------------------------------
        # 6. Summarise and print the report
        # ------------------------------------------------------------------
        cov_df = pd.DataFrame(coverage_records)
        rho_df = pd.DataFrame(rho_records)

        print("\n" + "=" * 70)
        print(
            "COVERAGE REPORT (fraction of liquidity-eligible names with a usable value)"
        )
        print("=" * 70)
        cov_summary = (
            cov_df.groupby("factor")["coverage"]
            .agg(["mean", "min", "max"])
            .rename(columns={"mean": "mean%", "min": "min%", "max": "max%"})
            .multiply(100)
            .round(1)
        )
        print(cov_summary.to_string())

        print("\n" + "=" * 70)
        print(
            "MOMENTUM RANK-ρ (Spearman, cross-sectional vs mom_12_1; expectation |ρ|<0.3)"
        )
        print("=" * 70)
        rho_summary = (
            rho_df.groupby("factor")["rho"]
            .agg(["mean", "min", "max", lambda x: (x.abs() < 0.3).mean()])
            .rename(
                columns={
                    "mean": "mean_rho",
                    "min": "min_rho",
                    "max": "max_rho",
                    "<lambda_0>": "frac_|ρ|<0.3",
                }
            )
            .round(3)
        )
        print(rho_summary.to_string())

        print("\n" + "=" * 70)
        print("PER-DATE DETAIL (rho by factor)")
        print("=" * 70)
        rho_pivot = rho_df.pivot(index="date", columns="factor", values="rho").round(3)
        print(rho_pivot.to_string())

        print("\n" + "=" * 70)
        print("PER-DATE COVERAGE (% by factor)")
        print("=" * 70)
        cov_pivot = (
            cov_df.pivot(index="date", columns="factor", values="coverage") * 100
        ).round(1)
        print(cov_pivot.to_string())

    finally:
        session.close()


if __name__ == "__main__":
    run_characterization()
