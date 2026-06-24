"""Tests for T8 — validate.py acceptance checks.

All tests are offline (no network). Each test builds a synthetic prices/
membership/isin_symbol_map frame that exercises exactly one check in isolation.
Negative tests assert that AssertionError is raised on deliberately-broken data.
"""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.data.bhavcopy import store as store_mod
from app.data.bhavcopy.validate import (
    KNOWN_CA_EVENTS,
    KNOWN_RENAME,
    ValidationReport,
    _check_1_known_ca_events,
    _check_2_survivorship,
    _check_3_isin_rename,
    _check_4_no_lookahead,
    _check_5_tr_ge_price_adjusted,
    _check_7_unadjusted_action_scan,
    _check_8_succession_coverage,
    _check_9_termination_force_exit,
    run_validation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_BASE_DATE = pd.Timestamp("2020-01-02")


def _make_prices(
    isin: str = "INE000000001",
    symbol: str = "STOCK",
    n: int = 30,
    start: pd.Timestamp = _BASE_DATE,
    adj_factor: float = 1.0,
    tr_factor: float = 1.0,
    close_raw: float = 100.0,
    has_event: bool = False,
    event_row: int | None = None,
    event_adj: float | None = None,
    event_tr: float | None = None,
    vary_tv: bool = False,
) -> pd.DataFrame:
    """Build a synthetic prices_adjusted frame for one ISIN.

    vary_tv=True uses linearly-increasing traded_value so that a reversed adv_20
    meaningfully differs from the causal rolling median (needed for lookahead tests).
    """
    dates = pd.date_range(start, periods=n, freq="B")
    close_raw_arr = np.full(n, close_raw)

    adj_arr = np.ones(n) * adj_factor
    tr_arr = np.ones(n) * tr_factor

    if has_event and event_row is not None:
        adj_arr[:event_row] = event_adj if event_adj is not None else adj_factor
        tr_arr[:event_row] = event_tr if event_tr is not None else tr_factor

    if vary_tv:
        tv = np.arange(1, n + 1, dtype=float) * 100_000.0 + 500_000.0
    else:
        tv = close_raw_arr * 10000.0

    return pd.DataFrame(
        {
            "isin": isin,
            "symbol": symbol,
            "date": dates,
            "open": close_raw_arr * adj_arr,
            "high": close_raw_arr * adj_arr * 1.01,
            "low": close_raw_arr * adj_arr * 0.99,
            "close": close_raw_arr * adj_arr,
            "close_raw": close_raw_arr,
            "close_tr": close_raw_arr * tr_arr,
            "volume": np.full(n, 10000, dtype=np.int64),
            "traded_value": tv,
            "adv_20": pd.Series(pd.Series(tv).rolling(20, min_periods=1).median()),
            "adj_factor": adj_arr,
            "tr_factor": tr_arr,
            "series": "EQ",
            "instrument_id": isin,  # T06.2: standalone → instrument_id == isin
        }
    )


def _make_membership(prices: pd.DataFrame) -> pd.DataFrame:
    return prices[["isin", "date"]].drop_duplicates().reset_index(drop=True)


def _make_isin_map(isin: str, symbol: str, prices: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "isin": [isin],
            "symbol": [symbol],
            "first_date": [prices["date"].min()],
            "last_date": [prices["date"].max()],
        }
    )


# ---------------------------------------------------------------------------
# Check 1 — Known CA events
# ---------------------------------------------------------------------------
class TestCheck1KnownCAEvents:
    def _prices_with_known_ca(self, ev: dict) -> pd.DataFrame:
        """Build synthetic price data for a known ISIN with a correctly-adjusted CA.

        Back-adjustment convention: adjusted close = constant C everywhere;
        close_raw = C / adj_factor (higher before ex-date, lower after).
        This mirrors a real post-split series where raw prices halve but
        adjusted prices stay continuous.
        """
        ex = pd.Timestamp(ev["ex_date"])
        pre_start = ex - pd.tseries.offsets.BDay(10)
        n_days = 21

        isin = ev["isin"]
        symbol = ev["symbol"]
        ratio = ev["expected_ratio"]

        dates = pd.bdate_range(pre_start, periods=n_days)
        n = len(dates)

        adj_arr = np.where(dates < ex, ratio, 1.0).astype(float)
        tr_arr = adj_arr.copy()

        adj_close = 100.0  # constant adjusted close → no gap
        close_raw_arr = adj_close / adj_arr  # pre-ex: 100/ratio; post-ex: 100

        tv = close_raw_arr * 5000.0

        return pd.DataFrame(
            {
                "isin": isin,
                "symbol": symbol,
                "date": dates,
                "open": np.full(n, adj_close),
                "high": np.full(n, adj_close * 1.01),
                "low": np.full(n, adj_close * 0.99),
                "close": np.full(n, adj_close),
                "close_raw": close_raw_arr,
                "close_tr": np.full(n, adj_close),
                "volume": np.full(n, 5000, dtype=np.int64),
                "traded_value": tv,
                "adv_20": pd.Series(tv).rolling(20, min_periods=1).median().values,
                "adj_factor": adj_arr,
                "tr_factor": tr_arr,
                "series": "EQ",
            }
        )

    def test_known_event_passes(self):
        ev = KNOWN_CA_EVENTS[0]  # RELIANCE Bonus 1:1
        prices = self._prices_with_known_ca(ev)
        report = ValidationReport()
        _check_1_known_ca_events(prices, report)  # must not raise

    def test_all_five_known_events_pass(self):
        """One synthetic frame per known event; check 1 passes for each."""
        for ev in KNOWN_CA_EVENTS:
            prices = self._prices_with_known_ca(ev)
            report = ValidationReport()
            _check_1_known_ca_events(prices, report)

    def test_spurious_gap_fails(self):
        """A >40% drop in adjusted close on the ex-date must fail.

        Simulates the failure mode where back-adjustment was NOT applied: the raw
        price halves on the ex-date but adj_factor stays 1.0, leaving a 50% drop
        in the 'adjusted' (actually unadjusted) series.
        """
        ev = KNOWN_CA_EVENTS[0]  # RELIANCE Bonus 1:1
        prices = self._prices_with_known_ca(ev)

        # Simulate missing adjustment: keep adj_factor=1.0 everywhere and let close
        # reflect the raw halving (close_raw doesn't change at ex-date, so set close
        # to close_raw — which halves post-ex in the correctly-built fixture).
        prices["adj_factor"] = 1.0
        # Before ex: close_raw = 100/ratio = 200; post-ex: close_raw = 100.
        # Set close = close_raw to remove adjustment → 50% gap.
        prices["close"] = prices["close_raw"]
        report = ValidationReport()
        with pytest.raises(AssertionError, match="gap"):
            _check_1_known_ca_events(prices, report)

    def test_wrong_ratio_fails(self):
        """adj_factor ratio that differs from the documented ratio must fail.

        Keep close continuous (no gap) so the gap check passes and the ratio
        check fires cleanly — tests only the ratio branch.
        """
        ev = KNOWN_CA_EVENTS[0]
        prices = self._prices_with_known_ca(ev)
        ex = pd.Timestamp(ev["ex_date"])
        # Wrong factor (0.9 instead of 0.5); close remains 100 everywhere (no gap).
        prices.loc[prices["date"] < ex, "adj_factor"] = 0.9
        # close stays at adj_close=100 — continuous, so gap=0%; only ratio is wrong.
        report = ValidationReport()
        with pytest.raises(AssertionError, match="adj_factor ratio"):
            _check_1_known_ca_events(prices, report)

    def test_missing_isin_skipped(self):
        """ISIN not in prices → skipped without failure, noted in report."""
        prices = _make_prices(isin="INE999999999", symbol="UNKNOWN")
        report = ValidationReport()
        _check_1_known_ca_events(prices, report)  # must not raise
        assert "1-known-ca" in " ".join(report.checks_skipped)

    def test_multi_year_build_no_known_events_fails(self):
        """Hardened Check 1: a build starting ≤2018 with zero known ISINs → FAIL.

        WHY: INFY (2018-06-14) and TCS (2018-07-26) events must be present in
        any build covering 2018.  Finding no known ISINs at all means data loss
        or wrong store path — it must fail, not silently skip.
        """
        early_start = pd.Timestamp("2018-01-02")
        prices = _make_prices(
            isin="INE999999999", symbol="UNKNOWN", n=30, start=early_start
        )
        report = ValidationReport()
        with pytest.raises(AssertionError, match="check_1"):
            _check_1_known_ca_events(prices, report)

    def test_post_2018_build_no_known_events_skipped(self):
        """Build starting after 2018 with no known ISINs → still skipped (not failed).

        WHY: RELIANCE/INFY/TCS events are all ≤2019; a 2021-start build
        legitimately lacks them.  The hardening only fires for ≤2018 builds.
        """
        late_start = pd.Timestamp("2021-01-04")
        prices = _make_prices(
            isin="INE999999999", symbol="UNKNOWN", n=30, start=late_start
        )
        report = ValidationReport()
        _check_1_known_ca_events(prices, report)  # must not raise
        assert "1-known-ca" in " ".join(report.checks_skipped)


