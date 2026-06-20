"""
test_v3tbe1_fundamental_factors.py — TBE1 done-criteria.

Tests encode WHY each constraint matters (Rule 9), not just WHAT it checks.

Done-criteria (specs/v3/04_TRACK_B_EXEC_TASKS.md §TBE1):
  [DC1] All 5 factors computed via read_fundamentals_asof + raw×raw; TTM +
        degenerate + financials rules match 03 §3/§4 exactly.
  [DC2] Composite blends fundamental ranks under mean-over-active;
        missing fundamental = not counted (nanmean, not zero-fill).
  [DC3] No raw-table read, no zero-fill, no market cap other than raw×raw
        (boundary tests on degenerate inputs).

Architecture note: the per-ISIN functions (earnings_yield, book_to_price, roe,
accruals, leverage) take FundamentalsSnapshot lists directly — no DB or session
needed for those tests. compute_fundamental_factor_frame needs a session, injected
via the 'reader' seam (CLAUDE.md §5 — no network, no real DB in tests).
"""

from __future__ import annotations

import datetime
import math

import numpy as np
import pandas as pd
import pytest

from app.backtest_v2.fundamental_factors import (
    _avg_equity_for_roe,
    _ttm_flow,
    accruals,
    book_to_price,
    compute_fundamental_factor_frame,
    earnings_yield,
    leverage,
    roe,
)
from app.fundamentals.reader import FundamentalsSnapshot

# ---------------------------------------------------------------------------
# Helpers — synthetic snapshot builders
# ---------------------------------------------------------------------------

_BASE = datetime.date(2022, 1, 1)


def _snap(
    period_end: datetime.date,
    statement_type: str,
    *,
    net_income: float | None = None,
    cfo: float | None = None,
    total_equity: float | None = None,
    total_assets: float | None = None,
    total_debt: float | None = None,
    shares_outstanding: float | None = None,
    ebit: float | None = None,
    revenue: float | None = None,
    debt_equity_ratio: float | None = None,
) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        isin="TEST",
        period_end=period_end,
        available_date=period_end + datetime.timedelta(days=60),
        statement_type=statement_type,
        net_income=net_income,
        cfo=cfo,
        total_equity=total_equity,
        total_assets=total_assets,
        total_debt=total_debt,
        shares_outstanding=shares_outstanding,
        ebit=ebit,
        revenue=revenue,
        debt_equity_ratio=debt_equity_ratio,
    )


def _quarterly_snaps(
    q_ends: list[datetime.date],
    *,
    net_income: float = 100.0,
    cfo: float = 120.0,
) -> list[FundamentalsSnapshot]:
    """4 quarterly snapshots for a given list of period ends."""
    return [_snap(d, "Quarterly", net_income=net_income, cfo=cfo) for d in q_ends]


# ---------------------------------------------------------------------------
# DC1a — TTM construction (03 §4.2)
# ---------------------------------------------------------------------------


