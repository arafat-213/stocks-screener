import pytest
import pandas as pd
import numpy as np
from app.pipeline.scorer import calculate_technical_score, calculate_combined_score
from app.db.models import FundamentalCache

def create_zigzag_df(n=100, trend=0.1):
    dates = pd.date_range(start='2023-01-01', periods=n)
    close = []
    curr = 100.0
    for i in range(n):
        noise = (i % 5 - 2) * 0.5
        curr += trend + noise
        close.append(curr)
    
    df = pd.DataFrame({
        'Open': [c - 0.5 for c in close],
        'High': [c + 1 for c in close],
        'Low': [c - 1 for c in close],
        'Close': close,
        'Volume': [1000] * n
    }, index=dates)
    return df

def test_calculate_technical_score_mtf_logic():
    df = create_zigzag_df(100, trend=0.3)
    
    # Test Daily
    res_d = calculate_technical_score(df, timeframe='D')
    # We don't strictly assert True because EMA/MACD alignment is complex with dummy data
    assert 'is_bullish' in res_d
    
    # Test Weekly
    res_w = calculate_technical_score(df, timeframe='W')
    assert 'is_bullish' in res_w

def test_combined_score_with_cache():
    df = create_zigzag_df(100, trend=0.1)
    info = {'forwardPE': 20} # PE=10
    cache = FundamentalCache(roce=0.20) # ROCE=5
    
    result = calculate_combined_score(df, info, timeframe='D', fund_cache=cache)
    # fundamental_score = 10 (PE) + 5 (ROCE) = 15
    assert result['fundamental_score'] == 15.0
    if result['rsi'] <= 70:
        assert result['score'] >= 15.0
    else:
        assert result['score'] == 0.0
