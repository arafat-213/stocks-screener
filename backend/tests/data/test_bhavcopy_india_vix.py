"""v4/01 Part B — India VIX ingestion tests (yfinance ^INDIAVIX).

Offline only — the live fetch is injected via ``_history`` so no test touches the
network (CLAUDE.md §5). Encodes WHY (Rule 9): the parser must strip tz, drop source
NaNs (no fabricated levels), dedupe, and fail loud on an empty source; and the cached
VIX must merge into ``market_internals.india_vix`` by date with a real gap left as NaN.
"""

import numpy as np
import pandas as pd
import pytest

from app.data.bhavcopy import india_vix as iv
from app.data.bhavcopy import market_internals as mi
from app.data.bhavcopy import store

D1 = pd.Timestamp("2020-01-01")
D2 = pd.Timestamp("2020-01-02")
D3 = pd.Timestamp("2020-01-03")
_LIQUID = 6e7


def _yf_history(dates, closes, tz=None) -> pd.DataFrame:
    """A yfinance-style history frame: a datetime index + OHLC columns."""
    idx = pd.DatetimeIndex(dates, tz=tz, name="Date")
    return pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": 0},
        index=idx,
    )


def test_fetch_parses_strips_tz_drops_nan_and_sorts():
    hist = _yf_history(
        [D3, D1, D2], [18.0, 15.0, np.nan], tz="Asia/Kolkata"
    )  # out of order, one NaN, tz-aware
    out = iv.fetch_india_vix(_history=hist)
    assert list(out.columns) == ["date", "india_vix"]
    assert getattr(out["date"].dt, "tz", None) is None  # tz stripped
    # NaN (D2) dropped → only D1, D3, sorted ascending.
    assert out["date"].tolist() == [D1, D3]
    assert out["india_vix"].tolist() == [15.0, 18.0]


def test_fetch_dedupes_keeping_last():
    hist = _yf_history([D1, D1], [15.0, 99.0])
    out = iv.fetch_india_vix(_history=hist)
    assert len(out) == 1
    assert out.loc[0, "india_vix"] == 99.0  # keep="last"


def test_fetch_fails_loud_on_empty_source():
    with pytest.raises(ValueError, match="empty history"):
        iv.fetch_india_vix(_history=pd.DataFrame())


def test_fetch_fails_loud_on_missing_close():
    bad = pd.DataFrame({"Open": [1.0]}, index=pd.DatetimeIndex([D1]))
    with pytest.raises(ValueError, match="no 'Close' column"):
        iv.fetch_india_vix(_history=bad)


def test_backfill_writes_round_trip(tmp_path):
    hist = _yf_history([D1, D2, D3], [15.0, 16.0, 17.0])
    iv.backfill_india_vix(root=tmp_path, _history=hist)
    back = store.read_india_vix(root=tmp_path)
    assert list(back.columns) == list(store.INDIA_VIX_SCHEMA)
    assert back["india_vix"].tolist() == [15.0, 16.0, 17.0]


def test_read_missing_vix_cache_returns_empty(tmp_path):
    assert store.read_india_vix(root=tmp_path).empty


def _write_min_prices(root):
    """Minimal full-schema prices_adjusted for 1 ISIN over D1..D3 (A advances daily)."""
    rows = []
    for i, d in enumerate([D1, D2, D3]):
        c = 100.0 + i
        rows.append(
            {
                "isin": "INE111A01011",
                "symbol": "AAA",
                "date": d,
                "open": c,
                "high": c,
                "low": c,
                "close": c,
                "close_raw": c,
                "close_tr": c,
                "volume": 1000,
                "traded_value": c * 1000,
                "adv_20": _LIQUID,
                "adj_factor": 1.0,
                "tr_factor": 1.0,
                "series": "EQ",
                "instrument_id": "INE111A01011",
            }
        )
    store.write_prices_adjusted(pd.DataFrame(rows), root=root)


def test_backfill_from_store_merges_vix_with_gap_as_nan(tmp_path):
    """End-to-end: cached VIX folds into market_internals.india_vix; a trading day with
    no VIX (D3) stays NaN — never forward-filled (01 §3)."""
    _write_min_prices(tmp_path)
    iv.backfill_india_vix(
        root=tmp_path, _history=_yf_history([D1, D2], [15.0, 16.0])
    )  # D3 absent
    mi.backfill_from_store(root=tmp_path)

    out = store.read_market_internals(root=tmp_path).set_index("date")
    assert out.loc[D2, "india_vix"] == pytest.approx(16.0)
    assert np.isnan(out.loc[D3, "india_vix"])  # gap surfaced, not filled