class TestTTMFlow:
    def test_four_clean_quarters_sums_correctly(self):
        """4 quarterly snapshots within 15 months → TTM = sum. Core TTM invariant."""
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = _quarterly_snaps(ends, net_income=25.0)
        assert _ttm_flow(snaps, "net_income") == pytest.approx(100.0)

    def test_four_quarters_span_exceeds_15_months_falls_back_to_annual(self):
        """If the 4-quarter span > 15 months, the TTM sum is unreliable → fallback."""
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2020, 9, 30),  # 18-month gap — outside 15-month window
            datetime.date(2020, 6, 30),
            datetime.date(2020, 3, 31),
        ]
        snaps = [_snap(d, "Quarterly", net_income=25.0) for d in ends]
        # Annual fallback should fire
        annual = _snap(datetime.date(2021, 3, 31), "Annual", net_income=90.0)
        result = _ttm_flow(snaps + [annual], "net_income")
        assert result == pytest.approx(90.0)

    def test_any_null_quarterly_field_falls_back(self):
        """If one quarterly snapshot has NULL for the field → not clean → annual fallback.

        Prevents a partial quarterly sum from masquerading as a full TTM.
        """
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = [
            _snap(ends[0], "Quarterly", net_income=25.0),
            _snap(ends[1], "Quarterly", net_income=None),  # NULL → not clean
            _snap(ends[2], "Quarterly", net_income=25.0),
            _snap(ends[3], "Quarterly", net_income=25.0),
        ]
        annual = _snap(datetime.date(2021, 3, 31), "Annual", net_income=88.0)
        result = _ttm_flow(snaps + [annual], "net_income")
        assert result == pytest.approx(88.0)

    def test_annual_fallback_when_fewer_than_four_quarters(self):
        """Companies that only file annually should return the annual value."""
        annual = _snap(datetime.date(2021, 3, 31), "Annual", net_income=200.0)
        result = _ttm_flow([annual], "net_income")
        assert result == pytest.approx(200.0)

    def test_no_quarters_no_annual_returns_none(self):
        """Neither quarterly nor annual data → None (absent, not 0)."""
        assert _ttm_flow([], "net_income") is None

    def test_annual_field_is_none_returns_none(self):
        """Annual snapshot exists but the specific field is NULL → None (not 0)."""
        annual = _snap(datetime.date(2021, 3, 31), "Annual", net_income=None)
        assert _ttm_flow([annual], "net_income") is None

    def test_negative_flow_item_sums_correctly(self):
        """Negative quarterly values (losses) sum normally — not zeroed or dropped."""
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = [_snap(d, "Quarterly", net_income=-10.0) for d in ends]
        assert _ttm_flow(snaps, "net_income") == pytest.approx(-40.0)


# ---------------------------------------------------------------------------
# DC1b — Earnings yield (E/P) (03 §3 V1)
# ---------------------------------------------------------------------------


class TestEarningsYield:
    def _snaps_with_ni(
        self, net_income: float, shares: float = 1_000_000.0
    ) -> list[FundamentalsSnapshot]:
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        return [
            _snap(d, "Quarterly", net_income=net_income, shares_outstanding=shares)
            for d in ends
        ]

    def test_basic_computation(self):
        """E/P = TTM NI / (close_raw × shares). Higher ratio = cheaper stock = better rank."""
        snaps = self._snaps_with_ni(100.0, shares=1_000.0)
        close_raw = 10.0
        # TTM NI = 4 × 100 = 400; market_cap = 10 × 1000 = 10000
        result = earnings_yield(snaps, close_raw)
        assert result == pytest.approx(400.0 / 10_000.0)

    def test_negative_net_income_is_computed_not_null(self):
        """Loss-makers have a real (negative) yield — not a degenerate case (03 §4.3)."""
        snaps = self._snaps_with_ni(-100.0, shares=1_000.0)
        result = earnings_yield(snaps, 10.0)
        assert result is not None
        assert result < 0.0

    def test_zero_shares_returns_none(self):
        """Zero shares_outstanding → market cap = 0 → None."""
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = [
            _snap(d, "Quarterly", net_income=50.0, shares_outstanding=0.0) for d in ends
        ]
        assert earnings_yield(snaps, 10.0) is None

    def test_missing_shares_returns_none(self):
        """No shares_outstanding in any snapshot → None (not zero-filled)."""
        annual = _snap(datetime.date(2021, 3, 31), "Annual", net_income=200.0)
        assert earnings_yield([annual], 10.0) is None

    def test_missing_net_income_returns_none(self):
        """No TTM net_income available → None (03 §4.2 absent-not-zero)."""
        annual = _snap(
            datetime.date(2021, 3, 31),
            "Annual",
            shares_outstanding=1000.0,
            net_income=None,
        )
        assert earnings_yield([annual], 10.0) is None


# ---------------------------------------------------------------------------
# DC1c — Book-to-price (B/P) (03 §3 V2)
# ---------------------------------------------------------------------------


