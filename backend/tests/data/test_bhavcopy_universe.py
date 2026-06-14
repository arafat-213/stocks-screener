"""T6 — universe.py tests.

Offline only — synthetic in-memory DataFrames, no network (CLAUDE.md Rule 4).

Covers:
  * adv_20 at date D uses only data ≤ D (no lookahead — 01_DATA_LAYER.md §7.4).
  * Rolling window uses median: a single spike day does not blow up adv_20.
  * Each ISIN gets its own independent rolling window (no cross-ISIN bleed).
  * Universe membership matches (isin, date) pairs present in the input exactly.
  * isin_symbol_map tracks renames: one ISIN → two rows when the ticker changes.
  * Empty input returns empty DataFrames with the correct column schemas.
  * Output schemas exactly match PRICES_ADJUSTED_SCHEMA / UNIVERSE_MEMBERSHIP_SCHEMA
    / ISIN_SYMBOL_MAP_SCHEMA.
"""

import numpy as np
import pandas as pd
import pytest

from app.data.bhavcopy.store import (
    ISIN_SYMBOL_MAP_SCHEMA,
    PRICES_ADJUSTED_SCHEMA,
    UNIVERSE_MEMBERSHIP_SCHEMA,
)
from app.data.bhavcopy.universe import build_universe

# --------------------------------------------------------------------------- #
# Fixture helpers                                                              #
# --------------------------------------------------------------------------- #

# Columns that T5 (adjust.py) outputs — PRICES_ADJUSTED_SCHEMA minus adv_20.
_INTERMEDIATE_COLS = [c for c in PRICES_ADJUSTED_SCHEMA if c != "adv_20"]

ISIN_A = "INE001A01036"
ISIN_B = "INE002A01018"
ISIN_C = "INE003A01026"


def _row(
    isin: str,
    date: str,
    close: float = 100.0,
    *,
    traded_value: float | None = None,
    symbol: str = "TEST",
    series: str = "EQ",
) -> dict:
    """Build a single row matching the T5 intermediate schema."""
    tv = traded_value if traded_value is not None else close * 1000
    return {
        "isin": isin,
        "symbol": symbol,
        "date": pd.Timestamp(date),
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "close_raw": close,
        "close_tr": close,
        "volume": 1000,
        "traded_value": tv,
        "adj_factor": 1.0,
        "tr_factor": 1.0,
        "series": series,
    }


def _df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=_INTERMEDIATE_COLS)


# --------------------------------------------------------------------------- #
# TestAdv20NoLookahead                                                         #
# --------------------------------------------------------------------------- #


class TestAdv20NoLookahead:
    """adv_20 on date D must only use data from dates ≤ D."""

    def test_first_day_adv20_equals_its_own_traded_value(self):
        """With a single row, adv_20 must equal that row's traded_value
        (min_periods=1 kicks in)."""
        raw = _df(_row(ISIN_A, "2024-01-02", traded_value=5_000_000))
        prices, _, _ = build_universe(raw)
        assert prices["adv_20"].iloc[0] == pytest.approx(5_000_000)

    def test_second_day_adv20_is_median_of_two(self):
        """After two days the adv_20 is the median of the two values, not just
        the second day."""
        raw = _df(
            _row(ISIN_A, "2024-01-02", traded_value=4_000_000),
            _row(ISIN_A, "2024-01-03", traded_value=6_000_000),
        )
        prices, _, _ = build_universe(raw)
        # median([4M, 6M]) = 5M
        assert prices.loc[prices["date"] == pd.Timestamp("2024-01-03"), "adv_20"].iloc[
            0
        ] == pytest.approx(5_000_000)

    def test_adv20_does_not_include_future_rows(self):
        """The adv_20 on day 1 must not incorporate day 5's traded_value
        even though day 5 is in the DataFrame."""
        rows = [
            _row(ISIN_A, f"2024-01-{d:02d}", traded_value=1_000_000)
            for d in range(2, 7)
        ]
        # Overwrite day 6 with a massive spike.
        rows[-1]["traded_value"] = 1_000_000_000
        raw = _df(*rows)
        prices, _, _ = build_universe(raw)
        # Day 2 (the first row) must equal 1M, not the spike.
        day2_adv = prices.loc[
            prices["date"] == pd.Timestamp("2024-01-02"), "adv_20"
        ].iloc[0]
        assert day2_adv == pytest.approx(1_000_000)

    def test_window_rolls_correctly_at_20_days(self):
        """On day 21 the oldest day drops out of the window."""
        # Days 1-10: traded_value = 2M; days 11-20: traded_value = 4M; day 21: 4M.
        rows = [
            _row(ISIN_A, f"2024-01-{d:02d}", traded_value=2_000_000)
            for d in range(2, 12)
        ] + [
            _row(ISIN_A, f"2024-01-{d:02d}", traded_value=4_000_000)
            for d in range(12, 23)
        ]
        raw = _df(*rows)
        prices, _, _ = build_universe(raw)
        prices = prices.sort_values("date").reset_index(drop=True)

        # Day 20 (index 19): window contains rows 0-19 → 10 × 2M + 10 × 4M.
        # Sorted: [2M×10, 4M×10]; median = (2M+4M)/2 = 3M.
        adv_day20 = prices.iloc[19]["adv_20"]
        assert adv_day20 == pytest.approx(3_000_000)

        # Day 21 (index 20): window drops row 0 (2M) → 9 × 2M + 11 × 4M.
        # Sorted: [2M×9, 4M×11]; median = 4M (index 9 in 0-based 20-element list).
        adv_day21 = prices.iloc[20]["adv_20"]
        assert adv_day21 == pytest.approx(4_000_000)


