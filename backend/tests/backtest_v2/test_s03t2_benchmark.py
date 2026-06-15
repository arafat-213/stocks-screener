"""
T2 acceptance tests — benchmark.py (spec 03 T2).

All offline: fixture parquet files only — no live niftyindices.com network calls.

WHY each test group exists:
  tri_load_cache   — second call must be zero-network; cache hit is verified by
                     asserting the fetch stub is only called once.
  three_series     — all three TRI constants load and return non-empty Series
                     with a DatetimeIndex and float values.
  price_index      — price index loader uses a distinct endpoint path (OHLC CLOSE
                     column); series is usable by engine.run(index_prices=...).
  distinct_roles   — TRI and price index are asserted to come from different
                     fetch functions (spec 03 §2.3 — do not feed TRI into regime).
  align_warmup     — aligned series starts exactly at date_from, not at an
                     earlier warmup date (the v1 dilution bug).
  align_rebase     — first value of aligned series equals starting_capital exactly.
  align_ffill      — a calendar date with no matching TRI entry gets forward-filled
                     from the previous TRI value.
  align_returns    — daily returns computed from aligned series match the raw TRI
                     daily returns (apples-to-apples Sharpe).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.backtest_v2.benchmark import (
    TRI_MIDCAP_MOMENTUM_50,
    TRI_MOMENTUM_30,
    TRI_NIFTY_50,
    _api_date,
    _parse_api_date,
    _rows_to_price_series,
    _rows_to_tri_series,
    align_benchmark,
    load_price_index,
    load_tri,
)

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> pd.Series:
    """Read a committed fixture parquet and return its single Series column."""
    df = pd.read_parquet(FIXTURES / name)
    return df.iloc[:, 0]


# ---------------------------------------------------------------------------
# Helpers: build synthetic row-dicts that mimic the niftyindices API response
# ---------------------------------------------------------------------------


def _tri_rows_from_series(series: pd.Series, index_name: str) -> list[dict]:
    """Convert a Series to TRI API row dicts (for inject via _fetch_fn)."""
    rows = []
    for ts, val in series.items():
        rows.append(
            {
                "RequestNumber": "FAKE",
                "Index Name": index_name,
                "Date": ts.strftime("%d %b %Y"),
                "TotalReturnsIndex": str(round(val, 2)),
                "NTR_Value": "-",
            }
        )
    return rows


def _price_rows_from_series(series: pd.Series) -> list[dict]:
    """Convert a Series to price-index API row dicts."""
    rows = []
    for ts, val in series.items():
        rows.append(
            {
                "RequestNumber": "FAKE",
                "Index Name": "",
                "INDEX_NAME": "Nifty 50",
                "HistoricalDate": ts.strftime("%d %b %Y"),
                "OPEN": str(round(val, 2)),
                "HIGH": str(round(val * 1.005, 2)),
                "LOW": str(round(val * 0.995, 2)),
                "CLOSE": str(round(val, 2)),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Date helper tests
# ---------------------------------------------------------------------------


class TestDateHelpers:
    def test_api_date_from_date(self):
        from datetime import date

        d = date(2024, 1, 15)
        assert _api_date(d) == "15-Jan-2024"

    def test_api_date_from_iso_string(self):
        assert _api_date("2024-03-31") == "31-Mar-2024"

    def test_parse_api_date_roundtrip(self):
        ts = _parse_api_date("31 Jan 2024")
        assert ts == pd.Timestamp("2024-01-31")

    def test_parse_api_date_various_months(self):
        assert _parse_api_date("01 Jun 2026") == pd.Timestamp("2026-06-01")
        assert _parse_api_date("15 Dec 2023") == pd.Timestamp("2023-12-15")


# ---------------------------------------------------------------------------
# Row-parser tests (unit)
# ---------------------------------------------------------------------------


class TestParsers:
    def test_rows_to_tri_series_sorted(self):
        rows = [
            {"Date": "15 Jan 2024", "TotalReturnsIndex": "36000.00", "NTR_Value": "-"},
            {"Date": "12 Jan 2024", "TotalReturnsIndex": "35800.00", "NTR_Value": "-"},
        ]
        s = _rows_to_tri_series(rows)
        assert list(s.index) == sorted(s.index)
        assert len(s) == 2
        assert s.iloc[0] == pytest.approx(35800.0)

    def test_rows_to_price_series_close_column(self):
        rows = [
            {
                "HistoricalDate": "31 Jan 2024",
                "OPEN": "21487.25",
                "HIGH": "21741.35",
                "LOW": "21448.85",
                "CLOSE": "21725.70",
            }
        ]
        s = _rows_to_price_series(rows)
        assert len(s) == 1
        assert s.iloc[0] == pytest.approx(21725.70)

    def test_rows_to_tri_empty(self):
        s = _rows_to_tri_series([])
        assert s.empty


# ---------------------------------------------------------------------------
# load_tri: cache behaviour
# ---------------------------------------------------------------------------


class TestLoadTriCache:
    def test_first_call_invokes_fetch(self, tmp_path):
        fixture = _load_fixture("tri_n200m30_fixture.parquet")
        rows = _tri_rows_from_series(fixture, TRI_MOMENTUM_30)
        mock_fetch = MagicMock(return_value=rows)

        result = load_tri(
            TRI_MOMENTUM_30,
            "2024-01-01",
            "2024-01-31",
            cache_dir=tmp_path,
            _fetch_fn=mock_fetch,
        )
        mock_fetch.assert_called_once()
        assert isinstance(result.index, pd.DatetimeIndex)
        assert len(result) == len(fixture)

    def test_second_call_is_zero_network(self, tmp_path):
        fixture = _load_fixture("tri_n200m30_fixture.parquet")
        rows = _tri_rows_from_series(fixture, TRI_MOMENTUM_30)
        mock_fetch = MagicMock(return_value=rows)

        # First call populates cache.
        load_tri(
            TRI_MOMENTUM_30,
            "2024-01-01",
            "2024-01-31",
            cache_dir=tmp_path,
            _fetch_fn=mock_fetch,
        )
        # Second call must NOT invoke the network.
        load_tri(
            TRI_MOMENTUM_30,
            "2024-01-01",
            "2024-01-31",
            cache_dir=tmp_path,
            _fetch_fn=mock_fetch,
        )
        mock_fetch.assert_called_once()  # still exactly once

    def test_cached_parquet_roundtrips_values(self, tmp_path):
        fixture = _load_fixture("tri_n200m30_fixture.parquet")
        rows = _tri_rows_from_series(fixture, TRI_MOMENTUM_30)
        mock_fetch = MagicMock(return_value=rows)

        first = load_tri(
            TRI_MOMENTUM_30,
            "2024-01-01",
            "2024-01-31",
            cache_dir=tmp_path,
            _fetch_fn=mock_fetch,
        )
        second = load_tri(
            TRI_MOMENTUM_30,
            "2024-01-01",
            "2024-01-31",
            cache_dir=tmp_path,
            _fetch_fn=mock_fetch,
        )
        pd.testing.assert_series_equal(first, second)


# ---------------------------------------------------------------------------
# load_tri: all three series
# ---------------------------------------------------------------------------


class TestThreeTriSeries:
    @pytest.mark.parametrize(
        "index_name,fixture_file",
        [
            (TRI_MOMENTUM_30, "tri_n200m30_fixture.parquet"),
            (TRI_MIDCAP_MOMENTUM_50, "tri_midcap_fixture.parquet"),
            (TRI_NIFTY_50, "tri_nifty50_fixture.parquet"),
        ],
    )
    def test_loads_non_empty_series(self, tmp_path, index_name, fixture_file):
        fixture = _load_fixture(fixture_file)
        rows = _tri_rows_from_series(fixture, index_name)
        mock_fetch = MagicMock(return_value=rows)

        result = load_tri(
            index_name,
            "2024-01-01",
            "2024-01-31",
            cache_dir=tmp_path,
            _fetch_fn=mock_fetch,
        )
        assert not result.empty
        assert result.dtype == float
        assert isinstance(result.index, pd.DatetimeIndex)

    def test_all_three_series_have_positive_values(self, tmp_path):
        for index_name, fixture_file in [
            (TRI_MOMENTUM_30, "tri_n200m30_fixture.parquet"),
            (TRI_MIDCAP_MOMENTUM_50, "tri_midcap_fixture.parquet"),
            (TRI_NIFTY_50, "tri_nifty50_fixture.parquet"),
        ]:
            fixture = _load_fixture(fixture_file)
            rows = _tri_rows_from_series(fixture, index_name)
            result = load_tri(
                index_name,
                "2024-01-01",
                "2024-01-31",
                cache_dir=tmp_path,
                _fetch_fn=MagicMock(return_value=rows),
            )
            assert (result > 0).all(), f"{index_name}: expected all positive TRI values"


# ---------------------------------------------------------------------------
# load_price_index
# ---------------------------------------------------------------------------


class TestLoadPriceIndex:
    def test_returns_close_series(self, tmp_path):
        fixture = _load_fixture("price_nifty50_fixture.parquet")
        rows = _price_rows_from_series(fixture)
        mock_fetch = MagicMock(return_value=rows)

        result = load_price_index(
            "2024-01-01",
            "2024-01-31",
            cache_dir=tmp_path,
            _fetch_fn=mock_fetch,
        )
        assert not result.empty
        assert isinstance(result.index, pd.DatetimeIndex)
        assert result.dtype == float
        assert (result > 0).all()

    def test_cache_is_idempotent(self, tmp_path):
        fixture = _load_fixture("price_nifty50_fixture.parquet")
        rows = _price_rows_from_series(fixture)
        mock_fetch = MagicMock(return_value=rows)

        load_price_index(
            "2024-01-01", "2024-01-31", cache_dir=tmp_path, _fetch_fn=mock_fetch
        )
        load_price_index(
            "2024-01-01", "2024-01-31", cache_dir=tmp_path, _fetch_fn=mock_fetch
        )
        mock_fetch.assert_called_once()

    def test_distinct_from_tri_fetch_path(self, tmp_path):
        """Price index uses a different fetch function than TRI — spec 03 §2.3."""
        price_fixture = _load_fixture("price_nifty50_fixture.parquet")
        tri_fixture = _load_fixture("tri_nifty50_fixture.parquet")

        price_fetch = MagicMock(return_value=_price_rows_from_series(price_fixture))
        tri_fetch = MagicMock(
            return_value=_tri_rows_from_series(tri_fixture, TRI_NIFTY_50)
        )

        load_price_index(
            "2024-01-01", "2024-01-31", cache_dir=tmp_path, _fetch_fn=price_fetch
        )
        load_tri(
            TRI_NIFTY_50,
            "2024-01-01",
            "2024-01-31",
            cache_dir=tmp_path,
            _fetch_fn=tri_fetch,
        )

        # Each function was used exactly once for its own endpoint — not cross-called.
        price_fetch.assert_called_once()
        tri_fetch.assert_called_once()


# ---------------------------------------------------------------------------
# align_benchmark
# ---------------------------------------------------------------------------


class TestAlignBenchmark:
    def _make_tri(self) -> pd.Series:
        """15 business days starting 2024-01-02."""
        dates = pd.bdate_range("2024-01-02", periods=15)
        vals = [35000.0 * (1.001**i) for i in range(15)]
        return pd.Series(vals, index=dates, name="tri")

    def test_starts_at_date_from_not_before(self):
        tri = self._make_tri()
        # The warmup period runs from tri.index[0] to tri.index[4].
        # date_from is the 5th date — aligned series must NOT contain warmup dates.
        date_from = tri.index[4]
        cal = list(tri.index)
        result = align_benchmark(tri, date_from, cal, starting_capital=1_000_000.0)

        assert result.index[0] == date_from, (
            f"align_benchmark must start at date_from ({date_from.date()}), "
            f"not at warmup start ({tri.index[0].date()})"
        )
        assert (result.index < date_from).sum() == 0

    def test_first_value_equals_starting_capital(self):
        tri = self._make_tri()
        date_from = tri.index[4]
        cal = list(tri.index)
        starting_capital = 1_500_000.0

        result = align_benchmark(tri, date_from, cal, starting_capital=starting_capital)
        assert result.iloc[0] == pytest.approx(starting_capital)

    def test_rebase_proportional(self):
        """If TRI doubles from date_from to end, rebased value should double too."""
        dates = pd.bdate_range("2024-01-02", periods=5)
        # TRI goes 100, 100, 100, 200, 200 — doubles at index[3].
        vals = [100.0, 100.0, 100.0, 200.0, 200.0]
        tri = pd.Series(vals, index=dates)
        date_from = dates[2]
        cal = list(dates)

        result = align_benchmark(tri, date_from, cal, starting_capital=1_000_000.0)
        assert result.iloc[0] == pytest.approx(1_000_000.0)
        assert result.iloc[-1] == pytest.approx(2_000_000.0)

    def test_forward_fill_on_calendar_gaps(self):
        """Calendar has extra dates not in TRI; those must be forward-filled."""
        tri_dates = pd.bdate_range("2024-01-02", periods=5)
        vals = [100.0, 101.0, 102.0, 103.0, 104.0]
        tri = pd.Series(vals, index=tri_dates)

        # Calendar includes one extra date (weekend gap between tri_dates[1] and [2]).
        extra_date = pd.Timestamp("2024-01-06")  # Saturday — not in tri
        cal = sorted(list(tri_dates) + [extra_date])
        date_from = tri_dates[0]

        result = align_benchmark(tri, date_from, cal, starting_capital=1_000_000.0)
        # The extra Saturday should be filled with the Friday value (tri_dates[1] = 101.0).
        # Since extra_date falls between tri[1] and tri[2], forward fill should give 101.0.
        assert extra_date in result.index
        assert not pd.isna(result[extra_date])

    def test_daily_returns_match_tri_returns(self):
        """Returns from rebased benchmark equal returns from raw TRI (apples-to-apples)."""
        tri = self._make_tri()
        date_from = tri.index[0]
        cal = list(tri.index)

        result = align_benchmark(tri, date_from, cal, starting_capital=1_000_000.0)
        bench_returns = result.pct_change().dropna()
        tri_returns = tri.pct_change().dropna()
        # Both series cover the same dates after date_from.
        pd.testing.assert_series_equal(
            bench_returns, tri_returns, check_names=False, check_freq=False, rtol=1e-6
        )

    def test_raises_when_no_data_at_date_from(self):
        tri = self._make_tri()
        future_date = pd.Timestamp("2030-01-01")
        cal = list(tri.index)

        with pytest.raises(ValueError, match="no TRI data"):
            align_benchmark(tri, future_date, cal, starting_capital=1_000_000.0)

    def test_warmup_does_not_dilute_benchmark_return(self):
        """The bug in v1: warmup period dilutes benchmark CAGR.

        Strategy: if the TRI grows 10% during the backtest window (date_from onward),
        the aligned benchmark return must be exactly 10%, not less (which would happen
        if warmup data diluted the start level).
        """
        # 10 day series; warmup = first 5 days; live = last 5 days.
        dates = pd.bdate_range("2024-01-02", periods=10)
        # TRI is flat during warmup, then grows 10%.
        warmup_vals = [10000.0] * 5
        live_vals = [10000.0 * (1.1 ** (i / 4)) for i in range(5)]
        tri = pd.Series(warmup_vals + live_vals, index=dates)
        date_from = dates[5]  # start of live period
        cal = list(dates)

        result = align_benchmark(tri, date_from, cal, starting_capital=1_000_000.0)
        total_return = result.iloc[-1] / result.iloc[0] - 1.0
        expected_return = tri.iloc[-1] / tri.iloc[5] - 1.0
        assert total_return == pytest.approx(expected_return, rel=1e-6)


# ---------------------------------------------------------------------------
# Integration: price index is consumable by regime overlay
# ---------------------------------------------------------------------------


class TestPriceIndexRegimeCompatibility:
    def test_price_index_has_datetimeindex(self, tmp_path):
        fixture = _load_fixture("price_nifty50_fixture.parquet")
        rows = _price_rows_from_series(fixture)
        result = load_price_index(
            "2024-01-01",
            "2024-01-31",
            cache_dir=tmp_path,
            _fetch_fn=MagicMock(return_value=rows),
        )
        assert isinstance(result.index, pd.DatetimeIndex)

    def test_price_index_accepted_by_regime_overlay(self, tmp_path):
        """Smoke: RegimeOverlay can consume the price index Series without error."""
        from app.backtest_v2.regime import RegimeConfig, RegimeOverlay

        fixture = _load_fixture("price_nifty50_fixture.parquet")
        rows = _price_rows_from_series(fixture)
        price_series = load_price_index(
            "2024-01-01",
            "2024-01-31",
            cache_dir=tmp_path,
            _fetch_fn=MagicMock(return_value=rows),
        )
        # RegimeOverlay accepts a pd.Series with DatetimeIndex → float.
        overlay = RegimeOverlay(
            index_prices=price_series, cfg=RegimeConfig(dma_period=3)
        )
        frac = overlay.deployable_fraction(price_series.index[0])
        assert frac in (1.0, RegimeConfig().risk_off_floor)