# ---------------------------------------------------------------------------
# Check 2 — Survivorship sanity
# ---------------------------------------------------------------------------
class TestCheck2Survivorship:
    def test_delisted_present_passes(self):
        """isin_symbol_map with a last_date >1yr ago → survivorship check passes."""
        today = date(2026, 6, 14)
        isin_map = pd.DataFrame(
            {
                "isin": ["INE000000001", "INE000000002"],
                "symbol": ["LIVE", "DELISTED"],
                "first_date": [pd.Timestamp("2018-01-01"), pd.Timestamp("2018-01-01")],
                "last_date": [pd.Timestamp("2026-06-01"), pd.Timestamp("2020-01-01")],
            }
        )
        report = ValidationReport()
        _check_2_survivorship(isin_map, report, today)  # must not raise
        assert report.distinct_delisted_isins == 1

    def test_no_delisted_fails(self):
        """isin_symbol_map with only recent last_dates → FAIL."""
        today = date(2026, 6, 14)
        isin_map = pd.DataFrame(
            {
                "isin": ["INE000000001", "INE000000002"],
                "symbol": ["STOCKA", "STOCKB"],
                "first_date": [pd.Timestamp("2024-01-01")] * 2,
                "last_date": [pd.Timestamp("2026-06-01")] * 2,
            }
        )
        report = ValidationReport()
        with pytest.raises(AssertionError, match="zero ISINs"):
            _check_2_survivorship(isin_map, report, today)

    def test_empty_map_fails(self):
        """Empty isin_symbol_map → FAIL immediately."""
        isin_map = pd.DataFrame(columns=["isin", "symbol", "first_date", "last_date"])
        report = ValidationReport()
        with pytest.raises(AssertionError, match="empty"):
            _check_2_survivorship(isin_map, report, date(2026, 6, 14))

    def test_exactly_at_threshold_passes(self):
        """last_date exactly at the threshold (366 days ago) counts as delisted."""
        today = date(2026, 6, 14)
        threshold_date = pd.Timestamp(today - timedelta(days=366))
        isin_map = pd.DataFrame(
            {
                "isin": ["INE000000001"],
                "symbol": ["OLD"],
                "first_date": [pd.Timestamp("2018-01-01")],
                "last_date": [threshold_date],
            }
        )
        report = ValidationReport()
        _check_2_survivorship(isin_map, report, today)  # must not raise
        assert report.distinct_delisted_isins == 1


# ---------------------------------------------------------------------------
# Check 3 — ISIN rename continuity
# ---------------------------------------------------------------------------
class TestCheck3ISINRename:
    def _rename_map(self) -> pd.DataFrame:
        """isin_symbol_map where MOTHERSUMI → MOTHERSON (same ISIN, no overlap)."""
        return pd.DataFrame(
            {
                "isin": [KNOWN_RENAME["isin"]] * 2,
                "symbol": [KNOWN_RENAME["old_symbol"], KNOWN_RENAME["new_symbol"]],
                "first_date": [pd.Timestamp("2018-01-01"), pd.Timestamp("2022-11-01")],
                "last_date": [pd.Timestamp("2022-10-31"), pd.Timestamp("2026-06-14")],
            }
        )

    def test_rename_passes(self):
        report = ValidationReport()
        _check_3_isin_rename(self._rename_map(), report)  # must not raise

    def test_overlapping_symbols_fails(self):
        """Both symbols active at same time → FAIL."""
        bad = pd.DataFrame(
            {
                "isin": [KNOWN_RENAME["isin"]] * 2,
                "symbol": [KNOWN_RENAME["old_symbol"], KNOWN_RENAME["new_symbol"]],
                "first_date": [pd.Timestamp("2018-01-01"), pd.Timestamp("2020-01-01")],
                "last_date": [pd.Timestamp("2023-01-01"), pd.Timestamp("2026-06-14")],
            }
        )
        report = ValidationReport()
        with pytest.raises(AssertionError, match="overlapping"):
            _check_3_isin_rename(bad, report)

    def test_isin_not_in_dataset_skipped(self):
        """Unknown ISIN → skipped, noted in report."""
        isin_map = pd.DataFrame(
            {
                "isin": ["INE999999999"],
                "symbol": ["OTHER"],
                "first_date": [pd.Timestamp("2020-01-01")],
                "last_date": [pd.Timestamp("2026-01-01")],
            }
        )
        report = ValidationReport()
        _check_3_isin_rename(isin_map, report)  # must not raise
        assert any("3-isin-rename" in s for s in report.checks_skipped)

    def test_only_one_symbol_skipped(self):
        """Only the new symbol in dataset → can't verify rename; skipped."""
        one_sym = pd.DataFrame(
            {
                "isin": [KNOWN_RENAME["isin"]],
                "symbol": [KNOWN_RENAME["new_symbol"]],
                "first_date": [pd.Timestamp("2022-11-01")],
                "last_date": [pd.Timestamp("2026-06-14")],
            }
        )
        report = ValidationReport()
        _check_3_isin_rename(one_sym, report)  # must not raise
        assert any("3-isin-rename" in s for s in report.checks_skipped)


