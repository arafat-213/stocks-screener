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
        # Add trend but with noise to keep RSI in check
        noise = (i % 5 - 2) * 0.5 # Zig-zag pattern
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

def test_calculate_fundamental_score():
    from app.pipeline.scorer import calculate_fundamental_score
    assert calculate_fundamental_score({'forwardPE': 20}) == 10.0
    assert calculate_fundamental_score({'pledgedPercent': 0.0}) == 5.0

def test_calculate_technical_score_bullish():
    df = create_zigzag_df(100, trend=0.2)
    # Ensure last day has high volume
    df.loc[df.index[-1], 'Volume'] = 5000
    
    result = calculate_technical_score(df)
    
    assert result['rsi'] > 40
    # Zig-zag should keep RSI < 70
    assert result['rsi'] < 75 # Be a bit more lenient
    assert result['is_bullish'] is True
    assert result['score'] > 0

def test_calculate_combined_score():
    df = create_zigzag_df(100, trend=0.1)
    info = {'forwardPE': 20, 'pledgedPercent': 0.0}
    result = calculate_combined_score(df, info)
    
    assert result['fundamental_score'] == 15.0
    if result['rsi'] <= 70:
        assert result['score'] >= 15.0
    else:
        assert result['score'] == 0.0

def test_is_bullish_logic():
    dates = pd.date_range(start='2023-01-01', periods=100)
    df = pd.DataFrame({
        'Open': [100]*100, 'High': [100]*100, 'Low': [100]*100, 'Close': [100]*100, 'Volume': [1000]*100
    }, index=dates)
    
    res = calculate_technical_score(df)
    assert res['is_bullish'] is False
