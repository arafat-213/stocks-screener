import pytest
import pandas as pd
import numpy as np
from app.pipeline.scorer import calculate_technical_score, calculate_fundamental_score, calculate_combined_score

def test_calculate_fundamental_score():
    # Test P/E cases (Max 10)
    assert calculate_fundamental_score({'forwardPE': 20}) == 10.0  # < 25
    assert calculate_fundamental_score({'trailingPE': 35}) == 6.0   # < 40 (Actual logic pe < 40)
    assert calculate_fundamental_score({'forwardPE': 50}) == 2.0    # < 60
    assert calculate_fundamental_score({'forwardPE': 80}) == 0.0    # >= 60
    assert calculate_fundamental_score({}) == 0.0                  # None
    
    # Test Pledge cases (Max 5)
    assert calculate_fundamental_score({'pledgedPercent': 0.0}) == 5.0   # == 0
    assert calculate_fundamental_score({'pledgedPercent': 0.05}) == 3.0  # < 10%
    assert calculate_fundamental_score({'pledgedPercent': 0.15}) == 1.0  # < 20%
    assert calculate_fundamental_score({'pledgedPercent': 0.25}) == 0.0  # >= 20%
    
    # Combined Fundamental (PE 10 + Pledge 5 = 15)
    info = {'forwardPE': 20, 'pledgedPercent': 0.0}
    assert calculate_fundamental_score(info) == 15.0

def test_calculate_technical_score_insufficient_data():
    df = pd.DataFrame({'Close': range(50)})
    result = calculate_technical_score(df)
    assert result['score'] == 0.0
    assert result['ema_signal'] == 'neutral'

def test_calculate_technical_score_bullish():
    # Create a bullish dataframe
    # 100 days of data
    dates = pd.date_range(start='2023-01-01', periods=100)
    # Price accelerating up to ensure MACD > Signal
    close = [100 + (i**1.2) for i in range(100)]
    # Volume high on last day
    volume = [1000] * 99 + [5000]
    
    df = pd.DataFrame({
        'Open': [c - 0.1 for c in close], # Ensure green candles
        'High': [c + 2 for c in close],
        'Low': [c - 2 for c in close],
        'Close': close,
        'Volume': volume
    }, index=dates)
    
    result = calculate_technical_score(df)
    
    # Debug print if needed (though I can't see it easily)
    # print(result)
    
    assert result['ema_signal'] == 'bullish'
    assert result['volume_signal'] == 'bullish'
    # It should be 60.0 now (EMA 20 + MACD 20 + RSI 5 + Volume 15)
    assert result['score'] == 60.0

def test_calculate_combined_score():
    # Mock DF that should give 60 pts technical
    dates = pd.date_range(start='2023-01-01', periods=100)
    close = [100 + (i**1.2) for i in range(100)]
    volume = [1000] * 99 + [5000]
    df = pd.DataFrame({
        'Open': [c - 0.1 for c in close], # Ensure green candles
        'High': [c + 2 for c in close],
        'Low': [c - 2 for c in close],
        'Close': close,
        'Volume': volume
    }, index=dates)
    
    # Mock Info that should give 15 pts (PE 10 + Pledge 5)
    info = {'forwardPE': 20, 'pledgedPercent': 0.0}
    
    result = calculate_combined_score(df, info)
    
    # Tech (60) + Fund (15) = 75
    assert result['score'] == 75.0
    assert result['technical_score'] == 60.0
    assert result['fundamental_score'] == 15.0

def test_calculate_combined_score_clipping():
    # Test high PE clipping (should be 0, not -5)
    dates = pd.date_range(start='2023-01-01', periods=100)
    close = [100] * 100
    volume = [1000] * 100
    df = pd.DataFrame({
        'Open': close, 'High': close, 'Low': close, 'Close': close, 'Volume': volume
    }, index=dates)
    
    # High PE gives 0
    info = {'forwardPE': 200}
    
    result = calculate_combined_score(df, info)
    # Tech score will likely be 0 (no trend)
    # Combined = 0 + 0 = 0
    assert result['score'] == 0.0
    assert result['fundamental_score'] == 0.0