# ---------------------------------------------------------------------------
# Check 4 — No lookahead in adv_20
# ---------------------------------------------------------------------------
class TestCheck4NoLookahead:
    def test_causal_adv20_passes(self):
        prices = _make_prices(n=30)
        report = ValidationReport()
        _check_4_no_lookahead(prices, report)  # must not raise

    def test_lookahead_contamination_fails(self):
        """Corrupt adv_20 (future values leaked in) → FAIL.

        vary_tv=True creates strictly-increasing traded_value so that reversing
        adv_20 produces values meaningfully different from the causal median.
        """
        prices = _make_prices(n=30, vary_tv=True)
        prices["adv_20"] = prices["adv_20"].values[::-1]
        report = ValidationReport()
        with pytest.raises(AssertionError, match="lookahead"):
            _check_4_no_lookahead(prices, report)

    def test_insufficient_rows_skipped(self):
        """ISIN with <25 rows → skipped gracefully."""
        prices = _make_prices(n=10)
        report = ValidationReport()
        _check_4_no_lookahead(prices, report)  # must not raise
        assert any("4-no-lookahead" in s for s in report.checks_skipped)

    def test_spike_resistance(self):
        """A single large traded_value spike must not affect adv_20 of other rows (median)."""
        prices = _make_prices(n=30)
        # Insert a ₹1B spike on day 15; the rolling median should absorb it.
        prices.loc[14, "traded_value"] = 1_000_000_000.0
        # Recompute adv_20 correctly.
        prices["adv_20"] = prices["traded_value"].rolling(20, min_periods=1).median()
        report = ValidationReport()
        _check_4_no_lookahead(prices, report)  # must not raise


# ---------------------------------------------------------------------------
# Check 5 — close_tr ≥ close cumulative return
# ---------------------------------------------------------------------------
class TestCheck5TRGePrice:
    def test_tr_ge_price_passes(self):
        """close_tr cumulative return ≥ close: passes when tr_factor ≤ adj_factor."""
        # tr_factor(0) = 0.4 ≤ adj_factor(0) = 0.5 → cum_tr > cum_adj.
        prices = _make_prices(
            n=30, has_event=True, event_row=15, event_adj=0.5, event_tr=0.4
        )
        report = ValidationReport()
        _check_5_tr_ge_price_adjusted(prices, report)  # must not raise

    def test_no_event_passes(self):
        """No events → adj_factor = tr_factor = 1.0 everywhere; cum_tr = cum_adj."""
        prices = _make_prices(n=30)
        report = ValidationReport()
        _check_5_tr_ge_price_adjusted(prices, report)  # must not raise

    def test_tr_less_than_price_fails(self):
        """close_tr gives lower cumulative return than close → FAIL."""
        prices = _make_prices(n=30)
        # Force close_tr much lower at the end (negative dividend would do this).
        prices.loc[prices.index[-1], "close_tr"] = 1.0  # near zero → cum_tr near 0
        prices.loc[prices.index[0], "close_tr"] = 50.0  # high start → cum_tr < 1
        # Ensure close gives cum_adj > 1.
        prices.loc[prices.index[-1], "close"] = 200.0
        prices.loc[prices.index[0], "close"] = 100.0
        report = ValidationReport()
        with pytest.raises(AssertionError, match="close_tr cumulative return"):
            _check_5_tr_ge_price_adjusted(prices, report)

    def test_empty_prices_skipped(self):
        empty = pd.DataFrame(columns=list(store_mod.PRICES_ADJUSTED_SCHEMA))
        report = ValidationReport()
        _check_5_tr_ge_price_adjusted(empty, report)  # must not raise
        assert any("5-tr-ge-price" in s for s in report.checks_skipped)


