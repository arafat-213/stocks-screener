"""T5 — adjust.py tests.

Offline only — synthetic in-memory DataFrames, no network (CLAUDE.md Rule 4).
Factor arithmetic is hand-verified against the T4 back-adjustment convention:
latest price = factor 1.0; pre-event prices scaled toward today's share basis.

Covers:
  * No CA events → adj_factor = tr_factor = 1.0; close = close_raw = close_tr.
  * 1:5 split: pre-ex-date adj_factor = 0.2; post adj_factor = 1.0;
    no spurious >40% single-day gap at the boundary (T8 criterion 1).
  * OHLC all scaled by the same factor.
  * close_raw × adj_factor = close; close_raw × tr_factor = close_tr (round-trip).
  * TR cumulative return >= price-adj cumulative return when dividend present (T8 criterion 5).
  * traded_value null / zero → fallback to close_raw × volume; valid value untouched.
  * Empty raw_df → empty output with correct columns.
  * Events for ISIN A do not affect ISIN B.
  * Output columns exactly match ADJUSTED_INTERMEDIATE_COLUMNS.
"""

import numpy as np
import pandas as pd
import pytest

from app.data.bhavcopy.adjust import ADJUSTED_INTERMEDIATE_COLUMNS, adjust_prices
from app.data.bhavcopy.corporate_actions import CA_EVENT_COLUMNS

# --------------------------------------------------------------------------- #
# Fixture helpers                                                              #
# --------------------------------------------------------------------------- #
_RAW_COLS = [
    "isin",
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "traded_value",
    "series",
]

ISIN_A = "INE001A01036"
ISIN_B = "INE002A01018"


def _row(
    isin: str,
    date: str,
    close: float,
    *,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: int = 1000,
    traded_value: float | None = None,
    symbol: str = "TEST",
    series: str = "EQ",
) -> dict:
    c = float(close)
    return {
        "isin": isin,
        "symbol": symbol,
        "date": pd.Timestamp(date),
        "open": float(open_) if open_ is not None else c * 0.99,
        "high": float(high) if high is not None else c * 1.01,
        "low": float(low) if low is not None else c * 0.98,
        "close": c,
        "volume": int(volume),
        "traded_value": float(traded_value) if traded_value is not None else c * volume,
        "series": series,
    }


def _raw(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=_RAW_COLS)


def _events(*rows: dict) -> pd.DataFrame:
    """Build a CA events DataFrame (T4 schema)."""
    if not rows:
        return pd.DataFrame(columns=CA_EVENT_COLUMNS)
    records = [
        {
            "isin": r["isin"],
            "symbol": r.get("symbol", "TEST"),
            "ex_date": pd.Timestamp(r["ex_date"]),
            "type": r["type"],
            "ratio": float(r["ratio"]) if "ratio" in r else np.nan,
            "dividend": float(r["dividend"]) if "dividend" in r else np.nan,
            "subject": r.get("subject", ""),
        }
        for r in rows
    ]
    return pd.DataFrame(records, columns=CA_EVENT_COLUMNS)


# --------------------------------------------------------------------------- #
# No CA events                                                                 #
# --------------------------------------------------------------------------- #
class TestNoEvents:
    def test_factors_are_one(self):
        """With no CA events adj_factor = tr_factor = 1.0 everywhere."""
        df = _raw(_row(ISIN_A, "2023-01-01", 100), _row(ISIN_A, "2023-01-02", 105))
        out = adjust_prices(df, _events())
        assert out["adj_factor"].tolist() == pytest.approx([1.0, 1.0])
        assert out["tr_factor"].tolist() == pytest.approx([1.0, 1.0])

    def test_close_equals_close_raw_and_close_tr(self):
        df = _raw(_row(ISIN_A, "2023-01-01", 100), _row(ISIN_A, "2023-01-02", 105))
        out = adjust_prices(df, _events())
        np.testing.assert_array_almost_equal(out["close"], out["close_raw"])
        np.testing.assert_array_almost_equal(out["close_tr"], out["close_raw"])


