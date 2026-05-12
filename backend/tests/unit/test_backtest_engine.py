import pandas as pd
import numpy as np
import pytest
from app.backtest.engine import score_series, BacktestConfig

def create_dummy_df(n=200):
    np.random.seed(42)
    dates = pd.date_range(start='2020-01-01', periods=n)
    # Create somewhat realistic trending data to avoid all NaNs/zeros
    close = 100 + np.cumsum(np.random.randn(n))
    df = pd.DataFrame({
        'Open': close * 0.99,
        'High': close * 1.01,
        'Low': close * 0.98,
        'Close': close,
        'Volume': np.random.uniform(1000, 5000, n)
    }, index=dates)
    return df

def test_score_series_returns_list():
    df = create_dummy_df(100)
    results = score_series(df)
    assert isinstance(results, list)
    # MIN_BARS = 60, so for 100 bars we expect 100 - 60 = 40 results
    assert len(results) == 40
    if len(results) > 0:
        first = results[0]
        assert "score" in first
        assert "is_bullish" in first
        assert "date" in first
        assert "rsi" in first
        assert "adx" in first
        assert "close" in first

def test_score_series_no_future_leak():
    # Use more bars to let indicators stabilize a bit
    df = create_dummy_df(300)
    results_full = score_series(df)
    
    # Take a point in the middle (e.g., index 150)
    # result index will be 150 - 60 = 90
    test_idx = 150
    result_idx = test_idx - 60
    expected_score_at_test = results_full[result_idx]['score']
    
    # Score truncated df (only up to test_idx)
    df_truncated = df.iloc[:test_idx+1]
    results_truncated = score_series(df_truncated)
    actual_score_at_test = results_truncated[-1]['score']
    
    # They should be identical if no future leak occurs
    # Note: EMA/RSI are recursive, but if the full history from start is present in both, 
    # they should be identical.
    assert abs(expected_score_at_test - actual_score_at_test) < 1e-6

def test_score_series_with_fundamentals():
    class MockFundCache:
        def __init__(self):
            self.roe = 0.20
            self.roce = 0.20
            self.de_ratio = 0.1
            self.pe = 15
            self.pledged = 0
            
    fund_cache = MockFundCache()
    # Mocking calculate_fundamental_score behavior:
    # ROE > 15% -> 5pts
    # ROCE > 15% -> 5pts
    # DE < 0.5 -> 5pts
    # (PE and Pledged need to be in an info dict or handled by cache)
    
    # Wait, looking at scorer.py:
    # pe = to_float(info.get('forwardPE') or info.get('trailingPE'))
    # pledged = to_float(info.get('pledgedPercent'))
    
    # So pe and pledged are ONLY from info.
    
    config = BacktestConfig(include_fundamentals=True)
    df = create_dummy_df(100)
    
    # results = score_series(df, fund_cache=fund_cache, config=config)
    # calculate_fundamental_score(None, fund_cache=fund_cache) will be called.
    # It will get roe, roce, de from fund_cache.
    # It will get pe, pledged from None (info), which results in 0.
    # So fund_score should be 5+5+5 = 15.
    
    results = score_series(df, fund_cache=fund_cache, config=config)
    
    # Check if scores are higher than default
    results_no_fund = score_series(df)
    
    for r_fund, r_no_fund in zip(results, results_no_fund):
        assert r_fund['score'] == r_no_fund['score'] + 15.0

def test_score_series_min_bars():
    df = create_dummy_df(50)
    results = score_series(df)
    assert len(results) == 0
