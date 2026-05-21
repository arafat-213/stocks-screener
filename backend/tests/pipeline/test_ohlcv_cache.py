import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from app.pipeline.ohlcv_cache import OHLCVCache

def test_ohlcv_cache_instantiates(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    assert cache is not None

def _make_df(days: int = 5) -> pd.DataFrame:
    """Helper: returns a minimal OHLCV DataFrame with a DatetimeIndex."""
    idx = pd.date_range("2024-01-01", periods=days, freq="D")
    return pd.DataFrame({
        "Open":   np.ones(days) * 100,
        "High":   np.ones(days) * 105,
        "Low":    np.ones(days) * 95,
        "Close":  np.ones(days) * 102,
        "Volume": np.ones(days, dtype=int) * 1_000_000,
    }, index=idx)


def test_stats_empty_cache(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    s = cache.stats()
    assert s["total_files"] == 0
    assert s["total_size_mb"] == 0.0
    assert s["oldest_file_date"] is None


def test_invalidate_single(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    df = _make_df()
    df.to_parquet(cache._file_path("RELIANCE"))
    assert cache._file_path("RELIANCE").exists()
    cache.invalidate("RELIANCE")
    assert not cache._file_path("RELIANCE").exists()


def test_invalidate_all(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    for sym in ["TCS", "INFY"]:
        _make_df().to_parquet(cache._file_path(sym))
    cache.invalidate_all()
    remaining = list(cache._root.glob("*.parquet"))
    assert remaining == []


def test_stats_after_write(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    _make_df(days=100).to_parquet(cache._file_path("HDFC"))
    s = cache.stats()
    assert s["total_files"] == 1
    assert s["total_size_mb"] > 0
    assert s["oldest_file_date"] is not None


def test_get_cold_miss_fetches_and_writes(tmp_path):
    """No parquet file → should call fetch_stock_data and write to disk."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    mock_df = _make_df(days=10)

    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(mock_df, None)) as mock_fetch:
        result = cache.get("RELIANCE", append_ns=True, period="3y")

    mock_fetch.assert_called_once_with("RELIANCE", append_ns=True, period="3y", fetch_info=False)
    assert result is not None
    assert len(result) == 10
    assert cache._file_path("RELIANCE").exists()


def test_get_returns_none_when_fetch_fails(tmp_path):
    """fetch_stock_data returns (None, None) and no file exists → get() returns None."""
    cache = OHLCVCache(cache_dir=str(tmp_path))

    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(None, None)):
        result = cache.get("BADSTOCK", append_ns=True, period="3y")

    assert result is None
    assert not cache._file_path("BADSTOCK").exists()

def test_get_cache_hit_no_network_call(tmp_path):
    """Fresh parquet file → return cached data, never call fetch_stock_data."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    # Write a file whose last row is within the past 24 hours
    now = pd.Timestamp.now(tz='UTC').replace(tzinfo=None)
    df = _make_df(days=5)
    # Start date is now - 4 days
    idx = pd.date_range(end=now.floor('D'), periods=len(df), freq="D")
    df.index = idx
    df.to_parquet(cache._file_path("TCS"))

    # Use a short period to avoid triggering backfill
    with patch("app.pipeline.ohlcv_cache.fetch_stock_data") as mock_fetch:
        result = cache.get("TCS", append_ns=True, period="5d")

    mock_fetch.assert_not_called()
    assert result is not None
    assert len(result) == 5


def test_get_triggers_backfill(tmp_path):
    """If requested period is longer than cached, trigger backfill."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    
    # Cache has 10 days of data
    now = pd.Timestamp.now(tz='UTC').replace(tzinfo=None)
    df = _make_df(days=10)
    idx = pd.date_range(end=now.floor('D'), periods=10, freq="D")
    df.index = idx
    df.to_parquet(cache._file_path("BACKFILL_STOCK"))
    
    # Mock backfill data (e.g., 20 more days)
    backfill_df = _make_df(days=20)
    backfill_idx = pd.date_range(end=idx[0] - pd.Timedelta(days=1), periods=20, freq="D")
    backfill_df.index = backfill_idx
    
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = backfill_df
    
    with patch("yfinance.Ticker", return_value=mock_ticker) as mock_yf:
        # Request 1 month (30 days), cache only has 10
        result = cache.get("BACKFILL_STOCK", append_ns=True, period="1mo")
        
    mock_yf.assert_called()
    assert result is not None
    assert len(result) == 30 # 10 original + 20 backfilled


def test_get_stale_file_triggers_incremental_fetch(tmp_path):
    """Stale parquet file → fetch only the tail and append to cached data."""
    cache = OHLCVCache(cache_dir=str(tmp_path))

    # Old data ending 5 days ago
    old_end = pd.Timestamp.now(tz='UTC').replace(tzinfo=None) - pd.Timedelta(days=5)
    old_df = _make_df(days=10)
    old_idx = pd.date_range(end=old_end.floor('D'), periods=len(old_df), freq="D")
    old_df.index = old_idx
    old_df.to_parquet(cache._file_path("INFY"))

    # Tail that yfinance would return for the missing window
    tail_idx = pd.date_range(start=old_idx[-1] + pd.Timedelta(days=1), periods=3, freq="D")
    tail_df = _make_df(days=3)
    tail_df.index = tail_idx

    mock_ticker = MagicMock()
    # First call might be backfill (if period is long), second is incremental
    # We'll use a short period to avoid backfill
    mock_ticker.history.return_value = tail_df

    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = cache.get("INFY", append_ns=True, period="10d")

    mock_ticker.history.assert_called_once()
    assert result is not None
    assert len(result) == 13  # 10 old + 3 new


def test_get_force_refresh_bypasses_fresh_cache(tmp_path):
    """force_refresh=True should re-fetch even if the cache is fresh."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    now = pd.Timestamp.now(tz='UTC').replace(tzinfo=None)
    df = _make_df(days=5)
    idx = pd.date_range(end=now.floor('D'), periods=len(df), freq="D")
    df.index = idx
    df.to_parquet(cache._file_path("WIPRO"))

    fresh_df = _make_df(days=20)
    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(fresh_df, None)) as mock_fetch:
        result = cache.get("WIPRO", append_ns=True, period="3y", force_refresh=True)

    mock_fetch.assert_called_once()
    assert len(result) == 20

def test_corrupt_parquet_is_deleted_and_refetched(tmp_path):
    """A corrupt Parquet file should be removed and a fresh fetch attempted."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    path = cache._file_path("CORRUPT")
    path.write_bytes(b"this is not a parquet file")

    fresh_df = _make_df(days=5)
    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(fresh_df, None)):
        result = cache.get("CORRUPT", append_ns=True, period="3y")

    assert result is not None
    assert len(result) == 5
    assert path.exists()  # re-written with valid data


def test_special_characters_in_symbol_name(tmp_path):
    """Symbols like ^NSEI must produce a valid filename."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    fresh_df = _make_df(days=5)
    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(fresh_df, None)):
        cache.get("^NSEI", append_ns=False, period="3y")

    files = list(cache._root.glob("*.parquet"))
    assert len(files) == 1
    assert "^" not in files[0].name  # caret must be sanitised


def test_empty_dataframe_from_fetch_is_not_written(tmp_path):
    """An empty DataFrame returned by yfinance should not be cached."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(pd.DataFrame(), None)):
        result = cache.get("EMPTY", append_ns=True, period="3y")

    assert result is None
    assert not cache._file_path("EMPTY").exists()


def test_incremental_no_new_data_returns_cached(tmp_path):
    """If the incremental fetch returns empty (market closed), serve the cached file."""
    cache = OHLCVCache(cache_dir=str(tmp_path))

    old_end = pd.Timestamp.now(tz='UTC').replace(tzinfo=None) - pd.Timedelta(days=3)
    old_df = _make_df(days=5)
    old_idx = pd.date_range(end=old_end.floor('D'), periods=5, freq="D")
    old_df.index = old_idx
    old_df.to_parquet(cache._file_path("STABLE"))

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()  # empty — weekend/holiday

    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = cache.get("STABLE", append_ns=True, period="3y")

    assert result is not None
    assert len(result) == 5  # original cached rows returned unchanged