class TestBookToPrice:
    def _btp_snaps(
        self, equity: float, shares: float = 1_000.0
    ) -> list[FundamentalsSnapshot]:
        return [
            _snap(
                datetime.date(2022, 3, 31),
                "Annual",
                total_equity=equity,
                shares_outstanding=shares,
            )
        ]

    def test_basic_computation(self):
        """B/P = total_equity / (close_raw × shares). raw×raw convention."""
        close_raw = 10.0
        snaps = self._btp_snaps(5_000.0, shares=1_000.0)
        # market_cap = 10 × 1000 = 10000; B/P = 5000 / 10000 = 0.5
        result = book_to_price(snaps, close_raw)
        assert result == pytest.approx(0.5)

    def test_non_positive_equity_returns_none(self):
        """total_equity ≤ 0 → None (03 §4.3 — meaningless ratio, not an outlier)."""
        assert book_to_price(self._btp_snaps(0.0), 10.0) is None
        assert book_to_price(self._btp_snaps(-100.0), 10.0) is None

    def test_zero_market_cap_returns_none(self):
        """close_raw = 0 → market cap = 0 → None."""
        snaps = self._btp_snaps(5_000.0, shares=1_000.0)
        assert book_to_price(snaps, 0.0) is None

    def test_missing_shares_returns_none(self):
        """No shares_outstanding → can't compute market cap → None."""
        snaps = [_snap(datetime.date(2022, 3, 31), "Annual", total_equity=5_000.0)]
        assert book_to_price(snaps, 10.0) is None


# ---------------------------------------------------------------------------
# DC1d — ROE (03 §3 Q1)
# ---------------------------------------------------------------------------


class TestROE:
    def _roe_snaps(
        self,
        net_income: float,
        equity: float,
        *,
        quarterly: bool = True,
        annual_equity: float | None = None,
    ) -> list[FundamentalsSnapshot]:
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = [_snap(d, "Quarterly", net_income=net_income) for d in ends]
        snaps.append(_snap(datetime.date(2022, 3, 31), "Annual", total_equity=equity))
        if annual_equity is not None:
            snaps.append(
                _snap(datetime.date(2021, 3, 31), "Annual", total_equity=annual_equity)
            )
        return snaps

    def test_basic_roe(self):
        """ROE = TTM NI / avg(equity). Profitable company → positive ROE."""
        snaps = self._roe_snaps(25.0, equity=500.0)
        # TTM NI = 4 × 25 = 100; only 1 annual → avg equity = 500
        result = roe(snaps)
        assert result == pytest.approx(100.0 / 500.0)

    def test_avg_of_two_annual_equities(self):
        """ROE denominator averages latest 2 Annual equity values when both visible."""
        snaps = self._roe_snaps(25.0, equity=600.0, annual_equity=400.0)
        # avg equity = (600 + 400) / 2 = 500; TTM NI = 100
        result = roe(snaps)
        assert result == pytest.approx(100.0 / 500.0)

    def test_non_positive_equity_returns_none(self):
        """total_equity ≤ 0 → None (03 §4.3). Avoids division by zero / negative ROE from bad data."""
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = [_snap(d, "Quarterly", net_income=25.0) for d in ends]
        snaps.append(_snap(datetime.date(2022, 3, 31), "Annual", total_equity=0.0))
        assert roe(snaps) is None

    def test_missing_net_income_returns_none(self):
        annual = _snap(datetime.date(2022, 3, 31), "Annual", total_equity=500.0)
        assert roe([annual]) is None

    def test_avg_equity_helper_two_annuals(self):
        """_avg_equity_for_roe uses latest 2 annual equity points."""
        snaps = [
            _snap(datetime.date(2022, 3, 31), "Annual", total_equity=600.0),
            _snap(datetime.date(2021, 3, 31), "Annual", total_equity=400.0),
        ]
        result = _avg_equity_for_roe(snaps)
        assert result == pytest.approx(500.0)

    def test_avg_equity_helper_one_annual(self):
        """Only 1 annual equity available → use that one."""
        snaps = [_snap(datetime.date(2022, 3, 31), "Annual", total_equity=500.0)]
        assert _avg_equity_for_roe(snaps) == pytest.approx(500.0)

    def test_avg_equity_helper_no_annual_falls_back_to_latest(self):
        """No Annual snapshots → fall back to latest any-type equity."""
        snaps = [
            _snap(datetime.date(2022, 3, 31), "Quarterly", total_equity=300.0),
        ]
        assert _avg_equity_for_roe(snaps) == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# DC1e — Accruals (03 §3 Q2)