# ---------------------------------------------------------------------------
# run_validation end-to-end (via store parquet round-trip)
# ---------------------------------------------------------------------------
class TestRunValidation:
    def _write_passing_dataset(self, tmp_path: Path, today: date) -> None:
        """Write all three tables with enough structure to pass all checks.

        Live ISIN: 30 business days ending ~today so it is NOT counted as delisted.
        Delisted ISIN: 30 business days ending ~2 years ago so it IS counted.
        traded_value varies (vary_tv=True) so that reversing adv_20 creates a real
        mismatch detectable by check 4.
        """
        live_isin = "INE000000001"
        delisted_isin = "INE000000002"

        # Live ISIN ends close to today (within 365 days → not delisted).
        live_start = pd.Timestamp(today - timedelta(days=50))
        prices_live = _make_prices(
            isin=live_isin, symbol="LIVE", n=30, start=live_start, vary_tv=True
        )

        # Delisted ISIN ends ~2 years ago (> 365 days → delisted).
        old_start = pd.Timestamp(today - timedelta(days=800))
        prices_del = _make_prices(
            isin=delisted_isin, symbol="GONE", n=30, start=old_start
        )

        prices = pd.concat([prices_live, prices_del], ignore_index=True)
        membership = pd.concat(
            [_make_membership(prices_live), _make_membership(prices_del)],
            ignore_index=True,
        )
        isin_map = pd.DataFrame(
            {
                "isin": [live_isin, delisted_isin],
                "symbol": ["LIVE", "GONE"],
                "first_date": [prices_live["date"].min(), prices_del["date"].min()],
                "last_date": [prices_live["date"].max(), prices_del["date"].max()],
                "instrument_id": [live_isin, delisted_isin],
            }
        )

        store_mod.write_prices_adjusted(prices, root=tmp_path)
        store_mod.write_universe_membership(membership, root=tmp_path)
        store_mod.write_isin_symbol_map(isin_map, root=tmp_path)

    def test_full_validation_passes(self, tmp_path):
        today = date(2026, 6, 14)
        self._write_passing_dataset(tmp_path, today)
        report = run_validation(
            root=tmp_path,
            ca_events_applied=5,
            ca_events_unmatched=1,
            today=today,
        )
        assert isinstance(report, ValidationReport)
        assert report.rows == 60
        assert report.distinct_isins == 2
        assert report.distinct_delisted_isins == 1
        assert report.ca_events_applied == 5
        assert report.ca_events_unmatched == 1

    def test_survivorship_failure_breaks_run(self, tmp_path):
        """Dataset with no delisted ISINs must fail even if all other checks pass."""
        today = date(2026, 6, 14)
        # Use a recent start so last_date is within 365 days of today → not delisted.
        live_start = pd.Timestamp(today - timedelta(days=50))
        prices = _make_prices(n=30, start=live_start)
        membership = _make_membership(prices)
        isin_map = pd.DataFrame(
            {
                "isin": ["INE000000001"],
                "symbol": ["LIVE"],
                "first_date": [prices["date"].min()],
                "last_date": [prices["date"].max()],  # within 365 days → not delisted
                "instrument_id": ["INE000000001"],
            }
        )
        store_mod.write_prices_adjusted(prices, root=tmp_path)
        store_mod.write_universe_membership(membership, root=tmp_path)
        store_mod.write_isin_symbol_map(isin_map, root=tmp_path)

        with pytest.raises(AssertionError, match="zero ISINs"):
            run_validation(root=tmp_path, today=today)

    def test_lookahead_failure_breaks_run(self, tmp_path):
        """Corrupted adv_20 (future values leaked in) must fail check 4."""
        today = date(2026, 6, 14)
        self._write_passing_dataset(tmp_path, today)

        # Reverse adv_20 for the live ISIN. Because vary_tv=True was used,
        # traded_value strictly increases, so the causal median and its reverse
        # differ meaningfully at most row positions.
        prices = store_mod.read_prices_adjusted(tmp_path)
        live_mask = prices["isin"] == "INE000000001"
        live_adv = prices.loc[live_mask, "adv_20"].values.copy()
        prices.loc[live_mask, "adv_20"] = live_adv[::-1]
        store_mod.write_prices_adjusted(prices, root=tmp_path)

        with pytest.raises(AssertionError, match="lookahead"):
            run_validation(root=tmp_path, today=today)

    def test_tr_below_price_breaks_run(self, tmp_path):
        """close_tr < close cumulative return must fail check 5."""
        today = date(2026, 6, 14)
        self._write_passing_dataset(tmp_path, today)

        prices = store_mod.read_prices_adjusted(tmp_path)
        # Force close_tr to give a terrible cumulative return for the live ISIN.
        live_mask = prices["isin"] == "INE000000001"
        idx = prices[live_mask].index
        prices.loc[idx[0], "close_tr"] = 200.0  # high start
        prices.loc[idx[-1], "close_tr"] = 10.0  # low end → cum_tr << 1
        prices.loc[idx[0], "close"] = 100.0
        prices.loc[idx[-1], "close"] = 200.0  # cum_adj = 2.0 > cum_tr
        store_mod.write_prices_adjusted(prices, root=tmp_path)

        with pytest.raises(AssertionError, match="close_tr cumulative return"):
            run_validation(root=tmp_path, today=today)

    def test_coverage_report_fields_populated(self, tmp_path):
        today = date(2026, 6, 14)
        self._write_passing_dataset(tmp_path, today)
        report = run_validation(root=tmp_path, today=today)
        assert report.date_range_start is not None
        assert report.date_range_end is not None
        assert report.pct_days_with_gaps >= 0.0
        assert report.rows > 0

    def test_empty_store_check2_fails(self, tmp_path):
        """An empty store fails check 2 (empty isin_symbol_map)."""
        # Write empty frames.
        store_mod.write_prices_adjusted(
            pd.DataFrame(
                {
                    c: pd.Series([], dtype=store_mod.PRICES_ADJUSTED_SCHEMA[c])
                    for c in store_mod.PRICES_ADJUSTED_SCHEMA
                }
            ),
            root=tmp_path,
        )
        store_mod.write_universe_membership(
            pd.DataFrame(
                {
                    c: pd.Series(
                        [], dtype="string" if "isin" in c else "datetime64[ns]"
                    )
                    for c in store_mod.UNIVERSE_MEMBERSHIP_SCHEMA
                }
            ),
            root=tmp_path,
        )
        store_mod.write_isin_symbol_map(
            pd.DataFrame(
                {
                    c: pd.Series(
                        [],
                        dtype="string"
                        if "isin" in c or "symbol" in c
                        else "datetime64[ns]",
                    )
                    for c in store_mod.ISIN_SYMBOL_MAP_SCHEMA
                }
            ),
            root=tmp_path,
        )
        with pytest.raises(AssertionError, match="empty"):
            run_validation(root=tmp_path, today=date(2026, 6, 14))


# ---------------------------------------------------------------------------
# Check 7 — Universe-wide unadjusted-split/bonus scan
# ---------------------------------------------------------------------------
def _make_prices_with_split_cliff(
    ratio: float,
    isin: str = "INE000000001",
    symbol: str = "STOCK",
    n: int = 30,
    cliff_row: int = 15,
    adjust: bool = False,
) -> pd.DataFrame:
    """Build a synthetic prices frame with a single split/bonus cliff at cliff_row.

    ratio:   price multiplier after the event (e.g. 0.5 for a 2:1 split).
    adjust:  if True, adj_factor steps at cliff_row so the adjusted close is
             continuous — simulates a correctly-applied back-adjustment.
             if False, adj_factor stays 1.0 — simulates a missed adjustment.
    """
    dates = pd.date_range("2022-01-03", periods=n, freq="B")

    close_raw = np.ones(n, dtype=float) * 100.0
    close_raw[cliff_row:] *= ratio  # raw price drops at cliff

    adj_factor = np.ones(n, dtype=float)
    if adjust:
        # Factor steps down before the cliff so close = close_raw * adj_factor = 100
        adj_factor[:cliff_row] = ratio

    close = close_raw * adj_factor
    tv = np.ones(n, dtype=float) * 1_000_000.0

    return pd.DataFrame(
        {
            "isin": isin,
            "symbol": symbol,
            "date": dates,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "close_raw": close_raw,
            "close_tr": close,
            "volume": np.full(n, 10_000, dtype=np.int64),
            "traded_value": tv,
            "adv_20": pd.Series(tv).rolling(20, min_periods=1).median().values,
            "adj_factor": adj_factor,
            "tr_factor": adj_factor.copy(),
            "series": "EQ",
        }
    )


