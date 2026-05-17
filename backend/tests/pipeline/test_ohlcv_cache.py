# backend/tests/pipeline/test_ohlcv_cache.py
import pytest
from app.pipeline.ohlcv_cache import OHLCVCache

def test_ohlcv_cache_instantiates(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    assert cache is not None