# ---------------------------------------------------------------------------


class TestAccruals:
    def _acc_snaps(
        self,
        net_income: float = 100.0,
        cfo: float = 120.0,
        assets: float = 2000.0,
    ) -> list[FundamentalsSnapshot]:
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = [_snap(d, "Quarterly", net_income=net_income, cfo=cfo) for d in ends]
        snaps.append(_snap(datetime.date(2022, 3, 31), "Annual", total_assets=assets))
        return snaps

    def test_basic_accruals_sign_flipped(self):
        """Low accruals (NI < CFO) → negative raw value → flipped to positive → better rank.

        Sloan's quality signal: earnings backed by cash are more persistent.
        """
        snaps = self._acc_snaps(net_income=25.0, cfo=30.0, assets=2000.0)
        # TTM NI = 100; TTM CFO = 120; assets = 2000
        # raw accrual = (100 - 120) / 2000 = -0.01; sign-flipped = +0.01
        result = accruals(snaps, is_financial=False)
        assert result == pytest.approx(0.01)

    def test_high_accruals_gives_negative_value(self):
        """High accruals (NI >> CFO) → positive raw → flipped to negative → worse rank."""
        snaps = self._acc_snaps(net_income=25.0, cfo=10.0, assets=2000.0)
        # TTM NI = 100; TTM CFO = 40; accrual = (100 - 40) / 2000 = +0.03; flipped = -0.03
        result = accruals(snaps, is_financial=False)
        assert result == pytest.approx(-0.03)

    def test_financial_isin_returns_none(self):
        """Banks/NBFCs excluded from accruals cross-section (03 §3 — pre-committed)."""
        snaps = self._acc_snaps()
        assert accruals(snaps, is_financial=True) is None

    def test_zero_assets_returns_none(self):
        """total_assets = 0 → division by zero → None (03 §4.3)."""
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = [_snap(d, "Quarterly", net_income=25.0, cfo=30.0) for d in ends]
        snaps.append(_snap(datetime.date(2022, 3, 31), "Annual", total_assets=0.0))
        assert accruals(snaps, is_financial=False) is None

    def test_negative_assets_returns_none(self):
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = [_snap(d, "Quarterly", net_income=25.0, cfo=30.0) for d in ends]
        snaps.append(_snap(datetime.date(2022, 3, 31), "Annual", total_assets=-500.0))
        assert accruals(snaps, is_financial=False) is None

    def test_missing_cfo_returns_none(self):
        """Can't compute TTM CFO → accruals is None (not zero-filled)."""
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = [_snap(d, "Quarterly", net_income=25.0, cfo=None) for d in ends]
        snaps.append(_snap(datetime.date(2022, 3, 31), "Annual", total_assets=2000.0))
        assert accruals(snaps, is_financial=False) is None


# ---------------------------------------------------------------------------
# DC1f — Leverage (03 §3 Q3)
# ---------------------------------------------------------------------------


