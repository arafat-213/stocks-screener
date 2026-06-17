"""
v3 / T3 acceptance tests — engine rebalance-cadence knob.

All offline: synthetic price frames only, no network / DB / live parquet (Rule 5).

WHY each test group exists:
  generator   — `_rebalance_dates` is the turnover lever #1 (trade less often).
                monthly MUST equal v2's original `_month_end_dates` byte-for-byte
                so v2's MomentumConfig path is unchanged (prereg T3 / Rule 1).
                quarterly/semi-annual must land on exactly the calendar
                quarter-ends ({3,6,9,12}) / half-year-ends ({6,12}).
  engine      — driven through the UNCHANGED `run` via `config.rebalance`:
                monthly default reproduces v2 scheduling; quarterly schedules
                strictly fewer decisions (the lever actually fires — Rule 9 WHY).
  no_lookahead— 02 §10 invariant: a decision on day R executes at the NEXT
                session, never on/before R. Changing cadence must not break the
                next-open queue discipline — every fill has a strictly-earlier
                rebalance date that could have caused it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.engine import (
    EngineResult,
    _month_end_dates,
    _rebalance_dates,
    run,
)

# ---------------------------------------------------------------------------
# Synthetic data builders (column shape mirrors test_t7_engine)
# ---------------------------------------------------------------------------


def _make_prices(
    isins: list[str],
    start: str = "2021-01-04",
    n_days: int = 550,
    seed: int = 11,
    base_price: float = 100.0,
    drift: float = 0.0006,
    vol: float = 0.015,
) -> pd.DataFrame:
    """
    Long-format prices spanning multiple calendar quarters (n_days ≈ 2.2y so
    several quarter-ends and half-year-ends exist). Positive drift + 273-day
    warmup window means the 12-1 momentum gate has real names on late dates.
    adv_20 fixed at ₹10cr so the liquidity floor never gates.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    for k, isin in enumerate(isins):
        name_drift = drift + k * 0.0002  # distinct drift → unambiguous ordering
        price = base_price
        series = []
        for _ in dates:
            price = max(price * (1.0 + rng.normal(name_drift, vol)), 0.01)
            series.append(price)
        for i, (d, p) in enumerate(zip(dates, series)):
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "date": d,
                    "open": p * rng.uniform(0.995, 1.005),
                    "high": p * 1.01,
                    "low": p * 0.99,
                    "close": p,
                    "close_raw": p,
                    "close_tr": p * 1.0005**i,
                    "volume": 100_000,
                    "traded_value": 1e9,
                    "adv_20": 1e8,  # ₹10 crore — always liquid
                    "adj_factor": 1.0,
                    "tr_factor": 1.0005**i,
                    "series": "EQ",
                }
            )
    return pd.DataFrame(rows)


def _calendar(prices: pd.DataFrame) -> list[pd.Timestamp]:
    return sorted(pd.to_datetime(prices["date"].unique()))


def _cfg(**overrides) -> MomentumConfig:
    base = dict(
        target_positions=3,
        sell_rank_buffer=5,
        liquidity_floor_cr=1.0,
        momentum_lookback_days=252,
        momentum_skip_days=21,
        vol_lookback_days=60,
        max_position_pct=40.0,
        starting_capital=1_000_000.0,
        use_regime_overlay=False,
        catastrophic_stop_pct=25.0,
        rebalance="monthly",
        date_from=None,
        date_to=None,
    )
    base.update(overrides)
    return MomentumConfig(**base)


# ---------------------------------------------------------------------------
# Generator — _rebalance_dates correctness
# ---------------------------------------------------------------------------