class TestCheck7UnadjustedActionScan:
    def test_unadjusted_split_fails(self):
        """A clean-ratio drop with flat factors must FAIL check_7.

        WHY: flat adj_factor + clean-ratio close drop is the exact signature of
        a missed back-adjustment.  Even one event must trigger the gate.
        """
        prices = _make_prices_with_split_cliff(ratio=0.5, adjust=False)
        report = ValidationReport()
        with pytest.raises(AssertionError, match="check_7"):
            _check_7_unadjusted_action_scan(prices, report, tolerance=0)

    def test_correctly_adjusted_passes(self):
        """Same split, but adj_factor steps correctly → check_7 must PASS.

        WHY: the back-adjustment factor must absorb the corporate action so the
        adjusted close series is continuous (no clean-ratio drop remains).
        """
        prices = _make_prices_with_split_cliff(ratio=0.5, adjust=True)
        report = ValidationReport()
        _check_7_unadjusted_action_scan(prices, report, tolerance=0)  # must not raise

    @pytest.mark.parametrize(
        "ratio",
        [0.5, 1.0 / 3, 0.25, 0.2, 0.1],
        ids=["2:1", "3:1", "4:1", "5:1", "10:1"],
    )
    def test_all_standard_ratios_flagged(self, ratio: float):
        """Every supported split/bonus ratio must be detected when unadjusted.

        WHY: the NSE CA universe includes all these ratio types; missing any one
        of them would leave real splits undetected by the gate.
        """
        prices = _make_prices_with_split_cliff(ratio=ratio, adjust=False)
        report = ValidationReport()
        with pytest.raises(AssertionError, match="check_7"):
            _check_7_unadjusted_action_scan(prices, report, tolerance=0)

    def test_near_ratio_within_tolerance_flagged(self):
        """A price ratio within ±10% of a clean multiplier must still be flagged.

        WHY: real CUPID Bonus 4:1 gave ratio 0.204 (target 0.2, +2%) — the
        tolerance must absorb minor rounding without missing the event.
        """
        # ratio=0.204 is within ±10% of 0.2 (5:1/Bonus-4:1)
        prices = _make_prices_with_split_cliff(ratio=0.204, adjust=False)
        report = ValidationReport()
        with pytest.raises(AssertionError, match="check_7"):
            _check_7_unadjusted_action_scan(prices, report, tolerance=0)

    def test_non_split_ratio_not_flagged(self):
        """A >40% drop that does NOT match any standard split ratio → not flagged.

        WHY: genuine market crashes can produce large drops; check_7 must not
        false-positive on a -43% crash that doesn't match 2:1, 3:1, 4:1, 5:1,
        or 10:1 within the ±10% band.
        """
        # ratio=0.57 → 43% drop.  Nearest multiplier 0.5 (2:1): |0.57-0.5|=0.07
        # vs tolerance band 0.5*0.10=0.05 → outside band → not flagged.
        prices = _make_prices_with_split_cliff(ratio=0.57, adjust=False)
        report = ValidationReport()
        _check_7_unadjusted_action_scan(prices, report, tolerance=0)  # must not raise

    def test_small_drop_not_flagged(self):
        """A drop < 40% (even at a clean ratio) must not be flagged.

        WHY: Bonus 1:2 events only drop the price by ~33%; they should not
        trigger the gate (below the detection threshold of 40%).
        """
        # ratio=0.8 → 20% drop; even if the ratio happened to match a multiplier,
        # 0.8 is outside all the ±10% bands around [0.5, 0.333, 0.25, 0.2, 0.1].
        prices = _make_prices_with_split_cliff(ratio=0.8, adjust=False)
        report = ValidationReport()
        _check_7_unadjusted_action_scan(prices, report, tolerance=0)  # must not raise

    def test_multiple_isins_counted_independently(self):
        """Events across multiple ISINs are each counted; sum must exceed tolerance.

        WHY: the scan must aggregate across the full universe, not per-ISIN.
        """
        p1 = _make_prices_with_split_cliff(ratio=0.5, isin="INE000000001", adjust=False)
        p2 = _make_prices_with_split_cliff(ratio=0.5, isin="INE000000002", adjust=False)
        prices = pd.concat([p1, p2], ignore_index=True)
        report = ValidationReport()
        # 2 events; tolerance=1 → fails (2 > 1)
        with pytest.raises(AssertionError, match="check_7"):
            _check_7_unadjusted_action_scan(prices, report, tolerance=1)
        # tolerance=2 → passes (2 ≤ 2)
        report2 = ValidationReport()
        _check_7_unadjusted_action_scan(prices, report2, tolerance=2)  # must not raise

    def test_empty_prices_skipped(self):
        """Empty prices → check_7 skipped gracefully, noted in report."""
        empty = pd.DataFrame(columns=list(store_mod.PRICES_ADJUSTED_SCHEMA))
        report = ValidationReport()
        _check_7_unadjusted_action_scan(empty, report)
        assert any("7-unadjusted" in s for s in report.checks_skipped)


class TestRunValidationCheck7Integration:
    """End-to-end run_validation integration tests for Check 7."""

    def _write_passing_dataset(self, tmp_path: Path, today: date) -> None:
        """Minimal passing dataset (reused from TestRunValidation helpers)."""
        live_start = pd.Timestamp(today - timedelta(days=50))
        old_start = pd.Timestamp(today - timedelta(days=800))
        prices_live = _make_prices(
            isin="INE000000001", symbol="LIVE", n=30, start=live_start, vary_tv=True
        )
        prices_del = _make_prices(
            isin="INE000000002", symbol="GONE", n=30, start=old_start
        )
        prices = pd.concat([prices_live, prices_del], ignore_index=True)
        membership = pd.concat(
            [_make_membership(prices_live), _make_membership(prices_del)],
            ignore_index=True,
        )
        isin_map = pd.DataFrame(
            {
                "isin": ["INE000000001", "INE000000002"],
                "symbol": ["LIVE", "GONE"],
                "first_date": [prices_live["date"].min(), prices_del["date"].min()],
                "last_date": [prices_live["date"].max(), prices_del["date"].max()],
                "instrument_id": ["INE000000001", "INE000000002"],
            }
        )
        store_mod.write_prices_adjusted(prices, root=tmp_path)
        store_mod.write_universe_membership(membership, root=tmp_path)
        store_mod.write_isin_symbol_map(isin_map, root=tmp_path)

    def test_unadjusted_split_breaks_run(self, tmp_path):
        """An injected unadjusted split must fail run_validation via Check 7.

        WHY: end-to-end gate — the full validation pipeline must surface a
        missed adjustment even when all other checks pass.
        """
        today = date(2026, 6, 14)
        self._write_passing_dataset(tmp_path, today)

        # Inject one unadjusted 2:1 split into the live ISIN.
        prices = store_mod.read_prices_adjusted(tmp_path)
        live_mask = prices["isin"] == "INE000000001"
        idx = prices[live_mask].index.tolist()
        for i in idx[15:]:
            prices.loc[i, "close"] = prices.loc[i, "close"] * 0.5
        # adj_factor stays 1.0 (flat) — simulates missed adjustment.
        store_mod.write_prices_adjusted(prices, root=tmp_path)

        with pytest.raises(AssertionError, match="check_7"):
            run_validation(root=tmp_path, today=today, check7_tolerance=0)

    def test_clean_dataset_passes_check7(self, tmp_path):
        """Dataset with no split cliffs passes Check 7 at default tolerance."""
        today = date(2026, 6, 14)
        self._write_passing_dataset(tmp_path, today)
        report = run_validation(root=tmp_path, today=today)
        assert isinstance(report, ValidationReport)


# ---------------------------------------------------------------------------
# Check 8 — Succession coverage (T06.4)
# ---------------------------------------------------------------------------