# --------------------------------------------------------------------------- #
# TestAdv20MedianNotMean                                                       #
# --------------------------------------------------------------------------- #


class TestAdv20MedianNotMean:
    """A single huge spike day must not inflate adv_20 (median, not mean)."""

    def test_spike_does_not_blow_up_adv20(self):
        """19 normal days + 1 billion-rupee spike: adv_20 must stay near the
        normal level, not the spike average."""
        normal_tv = 1_000_000  # ₹10 lakh/day
        spike_tv = 1_000_000_000  # ₹100 crore spike

        rows = [
            _row(ISIN_A, f"2024-01-{d:02d}", traded_value=normal_tv)
            for d in range(2, 21)
        ]
        # Day 20: the spike.
        rows.append(_row(ISIN_A, "2024-01-21", traded_value=spike_tv))
        raw = _df(*rows)
        prices, _, _ = build_universe(raw)
        prices = prices.sort_values("date").reset_index(drop=True)

        spike_row_adv = prices.iloc[-1]["adv_20"]
        # Median of [1M × 19, 1B × 1] sorted = [1M, 1M, …, 1B].
        # 20 elements; median = (element[9] + element[10]) / 2 = (1M + 1M) / 2 = 1M.
        assert spike_row_adv == pytest.approx(normal_tv)

        # Contrast with what mean would give (should be much larger).
        mean_would_be = (19 * normal_tv + spike_tv) / 20
        assert spike_row_adv < mean_would_be / 10, (
            "adv_20 should be far below the mean when a spike is present"
        )

    def test_adv20_is_not_zero_when_some_days_are_zero(self):
        """If half the window has 0 traded_value and half has 2M, median = 1M."""
        rows = [
            _row(ISIN_A, f"2024-01-{d:02d}", traded_value=0) for d in range(2, 12)
        ] + [
            _row(ISIN_A, f"2024-01-{d:02d}", traded_value=2_000_000)
            for d in range(12, 22)
        ]
        raw = _df(*rows)
        prices, _, _ = build_universe(raw)
        prices = prices.sort_values("date").reset_index(drop=True)

        # Day 21 (index 19): 10×0 + 10×2M → sorted median = (0+2M)/2 = 1M.
        adv_day21 = prices.iloc[19]["adv_20"]
        assert adv_day21 == pytest.approx(1_000_000)


# --------------------------------------------------------------------------- #
# TestAdv20IsinIsolation                                                       #
# --------------------------------------------------------------------------- #