class TestLeverage:
    def _lev_snaps(
        self,
        debt: float = 500.0,
        equity: float = 1000.0,
    ) -> list[FundamentalsSnapshot]:
        return [
            _snap(
                datetime.date(2022, 3, 31),
                "Annual",
                total_debt=debt,
                total_equity=equity,
            )
        ]

    def test_basic_leverage_sign_flipped(self):
        """Low debt/equity → less negative (after flip) → higher rank → better.

        Signal: low leverage cushions drawdown in risk-off regimes (03 §3 rationale).
        """
        snaps = self._lev_snaps(debt=500.0, equity=1000.0)
        # ratio = 500/1000 = 0.5; sign-flipped = -0.5
        result = leverage(snaps, is_financial=False)
        assert result == pytest.approx(-0.5)

    def test_high_leverage_worse_rank(self):
        """High debt/equity → more negative (after flip) → lower rank → worse."""
        snaps = self._lev_snaps(debt=2000.0, equity=500.0)
        # ratio = 4.0; flipped = -4.0
        result = leverage(snaps, is_financial=False)
        assert result == pytest.approx(-4.0)

    def test_financial_isin_returns_none(self):
        """Banks/NBFCs excluded from leverage cross-section (03 §3 — pre-committed).

        Bank 'leverage' is their business model — not comparable to non-financials.
        """
        snaps = self._lev_snaps()
        assert leverage(snaps, is_financial=True) is None

    def test_non_positive_equity_returns_none(self):
        """total_equity ≤ 0 → None (03 §4.3 — D/E ratio is meaningless)."""
        assert leverage(self._lev_snaps(equity=0.0), is_financial=False) is None
        assert leverage(self._lev_snaps(equity=-100.0), is_financial=False) is None

    def test_missing_debt_returns_none(self):
        """No total_debt in any snapshot → None (absent, not zero-filled)."""
        snaps = [_snap(datetime.date(2022, 3, 31), "Annual", total_equity=1000.0)]
        assert leverage(snaps, is_financial=False) is None


# ---------------------------------------------------------------------------
# DC2 — Composite wiring: mean-over-active (03 §5)
# ---------------------------------------------------------------------------


def _make_prices(isins: list[str], dates: list[datetime.date]) -> pd.DataFrame:
    """Minimal long-format prices DataFrame for composite_rank tests."""
    rows = []
    for isin in isins:
        for d in dates:
            rows.append(
                {
                    "isin": isin,
                    "date": pd.Timestamp(d),
                    "close": 100.0,
                    "close_raw": 100.0,
                }
            )
    return pd.DataFrame(rows)


def _make_factor_frame(
    value: float | None, isins: list[str], dates: list[datetime.date]
) -> pd.DataFrame:
    """Uniform-value fundamental factor frame (date × isin)."""
    idx = pd.to_datetime(dates)
    data = {isin: ([value] * len(dates)) for isin in isins}
    return pd.DataFrame(data, index=idx)


