"""
fundamentals.ca_consistency — TB6: corporate-action consistency with the price layer (§3.6).

CONVENTION (fixed here; factors in 03_TRACK_B_PREREG must follow this):
──────────────────────────────────────────────────────────────────────────
The v2 price layer stores two price columns per trading day:

    close        split+bonus back-adjusted signal price  (adj_factor × close_raw)
    close_raw    unadjusted traded close; retained for audit
    adj_factor   cumulative back-adjustment factor — latest date = 1.0,
                 earlier dates < 1.0 wherever a split/bonus occurred

The XBRL fundamentals layer stores ``shares_outstanding`` as the raw share
count reported in the filing (pre-adjusted basis).  At a 2:1 split:

    pre-split:  adj_factor = 0.5, close = 500, close_raw = 1000, shares = N
    post-split: adj_factor = 1.0, close = 500, close_raw = 500,  shares = 2N

Naïve ``market_cap = close × shares`` gives:
    pre:  500 × N   = 500N
    post: 500 × 2N  = 1000N   ← artificial ×2 jump — WRONG

CHOSEN CONVENTION — Raw × Raw:
──────────────────────────────
    market_cap(D) = close_raw(D) × shares_outstanding_from_snapshot(D)

Both quantities are on the raw (unadjusted) basis for any given date, so the
product is continuous across split/bonus events.

    pre:  1000 × N  = 1000N ✓
    post:  500 × 2N = 1000N ✓  (continuous)

For book-to-price the same price denominator applies:

    book_to_price(D) = total_equity / (close_raw(D) × shares_outstanding)

``total_equity`` is a monetary total (₹) — not per-share — so it is already
continuous across splits; no adjustment needed.

WHAT NOT TO DO:
    ✗  market_cap = close × shares_outstanding       (adjusted price, raw shares → jump)
    ✗  market_cap = close_tr × shares_outstanding    (total-return price, same problem)

MISMATCH DETECTION:
For each ISIN, an ``adj_factor`` step at a known CA ex_date implies an expected
shares multiplier (step_ratio = adj_factor_post / adj_factor_pre ≈ 2.0 for 2:1).
``reconcile_ca_consistency`` compares the XBRL shares straddling each event
against the expected multiplier and surfaces any divergence (Rule 12).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd
from sqlalchemy.orm import Session

from app.fundamentals.data_config import RECON_TOLERANCE
from app.fundamentals.reader import read_fundamentals_asof

# ── Seam type ────────────────────────────────────────────────────────────────
# (isin, start_date, end_date) -> DataFrame with columns: date, close_raw, adj_factor
PriceReader = Callable[[str, datetime.date, datetime.date], pd.DataFrame]

# Minimum adj_factor step magnitude to treat as a split/bonus event.
# Filters out floating-point drift and tiny dividend-only factor changes.
_MIN_STEP = 0.05


# ── Public helpers — the only sanctioned computation paths for 03 factors ────


def market_cap_raw(close_raw: float, shares_outstanding: float) -> float:
    """Market cap using the raw × raw convention (§TB6).

    Both inputs are unadjusted: close_raw from the price layer, shares_outstanding
    from the most recent qualifying XBRL snapshot.  This product is continuous
    across split/bonus events.
    """
    return close_raw * shares_outstanding


def book_to_price_raw(
    total_equity: float | None,
    close_raw: float | None,
    shares_outstanding: float | None,
) -> float | None:
    """Book-to-price using the raw × raw convention (§TB6).

    total_equity is a monetary total (₹), not per-share — already continuous
    across splits.  Returns None when any input is None or market cap is zero.
    """
    if total_equity is None or close_raw is None or shares_outstanding is None:
        return None
    mc = close_raw * shares_outstanding
    if mc == 0.0:
        return None
    return total_equity / mc


# ── Mismatch detection ───────────────────────────────────────────────────────


@dataclass
class CaMismatch:
    isin: str
    ex_date: datetime.date
    # step_ratio: adj_factor[post] / adj_factor[pre] (e.g. 2.0 for a 2:1 split)
    step_ratio: float
    # shares ratio observed in XBRL: shares_after / shares_before
    shares_ratio_observed: float | None
    # expected = step_ratio (e.g. 2.0 shares should double for a 2:1 split)
    shares_ratio_expected: float
    detail: str


@dataclass
class CaConsistencyReport:
    # ISINs with no CA events, or where all events reconcile within tolerance.
    ok_isins: list[str] = field(default_factory=list)
    # ISINs skipped — no price data or no XBRL snapshots to compare against.
    skipped_isins: list[str] = field(default_factory=list)
    # ISINs with at least one adj_factor / shares_outstanding divergence.
    mismatches: list[CaMismatch] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.mismatches) == 0


def _adj_factor_steps(prices: pd.DataFrame) -> list[tuple[datetime.date, float]]:
    """Return (ex_date, step_ratio) for each significant adj_factor step.

    step_ratio = adj_factor_post / adj_factor_pre (> 1.0 means shares increased:
    split or bonus).  Sorted chronologically.  Ignores steps ≤ _MIN_STEP.
    """
    df = prices.sort_values("date").reset_index(drop=True)
    if "adj_factor" not in df.columns or len(df) < 2:
        return []

    af = df["adj_factor"].to_numpy(dtype="float64")
    dates = [d.date() if hasattr(d, "date") else d for d in df["date"].tolist()]
    steps: list[tuple[datetime.date, float]] = []
    for i in range(1, len(af)):
        if af[i - 1] > 0 and af[i] > 0:
            ratio = af[i] / af[i - 1]
            if abs(ratio - 1.0) > _MIN_STEP:
                steps.append((dates[i], ratio))
    return steps


def _shares_straddling(
    session: Session,
    isin: str,
    ex_date: datetime.date,
) -> tuple[float | None, float | None]:
    """Return (shares_before, shares_after) relative to the CA ex_date.

    shares_before: from the most recent qualifying XBRL snapshot as of ex_date.
    shares_after:  from the first XBRL snapshot with a later period_end,
                   visible 400 calendar days after ex_date (next annual filing).
    Returns (None, None) when fundamentals data is unavailable.
    """
    before_snaps = read_fundamentals_asof(session, isin, ex_date)
    if not before_snaps:
        return None, None
    # read_fundamentals_asof returns descending period_end; first = most recent.
    before_snap = before_snaps[0]

    after_date = ex_date + datetime.timedelta(days=400)
    after_snaps = read_fundamentals_asof(session, isin, after_date)
    shares_after: float | None = None
    for snap in after_snaps:
        if snap.period_end > before_snap.period_end:
            shares_after = snap.shares_outstanding
            break

    return before_snap.shares_outstanding, shares_after


def reconcile_ca_consistency(
    session: Session,
    price_reader: PriceReader,
    isin_list: list[str],
    start: datetime.date,
    end: datetime.date,
) -> CaConsistencyReport:
    """Check shares_outstanding consistency with the price layer's adj_factor steps.

    For each ISIN in ``isin_list``:
    1. Read the price layer in [start, end] via ``price_reader`` (injectable seam).
    2. Detect adj_factor steps > _MIN_STEP (split/bonus events).
    3. For each event, compare XBRL shares straddling the ex_date to the expected
       multiplier implied by the adj_factor step.
    4. Surface any divergence beyond RECON_TOLERANCE (Rule 12 — never silent).

    ISINs with no price data, no CA events, or no XBRL snapshots to compare are
    recorded in ``skipped_isins`` (they cannot be checked, not that they're ok).
    ISINs where every event reconciles within tolerance are added to ``ok_isins``.
    """
    report = CaConsistencyReport()

    for isin in isin_list:
        prices = price_reader(isin, start, end)
        if prices.empty or "adj_factor" not in prices.columns:
            report.skipped_isins.append(isin)
            continue

        steps = _adj_factor_steps(prices)
        if not steps:
            report.ok_isins.append(isin)
            continue

        isin_mismatches: list[CaMismatch] = []
        any_skipped = False

        for ex_date, step_ratio in steps:
            shares_before, shares_after = _shares_straddling(session, isin, ex_date)

            if shares_before is None or shares_after is None:
                any_skipped = True
                continue

            observed = shares_after / shares_before if shares_before != 0 else None
            if observed is None:
                any_skipped = True
                continue

            expected = step_ratio
            relative_err = (
                abs(observed - expected) / expected if expected != 0 else float("inf")
            )
            if relative_err > RECON_TOLERANCE:
                isin_mismatches.append(
                    CaMismatch(
                        isin=isin,
                        ex_date=ex_date,
                        step_ratio=step_ratio,
                        shares_ratio_observed=observed,
                        shares_ratio_expected=expected,
                        detail=(
                            f"adj_factor step implies ×{expected:.3f} shares; "
                            f"XBRL shows ×{observed:.3f} "
                            f"(err={relative_err:.1%} > tolerance={RECON_TOLERANCE:.1%})"
                        ),
                    )
                )

        if isin_mismatches:
            report.mismatches.extend(isin_mismatches)
        elif any_skipped:
            report.skipped_isins.append(isin)
        else:
            report.ok_isins.append(isin)

    return report
