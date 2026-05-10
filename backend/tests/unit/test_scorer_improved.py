import pytest
import pandas as pd
from app.pipeline.scorer import calculate_fundamental_score, calculate_technical_score, calculate_combined_score
from app.db.models import FundamentalCache

def test_calculate_fundamental_score_improved():
    # Test PE (Max 10)
    assert calculate_fundamental_score({'forwardPE': 20}) == 10.0  # < 25
    assert calculate_fundamental_score({'forwardPE': 35}) == 6.0   # < 40
    assert calculate_fundamental_score({'forwardPE': 50}) == 2.0   # < 60
    assert calculate_fundamental_score({'forwardPE': 65}) == 0.0   # >= 60
    
    # Test Pledge (Max 5)
    assert calculate_fundamental_score({'pledgedPercent': 0.0}) == 5.0   # == 0
    assert calculate_fundamental_score({'pledgedPercent': 0.05}) == 3.0  # < 0.10
    assert calculate_fundamental_score({'pledgedPercent': 0.15}) == 1.0  # < 0.20
    assert calculate_fundamental_score({'pledgedPercent': 0.25}) == 0.0  # >= 0.20
    
    # Test ROE (Max 5)
    assert calculate_fundamental_score({'returnOnEquity': 0.20}) == 5.0  # > 0.15
    assert calculate_fundamental_score({'returnOnEquity': 0.12}) == 2.0  # > 0.10
    assert calculate_fundamental_score({'returnOnEquity': 0.05}) == 0.0
    
    # Test with fund_cache (ROCE and DE)
    cache = FundamentalCache(roce=0.20, de_ratio=0.3)
    # ROCE (5) + DE (5) = 10
    assert calculate_fundamental_score({}, fund_cache=cache) == 10.0
    
    # Combined with cache
    info = {'forwardPE': 20, 'pledgedPercent': 0.0, 'returnOnEquity': 0.20}
    # PE(10) + Pledge(5) + ROE(5) + ROCE(5) + DE(5) = 30
    assert calculate_fundamental_score(info, fund_cache=cache) == 30.0

def test_timeframe_score_ceiling():
    # 100 days of data
    dates = pd.date_range(start='2023-01-01', periods=100)
    # Strong uptrend
    close = [100 + i for i in range(100)]
    df = pd.DataFrame({
        'Open': [c-1 for c in close], 
        'High': [c+1 for c in close], 
        'Low': [c-2 for c in close], 
        'Close': close, 
        'Volume': [1000]*100
    }, index=dates)
    
    # W and M should be capped at 70
    res_w = calculate_technical_score(df, timeframe='W')
    if res_w['is_bullish']:
        assert res_w['score'] == 70.0
    
    res_m = calculate_technical_score(df, timeframe='M')
    if res_m['is_bullish']:
        assert res_m['score'] == 70.0

def test_combined_score_with_cache():
    dates = pd.date_range(start='2023-01-01', periods=100)
    close = [100 + i for i in range(100)]
    df = pd.DataFrame({
        'Open': [c-1 for c in close], 
        'High': [c+1 for c in close], 
        'Low': [c-2 for c in close], 
        'Close': close, 
        'Volume': [1000]*100
    }, index=dates)
    
    info = {'forwardPE': 20} # PE=10
    cache = FundamentalCache(roce=0.20) # ROCE=5
    
    result = calculate_combined_score(df, info, timeframe='D', fund_cache=cache)
    # fundamental_score = 10 (PE) + 5 (ROCE) = 15
    assert result['fundamental_score'] == 15.0
    # Score should be Technical (max 70) + 15
    assert result['score'] >= 15.0