# --------------------------------------------------------------------------- #
# Split adjustment                                                             #
# --------------------------------------------------------------------------- #
class TestSplitAdjustment:
    """1:5 split (FV 10→2, price multiplier ratio=0.2) ex-date 2023-03-01.

    Back-adjustment convention: dates strictly before ex-date get factor=0.2;
    on/after ex-date get factor=1.0 (price already reflects the split).
    """

    SPLIT_DATE = pd.Timestamp("2023-03-01")
    RATIO = 0.2  # new_FV / old_FV = 2 / 10

    def _build(self):
        rows = [
            _row(ISIN_A, "2023-02-27", 1020, open_=1010, high=1030, low=1000),
            _row(ISIN_A, "2023-02-28", 1000, open_=990, high=1010, low=980),
            # On ex-date the traded price is already post-split (~200).
            _row(ISIN_A, "2023-03-01", 204, open_=200, high=210, low=195),
            _row(ISIN_A, "2023-03-02", 206, open_=203, high=208, low=200),
        ]
        evts = _events(
            {
                "isin": ISIN_A,
                "ex_date": "2023-03-01",
                "type": "split",
                "ratio": self.RATIO,
            }
        )
        return _raw(*rows), evts

    def test_pre_split_adj_factor(self):
        raw, evts = self._build()
        out = adjust_prices(raw, evts).sort_values("date").reset_index(drop=True)
        pre = out[out["date"] < self.SPLIT_DATE]
        np.testing.assert_array_almost_equal(pre["adj_factor"], [self.RATIO] * len(pre))

    def test_post_split_adj_factor(self):
        raw, evts = self._build()
        out = adjust_prices(raw, evts).sort_values("date").reset_index(drop=True)
        post = out[out["date"] >= self.SPLIT_DATE]
        np.testing.assert_array_almost_equal(post["adj_factor"], [1.0] * len(post))

    def test_no_spurious_gap_at_ex_date(self):
        """Adjusted close-to-close gap at ex-date must be < 40% (T8 criterion 1)."""
        raw, evts = self._build()
        out = adjust_prices(raw, evts).sort_values("date").reset_index(drop=True)
        pre_close = out[out["date"] < self.SPLIT_DATE]["close"].iloc[-1]
        post_close = out[out["date"] >= self.SPLIT_DATE]["close"].iloc[0]
        gap_pct = abs(post_close - pre_close) / pre_close
        assert gap_pct < 0.40, (
            f"Spurious gap {gap_pct:.1%} >= 40% at split ex-date "
            f"(pre_adj={pre_close:.4f}, post={post_close:.4f})"
        )

    def test_ohlc_all_scaled_by_same_factor(self):
        """open / high / low / close are all multiplied by adj_factor."""
        raw, evts = self._build()
        out = adjust_prices(raw, evts).sort_values("date").reset_index(drop=True)
        pre = out[out["date"] < self.SPLIT_DATE].iloc[0]
        assert pre["open"] == pytest.approx(1010 * self.RATIO)
        assert pre["high"] == pytest.approx(1030 * self.RATIO)
        assert pre["low"] == pytest.approx(1000 * self.RATIO)
        assert pre["close"] == pytest.approx(1020 * self.RATIO)