class TestAdv20IsinIsolation:
    """Each ISIN's rolling window must be independent of other ISINs."""

    def test_two_isins_do_not_bleed(self):
        """ISIN_A with traded_value=1M and ISIN_B with traded_value=9M;
        their adv_20 must remain distinct regardless of insertion order."""
        rows_a = [
            _row(ISIN_A, f"2024-01-{d:02d}", traded_value=1_000_000)
            for d in range(2, 22)
        ]
        rows_b = [
            _row(ISIN_B, f"2024-01-{d:02d}", traded_value=9_000_000)
            for d in range(2, 22)
        ]
        # Interleave to ensure insertion order doesn't matter.
        interleaved = []
        for ra, rb in zip(rows_a, rows_b):
            interleaved.extend([ra, rb])
        raw = _df(*interleaved)
        prices, _, _ = build_universe(raw)

        a_adv = prices.loc[prices["isin"] == ISIN_A, "adv_20"]
        b_adv = prices.loc[prices["isin"] == ISIN_B, "adv_20"]

        # Use numpy allclose — pytest.approx does not work element-wise on Series.
        assert np.allclose(a_adv.to_numpy(), 1_000_000), (
            "ISIN_A adv_20 should be 1M throughout"
        )
        assert np.allclose(b_adv.to_numpy(), 9_000_000), (
            "ISIN_B adv_20 should be 9M throughout"
        )

    def test_isin_with_longer_history_does_not_affect_newer_isin(self):
        """An ISIN that appears later should start its own adv_20 from its own
        first date, not inherit any window from ISIN_A."""
        rows_a = [
            _row(ISIN_A, f"2024-01-{d:02d}", traded_value=5_000_000)
            for d in range(2, 22)
        ]
        # ISIN_B starts 10 days later.
        rows_b = [
            _row(ISIN_B, f"2024-01-{d:02d}", traded_value=2_000_000)
            for d in range(12, 22)
        ]
        raw = _df(*rows_a, *rows_b)
        prices, _, _ = build_universe(raw)

        # ISIN_B's first adv_20 must equal its own first traded_value (2M), not 5M.
        b_first_adv = (
            prices.loc[prices["isin"] == ISIN_B].sort_values("date")["adv_20"].iloc[0]
        )
        assert b_first_adv == pytest.approx(2_000_000)


# --------------------------------------------------------------------------- #
# TestUniverseMembership                                                       #
# --------------------------------------------------------------------------- #


class TestUniverseMembership:
    """membership contains exactly the (isin, date) pairs present in the input."""

    def test_membership_matches_input_pairs(self):
        raw = _df(
            _row(ISIN_A, "2024-01-02"),
            _row(ISIN_A, "2024-01-03"),
            _row(ISIN_B, "2024-01-02"),
        )
        _, membership, _ = build_universe(raw)
        assert set(zip(membership["isin"], membership["date"].astype(str))) == {
            (ISIN_A, "2024-01-02"),
            (ISIN_A, "2024-01-03"),
            (ISIN_B, "2024-01-02"),
        }

    def test_membership_has_no_duplicates(self):
        raw = _df(
            _row(ISIN_A, "2024-01-02"),
            _row(ISIN_A, "2024-01-02"),  # duplicate row
        )
        _, membership, _ = build_universe(raw)
        assert len(membership) == 1

    def test_membership_schema(self):
        raw = _df(_row(ISIN_A, "2024-01-02"))
        _, membership, _ = build_universe(raw)
        assert list(membership.columns) == list(UNIVERSE_MEMBERSHIP_SCHEMA)

    def test_membership_only_contains_dates_in_input(self):
        """membership must NOT contain dates absent from the input (no forward-projection)."""
        raw = _df(
            _row(ISIN_A, "2024-01-02"),
            _row(ISIN_A, "2024-01-05"),  # gap: Jan 03, 04 missing
        )
        _, membership, _ = build_universe(raw)
        dates = set(membership["date"].dt.strftime("%Y-%m-%d"))
        assert "2024-01-03" not in dates
        assert "2024-01-04" not in dates


# --------------------------------------------------------------------------- #
# TestIsinSymbolMap                                                            #
# --------------------------------------------------------------------------- #


