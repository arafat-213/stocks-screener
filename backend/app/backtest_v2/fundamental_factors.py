"""
fundamental_factors.py — TBE1: 5 value/quality factors for Track B (03 §3/§4).

Reads exclusively through read_fundamentals_asof (TB5 — the sole sanctioned path).
Market cap via ca_consistency.market_cap_raw / book_to_price_raw (TB6 raw×raw).
No ORM import; no zero-fill; no winsorization (ranks are scale-free).

Sign convention: every factor is oriented so HIGHER = BETTER after the sign,
matching factors.py convention and enabling a uniform percentile rank-blend.

  earnings_yield  E/P  = TTM net_income / market_cap_raw      higher = cheaper = better
  book_to_price   B/P  = book_to_price_raw(...)                higher = cheaper = better
  roe             Q1   = TTM net_income / avg(total_equity)    higher = more profitable = better
  accruals        Q2   = -(TTM net_income − TTM cfo) / assets  higher = more cash-backed = better
  leverage        Q3   = -(total_debt / total_equity)           higher = less levered = better

TTM for flow items (03 §4.2):
  - Sum of 4 most recent "Quarterly" snapshots within _TTM_MAX_SPAN_DAYS.
  - Fallback: latest "Annual" snapshot value.
  - If neither → None (absent, never 0-filled).

Degenerate handling (03 §4.3):
  - total_equity ≤ 0 → B/P and ROE are None.
  - total_assets ≤ 0 → accruals is None.
  - Zero / None market cap → E/P and B/P are None.
  - Negative net_income → E/P and ROE computed as-is (real information).

Financials exclusion (03 §3):
  - ISINs in financial_isins get None for accruals and leverage.
  - Retained for E/P, B/P, ROE.
"""

from __future__ import annotations

import datetime
from typing import Callable

import pandas as pd
from sqlalchemy.orm import Session

from app.backtest_v2.v3_config import FUNDAMENTAL_FACTOR_NAMES
from app.fundamentals.ca_consistency import book_to_price_raw, market_cap_raw
from app.fundamentals.reader import FundamentalsSnapshot, read_fundamentals_asof

# statement_type values from FundamentalsFilingIndex (models.py)
_QUARTERLY_TYPE = "Quarterly"
_ANNUAL_TYPE = "Annual"

# 15 months in days (≈ 15 × 30.44). Guards against irregular quarterly gaps.
_TTM_MAX_SPAN_DAYS = 456

# Seam type for the fundamentals reader (allows mocking in tests per CLAUDE.md §5).
FundamentalsReader = Callable[[Session, str, datetime.date], list[FundamentalsSnapshot]]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ttm_flow(snapshots: list[FundamentalsSnapshot], field: str) -> float | None:
    """TTM flow item (03 §4.2): 4-quarter sum or annual fallback, else None.

    "Clean" requires non-None values for the specific field in all 4 quarters
    and a span ≤ _TTM_MAX_SPAN_DAYS. A NULL value in any quarter is not clean
    → fallback to the latest Annual snapshot.
    """
    quarters = sorted(
        [s for s in snapshots if s.statement_type == _QUARTERLY_TYPE],
        key=lambda s: s.period_end,
        reverse=True,
    )
    if len(quarters) >= 4:
        top4 = quarters[:4]
        span_days = (top4[0].period_end - top4[3].period_end).days
        if span_days <= _TTM_MAX_SPAN_DAYS:
            values = [getattr(s, field) for s in top4]
            if all(v is not None for v in values):
                return float(sum(values))

    # Annual fallback
    annuals = sorted(
        [s for s in snapshots if s.statement_type == _ANNUAL_TYPE],
        key=lambda s: s.period_end,
        reverse=True,
    )
    if annuals:
        val = getattr(annuals[0], field)
        return float(val) if val is not None else None

    return None


def _latest_stock(snapshots: list[FundamentalsSnapshot], field: str) -> float | None:
    """Latest non-None stock item (03 §4.2 — reader already sorts descending)."""
    for snap in snapshots:
        val = getattr(snap, field)
        if val is not None:
            return float(val)
    return None


