"""
fundamentals.reader — TB5: as-of reader (chokepoint API + restatement read-side, §3.4).

This is the **sole sanctioned read path** for fundamentals line items.  No factor or
downstream module should import ``FundamentalsLineItemVersion`` directly — all reads
must flow through ``read_fundamentals_asof``.

PIT contract
------------
``read_fundamentals_asof(session, isin, D)`` returns the line-item versions available
as of date ``D``, one entry per ``period_end`` (restatement read-side: the latest
version with ``available_date ≤ D − lag``).

``lag = SAFETY_LAG_TRADING_DAYS`` (TB0-locked §8.4 constant = 2 trading days).  The
cutoff is computed as ``D`` minus ``lag`` business days via ``numpy.busday_offset``
(Mon–Fri weekdays; no Indian-holiday calendar — the locked 2-day buffer absorbs any
edge cases here).

A figure filed on ``D`` itself is excluded until ``D + lag`` — the look-ahead guard.
A ``D`` before the first filing returns an empty list, never a guess.

Both invariants are tested in ``tests/unit/test_fundamentals_reader.py``.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.fundamentals.data_config import SAFETY_LAG_TRADING_DAYS
from app.fundamentals.models import FundamentalsLineItemVersion


@dataclass(frozen=True)
class FundamentalsSnapshot:
    """One period's standardized line items as known on a given as-of date."""

    isin: str
    period_end: datetime.date
    # The version's public available_date that qualified (i.e. ≤ D − lag).
    available_date: datetime.date
    statement_type: str | None

    revenue: float | None
    net_income: float | None
    ebit: float | None
    total_equity: float | None
    total_assets: float | None
    total_debt: float | None
    shares_outstanding: float | None
    cfo: float | None
    # TBE5b: disclosed D/E ratio from results-only filings (leverage fallback).
    debt_equity_ratio: float | None


def _cutoff(as_of_date: datetime.date) -> datetime.date:
    """Return the latest available_date that qualifies for as_of_date.

    cutoff = as_of_date − SAFETY_LAG_TRADING_DAYS business days.
    A filing with available_date == cutoff is **included** (≤ not <).
    A filing with available_date == as_of_date is **excluded** when lag ≥ 1.
    """
    # numpy.busday_offset returns numpy.datetime64; .astype("O") gives a Python date.
    result = np.busday_offset(as_of_date, -SAFETY_LAG_TRADING_DAYS).astype("O")
    return result  # type: ignore[return-value]


def _to_snapshot(row: FundamentalsLineItemVersion) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        isin=row.isin,
        period_end=row.period_end,
        available_date=row.available_date,
        statement_type=row.statement_type,
        revenue=row.revenue,
        net_income=row.net_income,
        ebit=row.ebit,
        total_equity=row.total_equity,
        total_assets=row.total_assets,
        total_debt=row.total_debt,
        shares_outstanding=row.shares_outstanding,
        cfo=row.cfo,
        debt_equity_ratio=row.debt_equity_ratio,
    )


def read_fundamentals_asof(
    session: Session,
    isin: str,
    as_of_date: datetime.date,
) -> list[FundamentalsSnapshot]:
    """Return all periods available as of ``as_of_date``, one per ``period_end``.

    Restatement read-side (§3.4): for each ``period_end`` with multiple restated
    versions, the latest ``available_date ≤ D − lag`` wins.  The original version is
    never returned in place of a later restatement (as long as both qualify).

    Results are ordered by ``period_end`` descending (most recent period first) so
    callers building TTM windows can slice from the head.

    Returns an empty list if no qualifying rows exist — never a guess or a
    future-filed figure.

    This is the **only** sanctioned read path. Factors in ``03_TRACK_B_PREREG``
    import this function; they must not access ``FundamentalsLineItemVersion`` directly.
    """
    cutoff = _cutoff(as_of_date)

    rows: list[FundamentalsLineItemVersion] = (
        session.query(FundamentalsLineItemVersion)
        .filter(
            FundamentalsLineItemVersion.isin == isin,
            FundamentalsLineItemVersion.available_date <= cutoff,
        )
        .all()
    )

    if not rows:
        return []

    # Restatement read-side: keep the latest available_date per period_end.
    best: dict[datetime.date, FundamentalsLineItemVersion] = {}
    for row in rows:
        prev = best.get(row.period_end)
        if prev is None or row.available_date > prev.available_date:
            best[row.period_end] = row

    return [
        _to_snapshot(r)
        for r in sorted(best.values(), key=lambda r: r.period_end, reverse=True)
    ]