class TestRebalanceDatesGenerator:
    def test_monthly_is_byte_for_byte_month_end_dates(self):
        """
        The default cadence MUST be identical to v2's original `_month_end_dates`
        — this is what keeps v2's MomentumConfig run byte-for-byte unchanged
        (prereg T3 done-criterion / Rule 1: regression first).
        """
        cal = _calendar(_make_prices([f"ISIN{i:02d}" for i in range(4)]))
        assert _rebalance_dates(cal, "monthly") == _month_end_dates(cal)

    def test_quarterly_is_calendar_quarter_ends(self):
        """Quarterly keeps exactly the month-ends landing on months {3,6,9,12}."""
        cal = _calendar(_make_prices([f"ISIN{i:02d}" for i in range(4)]))
        month_ends = _month_end_dates(cal)
        got = _rebalance_dates(cal, "quarterly")
        expected = {ts for ts in month_ends if ts.month in {3, 6, 9, 12}}
        assert got == expected
        assert {ts.month for ts in got} <= {3, 6, 9, 12}
        assert len(got) > 0  # fixture actually spans quarter-ends

    def test_semi_annual_is_half_year_ends(self):
        """Semi-annual keeps exactly the month-ends on months {6,12}."""
        cal = _calendar(_make_prices([f"ISIN{i:02d}" for i in range(4)]))
        month_ends = _month_end_dates(cal)
        got = _rebalance_dates(cal, "semi-annual")
        expected = {ts for ts in month_ends if ts.month in {6, 12}}
        assert got == expected
        assert {ts.month for ts in got} <= {6, 12}
        assert len(got) > 0

    def test_cadence_nests_and_trades_less_often(self):
        """
        The lever's WHOLE point (Rule 9): coarser cadence = strictly fewer
        rebalances. semi-annual ⊂ quarterly ⊂ monthly.
        """
        cal = _calendar(_make_prices([f"ISIN{i:02d}" for i in range(4)]))
        monthly = _rebalance_dates(cal, "monthly")
        quarterly = _rebalance_dates(cal, "quarterly")
        semi = _rebalance_dates(cal, "semi-annual")
        assert semi < quarterly < monthly  # strict subset (fixture spans >1 of each)
        assert len(semi) < len(quarterly) < len(monthly)

    def test_unknown_cadence_raises(self):
        """Unknown cadence fails loud rather than silently defaulting (Rule 12)."""
        cal = _calendar(_make_prices([f"ISIN{i:02d}" for i in range(2)]))
        with pytest.raises(ValueError, match="unknown rebalance cadence"):
            _rebalance_dates(cal, "weekly")


# ---------------------------------------------------------------------------
# Engine — cadence drives scheduling through the unchanged run()
# ---------------------------------------------------------------------------


class TestEngineCadence:
    def test_monthly_default_unchanged_v2_behavior(self):
        """
        Default-cadence run schedules decisions on exactly v2's month-end days —
        the unchanged-v2 done-criterion, asserted end-to-end through run().
        """
        isins = [f"ISIN{i:02d}" for i in range(6)]
        prices = _make_prices(isins)
        result = run(prices, _cfg())  # rebalance="monthly" (default)

        cal = _calendar(prices)
        used = {pd.Timestamp(d) for d in result.rebalance_dates_used}
        assert used == _month_end_dates(cal)

    def test_quarterly_schedules_only_quarter_ends_and_trades_less(self):
        """
        Quarterly run fires on exactly the quarter-end sessions and strictly
        fewer of them than monthly — the turnover lever demonstrably engaged.
        """
        isins = [f"ISIN{i:02d}" for i in range(6)]
        prices = _make_prices(isins)
        cal = _calendar(prices)

        monthly = run(prices, _cfg(rebalance="monthly"))
        quarterly = run(prices, _cfg(rebalance="quarterly"))

        used = {pd.Timestamp(d) for d in quarterly.rebalance_dates_used}
        assert used == _rebalance_dates(cal, "quarterly")
        assert len(quarterly.rebalance_dates_used) < len(monthly.rebalance_dates_used)


# ---------------------------------------------------------------------------
# No-lookahead — 02 §10 invariant survives the cadence change
# ---------------------------------------------------------------------------


def test_no_lookahead_holds_under_quarterly():
    """
    Queue discipline (02 §10 / DC2): a decision on rebalance day R executes at
    the NEXT session, never on/before R. Every fill must therefore have at least
    one strictly-earlier rebalance date that could have produced it. The cadence
    change only alters WHICH days schedule decisions — the next-open stamping
    must remain intact.
    """
    isins = [f"ISIN{i:02d}" for i in range(6)]
    prices = _make_prices(isins)
    result = run(prices, _cfg(rebalance="quarterly"))

    assert isinstance(result, EngineResult)
    assert len(result.fills_log) > 0  # the run actually traded
    reb_dates = [pd.Timestamp(d) for d in result.rebalance_dates_used]
    for fill in result.fills_log:
        fdate = pd.Timestamp(fill.date)
        assert any(r < fdate for r in reb_dates), (
            f"fill on {fill.date} has no earlier rebalance decision — lookahead"
        )