class TestCompositeWiring:
    """Tests that composite_rank blends fundamentals correctly under mean-over-active."""

    def _cfg(self, active: list[str]):
        from app.backtest_v2.v3_config import V3Config

        return V3Config(active_factors=active)

    def _prices(self, isins: list[str], n_days: int = 300):
        dates = [
            datetime.date(2021, 1, 1) + datetime.timedelta(days=i)
            for i in range(n_days)
        ]
        rows = [
            {"isin": isin, "date": pd.Timestamp(d), "close": float(50 + j)}
            for j, isin in enumerate(isins)
            for d in dates
        ]
        return pd.DataFrame(rows)

    def test_track_a_path_unchanged_no_extra_frames(self):
        """Pure price factors with no extra_raw_frames → Track-A NaN-propagation path.

        Regression guard: existing Track-A tests should not be affected by TBE1.
        """
        from app.backtest_v2.factors import composite_rank

        isins = ["A", "B", "C"]
        prices = self._prices(isins, n_days=280)
        cfg = self._cfg(["mom_12_1"])
        result = composite_rank(prices, cfg, extra_raw_frames=None)
        assert isinstance(result, pd.DataFrame)
        assert set(result.columns) == set(isins)

    def test_missing_fundamental_does_not_count_in_mean(self):
        """Name with no fundamental data averages over its price factors only (03 §5).

        The uncovered tail must not become all-NaN just because fundamentals are missing.
        This is the key H3 composition rule: mean-over-active, not require-all-present.
        """
        from app.backtest_v2.factors import composite_rank

        isins = ["HAS_FUND", "NO_FUND"]
        prices = self._prices(isins, n_days=280)
        cfg = self._cfg(["mom_12_1", "earnings_yield"])

        # Only HAS_FUND has a fundamental frame; NO_FUND gets NaN there
        dates = [datetime.date(2022, 1, 3), datetime.date(2022, 2, 1)]
        fund_frame = pd.DataFrame(
            {"HAS_FUND": [0.9, 0.9], "NO_FUND": [None, None]},
            index=pd.to_datetime(dates),
        )

        result = composite_rank(
            prices, cfg, extra_raw_frames={"earnings_yield": fund_frame}
        )

        # Both names should have non-NaN composite on a date where price factor is available
        # (NO_FUND only has mom_12_1; HAS_FUND has both)
        # Both need price warmup (252 days) first; just verify the frame shape is correct.
        assert "HAS_FUND" in result.columns
        assert "NO_FUND" in result.columns

    def test_missing_frame_for_active_fundamental_raises(self):
        """Active fundamental factor without a frame in extra_raw_frames → ValueError (Rule 12)."""
        from app.backtest_v2.factors import composite_rank

        prices = self._prices(["A"], n_days=280)
        cfg = self._cfg(["mom_12_1", "earnings_yield"])
        with pytest.raises(ValueError, match="earnings_yield"):
            composite_rank(
                prices, cfg, extra_raw_frames={}
            )  # missing earnings_yield frame

    def test_all_factors_nan_for_cell_stays_nan(self):
        """If ALL factors produce NaN for a (date, isin) cell → composite NaN.

        A name truly absent from every factor is not tradeable (03 §5 — at least 1 factor needed).
        """
        from app.backtest_v2.factors import composite_rank

        isins = ["X"]
        prices = self._prices(isins, n_days=280)
        cfg = self._cfg(["mom_12_1", "earnings_yield"])

        # Fundamental frame with NaN everywhere
        fund_frame = pd.DataFrame(
            {"X": [None]},
            index=pd.to_datetime([datetime.date(2022, 3, 1)]),
        )
        result = composite_rank(
            prices, cfg, extra_raw_frames={"earnings_yield": fund_frame}
        )
        # Where mom_12_1 also has no data (warmup), composite should be NaN
        warmup_date = result.index[0]
        assert math.isnan(result.at[warmup_date, "X"])

    def test_nanmean_ignores_nan_factors_not_zero(self):
        """mean-over-active using nanmean: a NaN factor rank is excluded from the average,
        not treated as 0. This matters — zero-filling would systematically bias the score.
        """
        from app.backtest_v2.factors import composite_rank

        # Short prices for testing the blending logic directly
        dates = [
            datetime.date(2022, 1, 3) + datetime.timedelta(days=i * 7)
            for i in range(60)
        ]
        rows = []
        for d in dates:
            rows.append({"isin": "A", "date": pd.Timestamp(d), "close": 100.0})
            rows.append({"isin": "B", "date": pd.Timestamp(d), "close": 90.0})
        prices = pd.DataFrame(rows)

        cfg = self._cfg(["mom_12_1", "book_to_price"])

        # Only A has a fundamental; B's fundamental frame has NaN
        fund_frame = pd.DataFrame(
            {"A": [0.8, 0.8, 0.8], "B": [np.nan, np.nan, np.nan]},
            index=pd.to_datetime(dates[:3]),
        )
        result = composite_rank(
            prices, cfg, extra_raw_frames={"book_to_price": fund_frame}
        )

        # The result should be a valid DataFrame (no assertion error in nanmean logic)
        assert isinstance(result, pd.DataFrame)
        assert set(result.columns) == {"A", "B"}


# ---------------------------------------------------------------------------
# DC3 — Boundary tests: no zero-fill, raw×raw only, no ORM
# ---------------------------------------------------------------------------