class TestIsinSymbolMap:
    """isin_symbol_map must correctly track renames and per-symbol date ranges."""

    def test_single_symbol_single_row(self):
        raw = _df(
            _row(ISIN_A, "2024-01-02", symbol="ALPHA"),
            _row(ISIN_A, "2024-01-03", symbol="ALPHA"),
        )
        _, _, isin_map = build_universe(raw)
        assert len(isin_map) == 1
        row = isin_map.iloc[0]
        assert row["isin"] == ISIN_A
        assert row["symbol"] == "ALPHA"
        assert row["first_date"] == pd.Timestamp("2024-01-02")
        assert row["last_date"] == pd.Timestamp("2024-01-03")

    def test_rename_produces_two_rows_for_same_isin(self):
        """When a ticker renames, the same ISIN appears with two different symbols.
        This is the setup for T8 criterion 3 (ISIN continuity across rename)."""
        raw = _df(
            _row(ISIN_A, "2022-01-03", symbol="OLDNAME"),
            _row(ISIN_A, "2022-06-01", symbol="OLDNAME"),
            _row(ISIN_A, "2022-06-02", symbol="NEWNAME"),
            _row(ISIN_A, "2023-01-02", symbol="NEWNAME"),
        )
        _, _, isin_map = build_universe(raw)
        isin_rows = (
            isin_map[isin_map["isin"] == ISIN_A]
            .sort_values("first_date")
            .reset_index(drop=True)
        )
        assert len(isin_rows) == 2

        old_row = isin_rows.iloc[0]
        assert old_row["symbol"] == "OLDNAME"
        assert old_row["first_date"] == pd.Timestamp("2022-01-03")
        assert old_row["last_date"] == pd.Timestamp("2022-06-01")

        new_row = isin_rows.iloc[1]
        assert new_row["symbol"] == "NEWNAME"
        assert new_row["first_date"] == pd.Timestamp("2022-06-02")
        assert new_row["last_date"] == pd.Timestamp("2023-01-02")

    def test_multiple_isins_independent_map_rows(self):
        raw = _df(
            _row(ISIN_A, "2024-01-02", symbol="ALPHA"),
            _row(ISIN_B, "2024-01-02", symbol="BETA"),
            _row(ISIN_C, "2024-01-02", symbol="GAMMA"),
        )
        _, _, isin_map = build_universe(raw)
        assert len(isin_map) == 3
        assert set(isin_map["isin"]) == {ISIN_A, ISIN_B, ISIN_C}

    def test_isin_symbol_map_schema(self):
        raw = _df(_row(ISIN_A, "2024-01-02", symbol="ALPHA"))
        _, _, isin_map = build_universe(raw)
        assert list(isin_map.columns) == list(ISIN_SYMBOL_MAP_SCHEMA)


# --------------------------------------------------------------------------- #
# TestEmptyInput                                                               #
# --------------------------------------------------------------------------- #


class TestEmptyInput:
    """Empty adjusted_df must return three empty DataFrames with correct schemas."""

    def _empty_adjusted(self):
        return pd.DataFrame(
            columns=[c for c in PRICES_ADJUSTED_SCHEMA if c != "adv_20"]
        )

    def test_empty_input_returns_three_empty_frames(self):
        prices, membership, isin_map = build_universe(self._empty_adjusted())
        assert prices.empty
        assert membership.empty
        assert isin_map.empty

    def test_empty_prices_has_correct_columns(self):
        prices, _, _ = build_universe(self._empty_adjusted())
        assert list(prices.columns) == list(PRICES_ADJUSTED_SCHEMA)

    def test_empty_membership_has_correct_columns(self):
        _, membership, _ = build_universe(self._empty_adjusted())
        assert list(membership.columns) == list(UNIVERSE_MEMBERSHIP_SCHEMA)

    def test_empty_isin_map_has_correct_columns(self):
        _, _, isin_map = build_universe(self._empty_adjusted())
        assert list(isin_map.columns) == list(ISIN_SYMBOL_MAP_SCHEMA)


# --------------------------------------------------------------------------- #
# TestSchemaCompleteness                                                       #
# --------------------------------------------------------------------------- #


class TestSchemaCompleteness:
    """Output column sets must exactly match the spec schemas."""

    def _sample(self):
        return _df(
            _row(ISIN_A, "2024-01-02", traded_value=5_000_000),
            _row(ISIN_A, "2024-01-03", traded_value=6_000_000),
            _row(ISIN_B, "2024-01-02", traded_value=3_000_000),
        )

    def test_prices_has_adv20_and_all_schema_columns(self):
        prices, _, _ = build_universe(self._sample())
        assert list(prices.columns) == list(PRICES_ADJUSTED_SCHEMA)
        assert "adv_20" in prices.columns

    def test_prices_adv20_is_non_negative(self):
        prices, _, _ = build_universe(self._sample())
        assert (prices["adv_20"] >= 0).all()

    def test_membership_has_exactly_two_columns(self):
        _, membership, _ = build_universe(self._sample())
        assert list(membership.columns) == list(UNIVERSE_MEMBERSHIP_SCHEMA)

    def test_isin_map_has_exactly_four_columns(self):
        _, _, isin_map = build_universe(self._sample())
        assert list(isin_map.columns) == list(ISIN_SYMBOL_MAP_SCHEMA)

    def test_prices_preserves_all_intermediate_columns(self):
        """All columns that T5 outputs must still be present in T6 output."""
        intermediate = [c for c in PRICES_ADJUSTED_SCHEMA if c != "adv_20"]
        prices, _, _ = build_universe(self._sample())
        for col in intermediate:
            assert col in prices.columns, f"Missing column from T5 pass-through: {col}"

    def test_adv20_values_are_finite(self):
        prices, _, _ = build_universe(self._sample())
        assert np.isfinite(prices["adv_20"].to_numpy()).all()