def _avg_equity_for_roe(snapshots: list[FundamentalsSnapshot]) -> float | None:
    """ROE equity denominator (03 §4.2): avg of latest 2 Annual equity points.

    Falls back to the single latest Annual, then latest any-type, then None.
    Only positive equity is returned (non-positive → None, handled in roe()).
    """
    annuals = sorted(
        [
            s
            for s in snapshots
            if s.statement_type == _ANNUAL_TYPE and s.total_equity is not None
        ],
        key=lambda s: s.period_end,
        reverse=True,
    )
    if len(annuals) >= 2:
        return (annuals[0].total_equity + annuals[1].total_equity) / 2.0  # type: ignore[operator]
    if len(annuals) == 1:
        return float(annuals[0].total_equity)  # type: ignore[arg-type]
    # No Annual equity found — latest from any statement type
    return _latest_stock(snapshots, "total_equity")


# ---------------------------------------------------------------------------
# Per-ISIN factor functions (pure, no DB — take snapshots + close_raw)
# ---------------------------------------------------------------------------


def earnings_yield(
    snapshots: list[FundamentalsSnapshot],
    close_raw: float,
) -> float | None:
    """E/P = TTM net_income / market_cap_raw. Higher = cheaper. (03 §3 V1)

    Negative net_income is computed as-is (real information, not a degenerate case).
    None when market cap is zero/None, or TTM net_income is unavailable.
    """
    shares = _latest_stock(snapshots, "shares_outstanding")
    if shares is None or shares <= 0.0:
        return None
    mc = market_cap_raw(close_raw, shares)
    if mc <= 0.0:
        return None
    ttm_ni = _ttm_flow(snapshots, "net_income")
    if ttm_ni is None:
        return None
    return ttm_ni / mc


def book_to_price(
    snapshots: list[FundamentalsSnapshot],
    close_raw: float,
) -> float | None:
    """B/P = total_equity / market_cap_raw. Higher = cheaper. (03 §3 V2)

    Non-positive equity → None (03 §4.3). Uses the TB6 raw×raw helper.
    """
    equity = _latest_stock(snapshots, "total_equity")
    if equity is None or equity <= 0.0:
        return None
    shares = _latest_stock(snapshots, "shares_outstanding")
    # book_to_price_raw handles None shares / zero market cap → None
    return book_to_price_raw(equity, close_raw, shares)


def roe(snapshots: list[FundamentalsSnapshot]) -> float | None:
    """ROE = TTM net_income / avg(total_equity). Higher = more profitable. (03 §3 Q1)

    Non-positive equity → None (03 §4.3). Uses latest-two-annual avg.
    """
    ttm_ni = _ttm_flow(snapshots, "net_income")
    if ttm_ni is None:
        return None
    avg_eq = _avg_equity_for_roe(snapshots)
    if avg_eq is None or avg_eq <= 0.0:
        return None
    return ttm_ni / avg_eq


def accruals(
    snapshots: list[FundamentalsSnapshot],
    is_financial: bool,
) -> float | None:
    """Accruals = −(TTM NI − TTM CFO) / total_assets. Higher = more cash-backed. (03 §3 Q2)

    Sign-flipped so lower accruals → higher percentile rank → better.
    Financials excluded (03 §3). Zero/negative assets → None (03 §4.3).
    """
    if is_financial:
        return None
    assets = _latest_stock(snapshots, "total_assets")
    if assets is None or assets <= 0.0:
        return None
    ttm_ni = _ttm_flow(snapshots, "net_income")
    ttm_cfo = _ttm_flow(snapshots, "cfo")
    if ttm_ni is None or ttm_cfo is None:
        return None
    return -(ttm_ni - ttm_cfo) / assets