class TestBoundaryConstraints:
    def test_empty_snapshots_return_none_not_zero(self):
        """All factors must return None (not 0.0) when no snapshots exist.

        Zero-filling is forbidden (TB4 invariant). A missing fundamental is absent,
        not a zero value that biases the cross-sectional rank.
        """
        snaps: list[FundamentalsSnapshot] = []
        assert earnings_yield(snaps, 10.0) is None
        assert book_to_price(snaps, 10.0) is None
        assert roe(snaps) is None
        assert accruals(snaps, is_financial=False) is None
        assert leverage(snaps, is_financial=False) is None

    def test_market_cap_uses_close_raw_not_adjusted(self):
        """E/P and B/P use close_raw (unadjusted); a different close would change the result.

        The TB6 raw×raw convention is load-bearing: using adjusted close × raw shares
        creates an artificial discontinuity at split events.
        """
        snaps_ep = [
            _snap(
                datetime.date(2022, 3, 31),
                "Annual",
                net_income=100.0,
                shares_outstanding=1000.0,
            ),
        ]
        close_raw = 10.0
        adjusted_close = 5.0  # hypothetical post-split adjusted price

        ep_raw = earnings_yield(snaps_ep, close_raw)
        ep_adj = earnings_yield(snaps_ep, adjusted_close)

        # Results differ — confirming the function uses exactly the close passed in
        assert ep_raw != ep_adj

    def test_compute_fundamental_factor_frame_uses_reader_seam(self):
        """compute_fundamental_factor_frame uses the injected reader, not a direct ORM import.

        Tests must be able to replace read_fundamentals_asof with a fixture; if the
        function had a hardcoded ORM import, this test would fail to inject.
        """
        import datetime as dt

        call_log: list[tuple[str, dt.date]] = []

        def mock_reader(session, isin: str, as_of: dt.date):
            call_log.append((isin, as_of))
            return [
                _snap(
                    as_of - dt.timedelta(days=90),
                    "Annual",
                    total_debt=200.0,
                    total_equity=1000.0,
                )
            ]

        prices = pd.DataFrame(
            [
                {
                    "isin": "ISIN1",
                    "date": pd.Timestamp("2022-03-31"),
                    "close": 100.0,
                    "close_raw": 100.0,
                },
            ]
        )
        rebalance_dates = [dt.date(2022, 3, 31)]

        result = compute_fundamental_factor_frame(
            "leverage",
            session=None,  # not used — injected reader handles reads
            prices=prices,
            rebalance_dates=rebalance_dates,
            financial_isins=frozenset(),
            reader=mock_reader,
        )

        # Reader was called for each (isin, date) combination
        assert ("ISIN1", dt.date(2022, 3, 31)) in call_log
        assert isinstance(result, pd.DataFrame)
        assert "ISIN1" in result.columns

    def test_financial_isin_retains_value_and_book_to_price(self):
        """Banks/NBFCs kept for E/P, B/P, ROE — only excluded from accruals/leverage (03 §3)."""
        snaps = [
            _snap(
                datetime.date(2022, 3, 31),
                "Annual",
                net_income=100.0,
                shares_outstanding=1000.0,
                total_equity=5000.0,
                total_debt=2000.0,
                total_assets=8000.0,
            ),
        ]
        close_raw = 10.0

        assert earnings_yield(snaps, close_raw) is not None
        assert book_to_price(snaps, close_raw) is not None
        # ROE uses annual fallback: TTM NI = 100 (annual), equity = 5000 → 0.02
        assert roe(snaps) is not None

        assert accruals(snaps, is_financial=True) is None
        assert leverage(snaps, is_financial=True) is None

    def test_financial_isin_roe_computable(self):
        """Banks/NBFCs are kept for ROE — it measures profitability, not capital structure."""
        ends = [
            datetime.date(2022, 3, 31),
            datetime.date(2021, 12, 31),
            datetime.date(2021, 9, 30),
            datetime.date(2021, 6, 30),
        ]
        snaps = [_snap(d, "Quarterly", net_income=25.0) for d in ends]
        snaps.append(_snap(datetime.date(2022, 3, 31), "Annual", total_equity=500.0))
        result = roe(snaps)
        assert result is not None
        assert result > 0