_OLD = "INE100A01011"  # old leg of a face-value-split chain
_NEW = "INE100A01029"  # new leg (successor)
_ROOT = _OLD  # root_isin = oldest ISIN in the chain


def _make_successor_map_row(
    old: str = _OLD,
    new: str = _NEW,
    root: str = _ROOT,
    asserted: bool = True,
    liquid: bool = True,
) -> pd.DataFrame:
    return store_mod._conform(
        pd.DataFrame(
            [
                {
                    "old_isin": old,
                    "new_isin": new,
                    "transition_date": pd.Timestamp("2020-06-02"),
                    "sig_consecutive": True,
                    "sig_prefix": True,
                    "sig_ca_split": False,
                    "signals_matched": 2,
                    "asserted": asserted,
                    "root_isin": root if asserted else "",
                    "liquid_old_leg": liquid,
                }
            ]
        ),
        store_mod.SUCCESSOR_MAP_SCHEMA,
        "successor_map",
    )


def _make_prices_with_id(
    isin: str, instrument_id: str, n: int = 10, start: str = "2020-01-02"
) -> pd.DataFrame:
    """One ISIN's prices with an explicit instrument_id."""
    base = _make_prices(isin=isin, symbol="SYM", n=n, start=pd.Timestamp(start))
    base["instrument_id"] = instrument_id
    return base


class TestCheck8SuccessionCoverage:
    """Check 8 — asserted chains must resolve in prices_adjusted (T06.4).

    WHY: if the new leg's ISIN is absent or its instrument_id isn't set to the
    chain root, the signal layer is still momentum-blind on the new leg and the
    old leg remains a sellable ghost — the exact defect that 06 closes.
    """

    def test_stitched_chain_passes(self):
        """Both legs present + correct instrument_id → check 8 passes."""
        smap = _make_successor_map_row()
        prices = pd.concat(
            [
                _make_prices_with_id(_OLD, _ROOT, n=10, start="2020-01-02"),
                _make_prices_with_id(_NEW, _ROOT, n=10, start="2020-06-02"),
            ],
            ignore_index=True,
        )
        report = ValidationReport()
        _check_8_succession_coverage(smap, prices, report)  # must not raise

        assert report.succession_chains_asserted == 1
        assert report.succession_liquid_ghost_risk == 1
        assert report.succession_liquid_resolved == 1

    def test_broken_missing_new_isin_fails(self):
        """New leg absent from prices_adjusted → check 8 fails (ghost risk not resolved).

        WHY: the old leg held by the book has no future prices once it goes
        dark — fills are dropped and the position is carried forever. The check
        must catch this regression before it contaminates a warm-start.
        """
        smap = _make_successor_map_row()
        # Only the old leg; new leg (successor) is entirely absent.
        prices = _make_prices_with_id(_OLD, _ROOT, n=10, start="2020-01-02")
        report = ValidationReport()
        with pytest.raises(AssertionError, match="check_8"):
            _check_8_succession_coverage(smap, prices, report)

    def test_broken_wrong_instrument_id_mid_leg_fails(self):
        """Mid-chain leg instrument_id ≠ root_isin → check 8 fails (multi-hop not stitched).

        WHY: in a multi-hop chain A→B→C the B→C edge has old_isin=B, root=A.
        If B's instrument_id was never updated (still "B"), the momentum series
        for B's data is not joined to A's — the B leg is effectively invisible
        to A's signal computation. This tests the old-leg gate for the non-trivial
        case where old_isin != root_isin.
        """
        A = "INE100A01011"  # chain root
        B = "INE100A01029"  # middle leg
        C = "INE100A01037"  # newest leg
        # B→C edge asserted, root = A.
        smap = _make_successor_map_row(old=B, new=C, root=A, liquid=True)
        prices = pd.concat(
            [
                # B leg: instrument_id NOT updated to root A (still its own ISIN B).
                _make_prices_with_id(B, B, n=10, start="2019-06-01"),
                _make_prices_with_id(C, A, n=10, start="2020-06-02"),
            ],
            ignore_index=True,
        )
        report = ValidationReport()
        with pytest.raises(AssertionError, match="check_8"):
            _check_8_succession_coverage(smap, prices, report)

    def test_broken_wrong_instrument_id_new_leg_fails(self):
        """New leg instrument_id ≠ root_isin → check 8 fails (un-stitched new leg).

        WHY: the new leg carrying its own raw ISIN as instrument_id means
        T06.2 rederive was not applied — the new leg is momentum-blind for
        the full lookback window after the transition.
        """
        smap = _make_successor_map_row()
        prices = pd.concat(
            [
                _make_prices_with_id(_OLD, _ROOT, n=10, start="2020-01-02"),
                # New leg: instrument_id NOT updated (still its own ISIN, not root).
                _make_prices_with_id(_NEW, _NEW, n=10, start="2020-06-02"),
            ],
            ignore_index=True,
        )
        report = ValidationReport()
        with pytest.raises(AssertionError, match="check_8"):
            _check_8_succession_coverage(smap, prices, report)

    def test_no_map_skips_gracefully(self):
        """Empty successor_map → check 8 skipped, noted in report, no raise."""
        empty_smap = store_mod._empty(store_mod.SUCCESSOR_MAP_SCHEMA)
        prices = _make_prices_with_id(_OLD, _OLD, n=10)
        report = ValidationReport()
        _check_8_succession_coverage(empty_smap, prices, report)  # must not raise
        assert any("8-succession" in s for s in report.checks_skipped)

    def test_unasserted_links_ignored(self):
        """Non-asserted candidates in the map are not checked (only asserted matter)."""
        smap = _make_successor_map_row(asserted=False)
        # Only old leg present; if the unasserted link were checked this would fail.
        prices = _make_prices_with_id(_OLD, _OLD, n=10)
        report = ValidationReport()
        _check_8_succession_coverage(smap, prices, report)  # must not raise
        assert any("8-succession" in s for s in report.checks_skipped)

    def test_liquid_ghost_risk_counts(self):
        """Report correctly counts liquid vs non-liquid resolved chains."""
        # One liquid asserted edge (resolved), one non-liquid asserted edge (resolved).
        liq_row = _make_successor_map_row(
            old="INE111A01011", new="INE111A01029", root="INE111A01011", liquid=True
        )
        non_liq_row = _make_successor_map_row(
            old="INE222A01011", new="INE222A01029", root="INE222A01011", liquid=False
        )
        smap = pd.concat([liq_row, non_liq_row], ignore_index=True)
        prices = pd.concat(
            [
                _make_prices_with_id("INE111A01011", "INE111A01011", n=5),
                _make_prices_with_id("INE111A01029", "INE111A01011", n=5),
                _make_prices_with_id("INE222A01011", "INE222A01011", n=5),
                _make_prices_with_id("INE222A01029", "INE222A01011", n=5),
            ],
            ignore_index=True,
        )
        report = ValidationReport()
        _check_8_succession_coverage(smap, prices, report)

        assert report.succession_chains_asserted == 2
        assert report.succession_liquid_ghost_risk == 1
        assert report.succession_liquid_resolved == 1