# --------------------------------------------------------------------------- #
# Reconstructability                                                           #
# --------------------------------------------------------------------------- #
class TestReconstructability:
    """close_raw × adj_factor = close; close_raw × tr_factor = close_tr."""

    def test_split_round_trip(self):
        # 1:2.5 split (ratio = 0.4): pre-split price 500 → adj close 200.
        raw = _raw(
            _row(ISIN_A, "2022-07-01", 500),
            _row(ISIN_A, "2022-07-10", 200),
        )
        evts = _events(
            {"isin": ISIN_A, "ex_date": "2022-07-05", "type": "split", "ratio": 0.4}
        )
        out = adjust_prices(raw, evts).sort_values("date").reset_index(drop=True)
        np.testing.assert_array_almost_equal(
            out["close_raw"] * out["adj_factor"], out["close"]
        )
        np.testing.assert_array_almost_equal(
            out["close_raw"] * out["tr_factor"], out["close_tr"]
        )

    def test_bonus_round_trip(self):
        # Bonus 1:1 (ratio = 1/2 = 0.5): pre-bonus price 300 → adj close 150.
        raw = _raw(
            _row(ISIN_B, "2021-01-10", 300),
            _row(ISIN_B, "2021-01-20", 150),
        )
        evts = _events(
            {"isin": ISIN_B, "ex_date": "2021-01-15", "type": "bonus", "ratio": 0.5}
        )
        out = adjust_prices(raw, evts).sort_values("date").reset_index(drop=True)
        np.testing.assert_array_almost_equal(
            out["close_raw"] * out["adj_factor"], out["close"]
        )

    def test_close_raw_is_unadjusted(self):
        """close_raw must be the original traded price, never the adjusted value."""
        raw = _raw(_row(ISIN_A, "2023-01-01", 1000))
        evts = _events(
            {"isin": ISIN_A, "ex_date": "2023-02-01", "type": "split", "ratio": 0.2}
        )
        out = adjust_prices(raw, evts)
        assert out["close_raw"].iloc[0] == pytest.approx(1000.0)
        assert out["close"].iloc[0] == pytest.approx(1000.0 * 0.2)


# --------------------------------------------------------------------------- #
# Total-return: close_tr cumulative >= close (adj) cumulative (01 §7.5)        #
# --------------------------------------------------------------------------- #
class TestTotalReturn:
    def test_tr_cumulative_return_ge_adj_cumulative_with_dividend(self):
        """A dividend reduces tr_factor for pre-ex-date rows, making the historical
        TR-adjusted price lower and thus the cumulative TR return larger (T8 criterion 5).
        """
        # Flat stock at 1000 for 6 months; Rs 20 dividend on 2023-04-15.
        dates = [f"2023-0{m}-15" for m in range(1, 7)]
        raw = _raw(*[_row(ISIN_A, d, 1000) for d in dates])
        evts = _events(
            {
                "isin": ISIN_A,
                "ex_date": "2023-04-15",
                "type": "dividend",
                "dividend": 20.0,
            }
        )
        out = adjust_prices(raw, evts).sort_values("date").reset_index(drop=True)

        cum_tr = out["close_tr"].iloc[-1] / out["close_tr"].iloc[0]
        cum_adj = out["close"].iloc[-1] / out["close"].iloc[0]
        assert cum_tr >= cum_adj - 1e-9, (
            f"TR cumulative ({cum_tr:.6f}) < price-adj cumulative ({cum_adj:.6f})"
        )

    def test_pre_dividend_close_tr_less_than_adj_close(self):
        """Before dividend ex-date tr_factor < adj_factor → close_tr < close (adj)."""
        raw = _raw(
            _row(ISIN_A, "2023-01-01", 1000),
            _row(ISIN_A, "2023-06-01", 1000),
        )
        # Rs 50 dividend on 2023-06-01; cum-close used = close on 2023-01-01 = 1000.
        evts = _events(
            {
                "isin": ISIN_A,
                "ex_date": "2023-06-01",
                "type": "dividend",
                "dividend": 50.0,
            }
        )
        out = adjust_prices(raw, evts).sort_values("date").reset_index(drop=True)
        # Pre-ex-date row: tr_factor = (1 - 50/1000) = 0.95; adj_factor = 1.0.
        pre = out.iloc[0]
        assert pre["close_tr"] < pre["close"] + 1e-9


