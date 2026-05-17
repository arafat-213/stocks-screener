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
    idx = pd.date_range("2024-01-01", periods=days, freq="B")
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

    with patch("app.pipeline.fetcher.fetch_stock_data", return_value=(mock_df, None)) as mock_fetch:
        result = cache.get("RELIANCE", append_ns=True, period="3y")

    mock_fetch.assert_called_once_with("RELIANCE", append_ns=True, period="3y", fetch_info=False)
    assert result is not None
    assert len(result) == 10
    assert cache._file_path("RELIANCE").exists()


def test_get_returns_none_when_fetch_fails(tmp_path):
    """fetch_stock_data returns (None, None) and no file exists → get() returns None."""
    cache = OHLCVCache(cache_dir=str(tmp_path))

    with patch("app.pipeline.fetcher.fetch_stock_data", return_value=(None, None)):
        result = cache.get("BADSTOCK", append_ns=True, period="3y")

    assert result is None
    assert not cache._file_path("BADSTOCK").exists()