# ---------------------------------------------------------------------------
# Check 9 — termination force-exit safety (T07.4)
# ---------------------------------------------------------------------------
_TERM_CAL = pd.bdate_range("2024-01-01", periods=60)  # dense trading calendar
_TERM_EDGE_ORD = len(_TERM_CAL) - 1


def _term_rows(isin, symbol, last_idx, close=95.0, adv=1e8, iid=None):
    """Two-row terminated leg: first print at cal[0], last print at cal[last_idx].

    close < 100 keeps last_peak_ratio > 0.5 → value-preserved → classified merger
    (not insolvency); adv ≥ ₹5cr floor → liquid; unique last_idx → cluster_size 1.
    """
    iid = iid or isin
    cols = ("isin", "symbol", "date", "close_raw", "adv_20", "instrument_id")
    out = []
    for d, c in ((_TERM_CAL[0], 100.0), (_TERM_CAL[last_idx], close)):
        out.append(dict(zip(cols, (isin, symbol, d, c, adv, iid))))
    return out


def _term_alive_rows():
    """An ISIN trading every day of the calendar → defines the dense ordinals + edge.

    It is alive at the edge, so classify_terminations excludes it (its chain still
    trades) — it only supplies the trading-day grid silence is counted on.
    """
    cols = ("isin", "symbol", "date", "close_raw", "adv_20", "instrument_id")
    return [
        dict(zip(cols, ("INEALIVE0001", "ALIVE", d, 100.0, 1e8, "INEALIVE0001")))
        for d in _TERM_CAL
    ]


class TestCheck9TerminationForceExit:
    """Check 9 — no carried-unsellable holding at the store edge (T07.4).

    WHY: a merger/cancellation/insolvency leg with no successor stops trading, so a
    held position can never be sold and is carried as an MTM-frozen ghost (07 §1).
    The engine force-exits any holding silent ≥ K trading days (07 §6 Approach A);
    this check enforces that EVERY genuine liquid termination is past that K-day
    silence at the edge, so a warm-start (T07.5) inherits zero ghosts. A leg silent
    < K is the exact defect — it must fail loud, not pass quietly.
    """

    def _empty_smap(self):
        return store_mod._empty(store_mod.SUCCESSOR_MAP_SCHEMA)

    def test_all_terminations_silent_past_k_pass(self):
        """Two genuine terminated legs both silent ≥ K → force-exit-safe, no raise."""
        prices = pd.DataFrame(
            _term_alive_rows()
            + _term_rows("INEMERGE0001", "TAKENA", last_idx=_TERM_EDGE_ORD - 35)
            + _term_rows("INEMERGE0002", "TAKENB", last_idx=_TERM_EDGE_ORD - 25)
        )
        report = ValidationReport()
        _check_9_termination_force_exit(prices, self._empty_smap(), report, k=15)

        assert report.terminations_liquid == 2
        assert report.terminations_force_exit_safe == 2
        assert report.terminations_carried_at_edge == 0

    def test_termination_silent_under_k_fails(self):
        """A terminated leg silent < K trading days is still carried at the edge → fail.

        WHY: silence is counted in TRADING days (matching the engine), while the
        classifier's terminated cutoff is calendar days — a leg ~25 trading days
        silent is unambiguously terminated yet, under a K=30 force-exit rule, has
        not been liquidated. The book would still hold it: a carried-unsellable ghost.
        """
        prices = pd.DataFrame(
            _term_alive_rows()
            + _term_rows("INEMERGE0001", "SAFE", last_idx=_TERM_EDGE_ORD - 35)
            + _term_rows("INEMERGE0002", "CARRIED", last_idx=_TERM_EDGE_ORD - 25)
        )
        report = ValidationReport()
        # K=30: the 25-day-silent leg is carried; the 35-day-silent one is safe.
        # _check_9 populates the report but does NOT raise — the raise is gated
        # behind run_validation(raise_on_check9=True) since commit 9a1b0885.
        _check_9_termination_force_exit(prices, self._empty_smap(), report, k=30)
        assert report.terminations_carried_at_edge == 1
        assert report.terminations_force_exit_safe == 1
        assert "INEMERGE0002" in report.terminations_carried_isins

    def test_data_gap_suspect_excluded_from_assertion(self):
        """An ingest-gap cluster silent < K must NOT fail the check (07 §10).

        WHY: a shared near-edge last_date is a data-ingest fingerprint, not a real
        delisting — those names are expected to resume printing, so force-exiting
        them would be a false positive. They are counted, not asserted on.
        """
        # 5 names sharing one near-edge last_date → data_gap_suspect; silent only
        # ~14 trading days (< K) but must be excluded from the carried assertion.
        gap_idx = _TERM_EDGE_ORD - 14
        gap_rows = []
        for i in range(5):
            gap_rows += _term_rows(f"INEGAP0000{i}", f"GAP{i}", last_idx=gap_idx)
        prices = pd.DataFrame(
            _term_alive_rows()
            + _term_rows("INEMERGE0001", "SAFE", last_idx=_TERM_EDGE_ORD - 35)
            + gap_rows
        )
        report = ValidationReport()
        _check_9_termination_force_exit(prices, self._empty_smap(), report, k=20)

        assert report.terminations_data_gap_suspect == 5
        assert report.terminations_carried_at_edge == 0
        assert report.terminations_force_exit_safe == 1

    def test_three_t065_ghosts_force_exit_safe(self):
        """The three real T06.5 ghosts (HDFC, INOXLEISUR, TATAMTRDVR), terminated
        long before the edge, must classify as force-exit-safe — the production case."""
        prices = pd.DataFrame(
            _term_alive_rows()
            + _term_rows("INE001A01036", "HDFC", last_idx=2, close=91.0)
            + _term_rows("INE312H01016", "INOXLEISUR", last_idx=3, close=90.0)
            + _term_rows("IN9155A01020", "TATAMTRDVR", last_idx=4, close=90.0)
        )
        report = ValidationReport()
        _check_9_termination_force_exit(prices, self._empty_smap(), report, k=15)
        assert report.terminations_liquid == 3
        assert report.terminations_force_exit_safe == 3
        assert report.terminations_carried_at_edge == 0

    def test_missing_columns_skips_gracefully(self):
        """Pre-T07.1 store shape (no close_raw/instrument_id) → skip, no raise."""
        prices = pd.DataFrame(
            {"isin": ["X"], "symbol": ["X"], "date": [pd.Timestamp("2024-01-01")]}
        )
        report = ValidationReport()
        _check_9_termination_force_exit(prices, self._empty_smap(), report)
        assert any("9-termination" in s for s in report.checks_skipped)

    def test_empty_prices_skips_gracefully(self):
        report = ValidationReport()
        _check_9_termination_force_exit(pd.DataFrame(), self._empty_smap(), report)
        assert any("9-termination" in s for s in report.checks_skipped)