# --------------------------------------------------------------------------- #
# traded_value fallback                                                        #
# --------------------------------------------------------------------------- #
class TestTradedValueFallback:
    def test_nan_filled_with_close_raw_times_volume(self):
        raw = pd.DataFrame(
            [
                {
                    "isin": ISIN_A,
                    "symbol": "T",
                    "date": pd.Timestamp("2023-01-01"),
                    "open": 495.0,
                    "high": 505.0,
                    "low": 490.0,
                    "close": 500.0,
                    "volume": 2000,
                    "traded_value": np.nan,
                    "series": "EQ",
                }
            ]
        )
        out = adjust_prices(raw, _events())
        assert out["traded_value"].iloc[0] == pytest.approx(500.0 * 2000)

    def test_zero_filled_with_close_raw_times_volume(self):
        raw = pd.DataFrame(
            [
                {
                    "isin": ISIN_A,
                    "symbol": "T",
                    "date": pd.Timestamp("2023-01-01"),
                    "open": 495.0,
                    "high": 505.0,
                    "low": 490.0,
                    "close": 500.0,
                    "volume": 2000,
                    "traded_value": 0.0,
                    "series": "EQ",
                }
            ]
        )
        out = adjust_prices(raw, _events())
        assert out["traded_value"].iloc[0] == pytest.approx(500.0 * 2000)

    def test_valid_value_not_overwritten(self):
        raw = pd.DataFrame(
            [
                {
                    "isin": ISIN_A,
                    "symbol": "T",
                    "date": pd.Timestamp("2023-01-01"),
                    "open": 495.0,
                    "high": 505.0,
                    "low": 490.0,
                    "close": 500.0,
                    "volume": 2000,
                    "traded_value": 999_999.0,
                    "series": "EQ",
                }
            ]
        )
        out = adjust_prices(raw, _events())
        assert out["traded_value"].iloc[0] == pytest.approx(999_999.0)


# --------------------------------------------------------------------------- #
# Edge cases                                                                   #
# --------------------------------------------------------------------------- #
class TestEdgeCases:
    def test_empty_raw_returns_empty_with_correct_columns(self):
        empty_raw = pd.DataFrame(columns=_RAW_COLS)
        out = adjust_prices(empty_raw, _events())
        assert len(out) == 0
        assert set(out.columns) == set(ADJUSTED_INTERMEDIATE_COLUMNS)

    def test_output_columns_exactly_match_intermediate_schema(self):
        raw = _raw(_row(ISIN_A, "2023-01-01", 100))
        out = adjust_prices(raw, _events())
        assert set(out.columns) == set(ADJUSTED_INTERMEDIATE_COLUMNS)

    def test_events_for_isin_a_do_not_affect_isin_b(self):
        """Isolation: ISIN B must remain factor=1.0 when only ISIN A has a split."""
        raw = _raw(
            _row(ISIN_A, "2023-01-01", 100),
            _row(ISIN_B, "2023-01-01", 200),
        )
        evts = _events(
            {"isin": ISIN_A, "ex_date": "2023-02-01", "type": "split", "ratio": 0.2}
        )
        out = adjust_prices(raw, evts)

        isin_b = out[out["isin"] == ISIN_B]
        assert isin_b["adj_factor"].iloc[0] == pytest.approx(1.0)
        assert isin_b["close"].iloc[0] == pytest.approx(200.0)

        isin_a = out[out["isin"] == ISIN_A]
        assert isin_a["adj_factor"].iloc[0] == pytest.approx(0.2)

    def test_events_for_isin_not_in_raw_are_ignored(self):
        """CA events whose ISIN has no price rows should not raise or corrupt output."""
        raw = _raw(_row(ISIN_A, "2023-01-01", 100))
        evts = _events(
            {"isin": ISIN_B, "ex_date": "2023-02-01", "type": "split", "ratio": 0.5}
        )
        out = adjust_prices(raw, evts)
        assert len(out) == 1
        assert out["adj_factor"].iloc[0] == pytest.approx(1.0)

    def test_multiple_isins_present(self):
        """Both ISINs appear in the output; row count matches input."""
        raw = _raw(
            _row(ISIN_A, "2023-01-01", 100),
            _row(ISIN_A, "2023-01-02", 102),
            _row(ISIN_B, "2023-01-01", 200),
        )
        out = adjust_prices(raw, _events())
        assert len(out) == 3
        assert set(out["isin"].unique()) == {ISIN_A, ISIN_B}