def leverage(
    snapshots: list[FundamentalsSnapshot],
    is_financial: bool,
) -> float | None:
    """Leverage = −(total_debt / total_equity). Higher = less levered. (03 §3 Q3)

    Sign-flipped so lower leverage → higher rank → better.
    Financials excluded (03 §3). Non-positive equity → None (03 §4.3).

    TBE5b fallback: if total_debt is absent but the filing discloses
    DebtEquityRatio, use −DebtEquityRatio directly (mathematically equivalent).
    A negative disclosed ratio implies a filing error → None (not zero-filled).
    """
    if is_financial:
        return None
    equity = _latest_stock(snapshots, "total_equity")
    if equity is None or equity <= 0.0:
        return None
    debt = _latest_stock(snapshots, "total_debt")
    if debt is not None:
        return -(debt / equity)
    # Fallback: disclosed D/E ratio from results-only filings.
    de_ratio = _latest_stock(snapshots, "debt_equity_ratio")
    if de_ratio is not None and de_ratio >= 0.0:
        return -de_ratio
    return None


# ---------------------------------------------------------------------------
# Dispatcher: name → factor value for one (isin, date) cell
# ---------------------------------------------------------------------------


def _compute_one(
    name: str,
    snapshots: list[FundamentalsSnapshot],
    close_raw: float | None,
    is_financial: bool,
) -> float | None:
    if name == "earnings_yield":
        if close_raw is None:
            return None
        return earnings_yield(snapshots, close_raw)
    if name == "book_to_price":
        if close_raw is None:
            return None
        return book_to_price(snapshots, close_raw)
    if name == "roe":
        return roe(snapshots)
    if name == "accruals":
        return accruals(snapshots, is_financial)
    if name == "leverage":
        return leverage(snapshots, is_financial)
    raise ValueError(
        f"Unknown fundamental factor: {name!r}. Known: {sorted(FUNDAMENTAL_FACTOR_NAMES)}"
    )


# ---------------------------------------------------------------------------
# Frame builder: (name, session, prices) → wide raw-value DataFrame
# ---------------------------------------------------------------------------


def compute_fundamental_factor_frame(
    name: str,
    session: Session,
    prices: pd.DataFrame,
    rebalance_dates: list[datetime.date],
    financial_isins: frozenset[str] = frozenset(),
    *,
    reader: FundamentalsReader = read_fundamentals_asof,
) -> pd.DataFrame:
    """Build a wide (date × isin) raw factor-value frame for one fundamental factor.

    For each (rebalance_date, isin): reads snapshots via the injected reader
    (default: read_fundamentals_asof, TB5 PIT-correct path) and computes the
    factor value. Returns NaN where the factor cannot be computed.

    Args:
        name: one of FUNDAMENTAL_FACTOR_NAMES.
        session: SQLAlchemy session (passed to the reader).
        prices: long-format prices DataFrame with columns isin, date, close_raw.
        rebalance_dates: list of as-of dates to compute on.
        financial_isins: ISINs to exclude from accruals / leverage (03 §3).
        reader: injectable seam for unit tests (replaces read_fundamentals_asof).

    Returns:
        DataFrame indexed by pd.Timestamp(rebalance_dates), columns = ISINs.
        Missing values are NaN (never 0 — TB4 invariant).
    """
    if name not in FUNDAMENTAL_FACTOR_NAMES:
        raise ValueError(
            f"Unknown fundamental factor: {name!r}. "
            f"Known: {sorted(FUNDAMENTAL_FACTOR_NAMES)}"
        )

    all_isins: list[str] = sorted(prices["isin"].unique().tolist())

    # Build close_raw lookup: Timestamp → {isin → float}
    close_raw_map: dict[pd.Timestamp, dict[str, float]] = {}
    for row in prices[["isin", "date", "close_raw"]].itertuples(index=False):
        ts = pd.Timestamp(row.date)
        cr = row.close_raw
        if cr is not None and not (cr != cr):  # not NaN
            if ts not in close_raw_map:
                close_raw_map[ts] = {}
            close_raw_map[ts][row.isin] = float(cr)

    records: dict[pd.Timestamp, dict[str, float | None]] = {}
    for d in rebalance_dates:
        ts = pd.Timestamp(d)
        daily_cr = close_raw_map.get(ts, {})
        row_vals: dict[str, float | None] = {}
        for isin in all_isins:
            snaps = reader(session, isin, d)
            cr = daily_cr.get(isin)
            is_fin = isin in financial_isins
            row_vals[isin] = _compute_one(name, snaps, cr, is_fin)
        records[ts] = row_vals

    return pd.DataFrame.from_dict(records, orient="index", columns=all_isins)