class TestRunValidationCheck8Integration:
    """End-to-end run_validation integration for Check 8."""

    def _write_base_dataset(self, tmp_path: Path, today: date) -> None:
        """Minimal dataset that passes checks 1-7 (reused from Check 7 tests)."""
        live_start = pd.Timestamp(today - timedelta(days=50))
        old_start = pd.Timestamp(today - timedelta(days=800))
        prices_live = _make_prices(
            isin="INE000000001", symbol="LIVE", n=30, start=live_start, vary_tv=True
        )
        prices_del = _make_prices(
            isin="INE000000002", symbol="GONE", n=30, start=old_start
        )
        prices = pd.concat([prices_live, prices_del], ignore_index=True)
        membership = pd.concat(
            [_make_membership(prices_live), _make_membership(prices_del)],
            ignore_index=True,
        )
        isin_map = pd.DataFrame(
            {
                "isin": ["INE000000001", "INE000000002"],
                "symbol": ["LIVE", "GONE"],
                "first_date": [prices_live["date"].min(), prices_del["date"].min()],
                "last_date": [prices_live["date"].max(), prices_del["date"].max()],
                "instrument_id": ["INE000000001", "INE000000002"],
            }
        )
        store_mod.write_prices_adjusted(prices, root=tmp_path)
        store_mod.write_universe_membership(membership, root=tmp_path)
        store_mod.write_isin_symbol_map(isin_map, root=tmp_path)

    def test_stitched_chain_passes_run_validation(self, tmp_path):
        """A fully stitched chain in prices_adjusted + successor_map → run_validation passes."""
        today = date(2026, 6, 14)
        self._write_base_dataset(tmp_path, today)

        # Add a stitched succession chain.
        old_prices = _make_prices_with_id(
            _OLD,
            _ROOT,
            n=15,
            start=str((pd.Timestamp(today) - pd.tseries.offsets.BDay(35)).date()),
        )
        new_prices = _make_prices_with_id(
            _NEW,
            _ROOT,
            n=10,
            start=str((pd.Timestamp(today) - pd.tseries.offsets.BDay(15)).date()),
        )
        chain_prices = pd.concat([old_prices, new_prices], ignore_index=True)

        existing = store_mod.read_prices_adjusted(root=tmp_path)
        all_prices = pd.concat([existing, chain_prices], ignore_index=True)
        store_mod.write_prices_adjusted(all_prices, root=tmp_path)

        store_mod.write_successor_map(_make_successor_map_row(), root=tmp_path)

        report = run_validation(root=tmp_path, today=today)
        assert report.succession_chains_asserted == 1
        assert report.succession_liquid_resolved == 1

    def test_unstitched_chain_fails_run_validation(self, tmp_path):
        """An asserted edge where the new leg is absent breaks run_validation.

        WHY: end-to-end gate — the full validation pipeline must detect a
        succession that was asserted but not materialised in prices_adjusted,
        so any future re-derive regression is caught immediately.
        """
        today = date(2026, 6, 14)
        self._write_base_dataset(tmp_path, today)

        # Old leg present in prices, but new leg absent (broken / un-stitched).
        old_prices = _make_prices_with_id(_OLD, _ROOT, n=10)
        existing = store_mod.read_prices_adjusted(root=tmp_path)
        store_mod.write_prices_adjusted(
            pd.concat([existing, old_prices], ignore_index=True), root=tmp_path
        )
        store_mod.write_successor_map(_make_successor_map_row(), root=tmp_path)

        with pytest.raises(AssertionError, match="check_8"):
            run_validation(root=tmp_path, today=today)

    def test_no_successor_map_passes_run_validation(self, tmp_path):
        """Absence of successor_map → check 8 skipped; run_validation still passes."""
        today = date(2026, 6, 14)
        self._write_base_dataset(tmp_path, today)
        # No successor_map written — pre-T06.1 store shape.
        report = run_validation(root=tmp_path, today=today)
        assert report.succession_chains_asserted == 0
        assert any("8-succession" in s for s in report.checks_skipped)


class TestRunValidationCheck9Integration:
    """End-to-end run_validation integration for Check 9 (termination force-exit)."""

    def _write_dataset(
        self, tmp_path: Path, today: date, *, term_close_raw: float
    ) -> None:
        """A live name + one terminated leg (liquid iff term_close_raw clears the floor).

        The terminated leg's last trade is ~750 days before today → silent for far
        more than K trading days at the edge, so a liquid one is force-exit-safe.
        """
        live_start = pd.Timestamp(today - timedelta(days=50))
        term_start = pd.Timestamp(today - timedelta(days=800))
        prices_live = _make_prices(
            isin="INE000000001", symbol="LIVE", n=30, start=live_start, vary_tv=True
        )
        prices_term = _make_prices(
            isin="INE000000002",
            symbol="GONE",
            n=30,
            start=term_start,
            close_raw=term_close_raw,
        )
        prices = pd.concat([prices_live, prices_term], ignore_index=True)
        membership = pd.concat(
            [_make_membership(prices_live), _make_membership(prices_term)],
            ignore_index=True,
        )
        isin_map = pd.DataFrame(
            {
                "isin": ["INE000000001", "INE000000002"],
                "symbol": ["LIVE", "GONE"],
                "first_date": [prices_live["date"].min(), prices_term["date"].min()],
                "last_date": [prices_live["date"].max(), prices_term["date"].max()],
                "instrument_id": ["INE000000001", "INE000000002"],
            }
        )
        store_mod.write_prices_adjusted(prices, root=tmp_path)
        store_mod.write_universe_membership(membership, root=tmp_path)
        store_mod.write_isin_symbol_map(isin_map, root=tmp_path)

    def test_liquid_termination_force_exit_safe_passes(self, tmp_path):
        """A liquid leg terminated long ago → force-exit-safe → run_validation passes."""
        today = date(2026, 6, 14)
        # close_raw 6000 ⇒ traded_value 6e7 ⇒ adv_20 ≥ ₹5cr floor ⇒ liquid.
        self._write_dataset(tmp_path, today, term_close_raw=6000.0)
        report = run_validation(root=tmp_path, today=today)
        assert report.terminations_liquid == 1
        assert report.terminations_force_exit_safe == 1
        assert report.terminations_carried_at_edge == 0

    def test_illiquid_termination_not_counted(self, tmp_path):
        """A leg below the ₹5cr floor is not S3-eligible → not a ghost-risk → skipped."""
        today = date(2026, 6, 14)
        # close_raw 100 ⇒ traded_value 1e6 ⇒ adv_20 well below floor ⇒ illiquid.
        self._write_dataset(tmp_path, today, term_close_raw=100.0)
        report = run_validation(root=tmp_path, today=today)
        assert report.terminations_liquid == 0
        assert report.terminations_carried_at_edge == 0
