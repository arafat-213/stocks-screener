"""T1 round-trip tests for the bhavcopy storage contract.

Offline only — synthetic frames, a tmp root, no network (CLAUDE.md Rule 4).
Verifies schema + values are preserved across write/read for each of the three
logical tables, plus filter pushdown and idempotent (no-duplicate) rewrites.
"""

import pandas as pd
import pytest

from app.data.bhavcopy import store


def _prices_frame() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    rows = []
    for isin, sym in [("INE111A01011", "AAA"), ("INE222B01012", "BBB")]:
        for i, d in enumerate(dates):
            base = 100.0 + i
            rows.append(
                {
                    "isin": isin,
                    "symbol": sym,
                    "date": d,
                    "open": base,
                    "high": base + 2,
                    "low": base - 2,
                    "close": base + 1,
                    "close_raw": base + 1,
                    "close_tr": base + 1.5,
                    "volume": 1000 + i,
                    "traded_value": (base + 1) * (1000 + i),
                    "adv_20": (base + 1) * 1000.0,
                    "adj_factor": 1.0,
                    "tr_factor": 1.0,
                    "series": "EQ",
                }
            )
    return pd.DataFrame(rows)


def _membership_frame() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    rows = [
        {"isin": isin, "date": d}
        for isin in ("INE111A01011", "INE222B01012")
        for d in dates
    ]
    return pd.DataFrame(rows)


def _isin_map_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "isin": "INE111A01011",
                "symbol": "AAA",
                "first_date": pd.Timestamp("2020-01-01"),
                "last_date": pd.Timestamp("2020-01-03"),
            },
            {
                "isin": "INE222B01012",
                "symbol": "BBB",
                "first_date": pd.Timestamp("2020-01-01"),
                "last_date": pd.Timestamp("2020-01-03"),
            },
        ]
    )


def _assert_schema(df: pd.DataFrame, schema: dict[str, str]) -> None:
    assert list(df.columns) == list(schema), "column set/order must match contract"
    for col, dtype in schema.items():
        assert str(df[col].dtype) == dtype, f"{col}: {df[col].dtype} != {dtype}"


def test_prices_roundtrip(tmp_path):
    src = _prices_frame()
    store.write_prices_adjusted(src, root=tmp_path)
    got = store.read_prices_adjusted(root=tmp_path)
    _assert_schema(got, store.PRICES_ADJUSTED_SCHEMA)

    key = ["isin", "date"]
    a = src.sort_values(key).reset_index(drop=True)
    b = got.sort_values(key).reset_index(drop=True)[a.columns]
    # dtypes are asserted by _assert_schema above; here we verify values survive.
    pd.testing.assert_frame_equal(a, b, check_like=False, check_dtype=False)


def test_prices_filter_pushdown(tmp_path):
    store.write_prices_adjusted(_prices_frame(), root=tmp_path)

    one = store.read_prices_adjusted(root=tmp_path, isins=["INE111A01011"])
    assert set(one["isin"]) == {"INE111A01011"}

    ranged = store.read_prices_adjusted(
        root=tmp_path, start="2020-01-02", end="2020-01-02"
    )
    assert set(ranged["date"]) == {pd.Timestamp("2020-01-02")}


def test_prices_rewrite_is_idempotent(tmp_path):
    src = _prices_frame()
    store.write_prices_adjusted(src, root=tmp_path)
    store.write_prices_adjusted(src, root=tmp_path)  # same partitions again
    got = store.read_prices_adjusted(root=tmp_path)
    assert len(got) == len(src), "rewrite must overwrite partitions, not duplicate"


def test_membership_roundtrip_and_date_filter(tmp_path):
    src = _membership_frame()
    store.write_universe_membership(src, root=tmp_path)

    got = store.read_universe_membership(root=tmp_path)
    _assert_schema(got, store.UNIVERSE_MEMBERSHIP_SCHEMA)
    assert "year" not in got.columns, "partition col must not leak into schema"

    key = ["isin", "date"]
    a = src.sort_values(key).reset_index(drop=True)
    b = got.sort_values(key).reset_index(drop=True)[a.columns]
    pd.testing.assert_frame_equal(a, b, check_dtype=False)

    one_day = store.read_universe_membership(root=tmp_path, date="2020-01-02")
    assert set(one_day["date"]) == {pd.Timestamp("2020-01-02")}
    assert len(one_day) == 2


def test_isin_map_roundtrip_and_filter(tmp_path):
    src = _isin_map_frame()
    store.write_isin_symbol_map(src, root=tmp_path)

    got = store.read_isin_symbol_map(root=tmp_path)
    _assert_schema(got, store.ISIN_SYMBOL_MAP_SCHEMA)
    pd.testing.assert_frame_equal(
        src.sort_values("isin").reset_index(drop=True),
        got.sort_values("isin").reset_index(drop=True)[src.columns],
        check_dtype=False,
    )

    one = store.read_isin_symbol_map(root=tmp_path, isins=["INE222B01012"])
    assert list(one["isin"]) == ["INE222B01012"]


def test_read_empty_returns_typed_empty_frames(tmp_path):
    _assert_schema(
        store.read_prices_adjusted(root=tmp_path), store.PRICES_ADJUSTED_SCHEMA
    )
    _assert_schema(
        store.read_universe_membership(root=tmp_path),
        store.UNIVERSE_MEMBERSHIP_SCHEMA,
    )
    _assert_schema(
        store.read_isin_symbol_map(root=tmp_path), store.ISIN_SYMBOL_MAP_SCHEMA
    )


def test_missing_column_fails_loud(tmp_path):
    bad = _prices_frame().drop(columns=["close_tr"])
    with pytest.raises(ValueError, match="missing required columns"):
        store.write_prices_adjusted(bad, root=tmp_path)
