import pytest
import pandas as pd
import numpy as np
from app.pipeline.scorer import calculate_technical_score, calculate_fundamental_score, calculate_combined_score

def test_calculate_fundamental_score():
    # Test P/E cases
    assert calculate_fundamental_score({'forwardPE': 20}) == 20.0  # < 25
    assert calculate_fundamental_score({'trailingPE': 40}) == 15.0  # < 50
    assert calculate_fundamental_score({'forwardPE': 80}) == 5.0   # < 100
    assert calculate_fundamental_score({'forwardPE': 120}) == -5.0 # >= 100
    assert calculate_fundamental_score({}) == 0.0                  # None
    
    # Test Pledge cases
    assert calculate_fundamental_score({'pledgedPercent': 0.04}) == 10.0 # < 5%
    assert calculate_fundamental_score({'pledgedPercent': 0.10}) == 5.0  # < 15%
    assert calculate_fundamental_score({'pledgedPercent': 0.18}) == 2.0  # < 20%
    assert calculate_fundamental_score({'pledgedPercent': 0.25}) == 0.0  # >= 20%
    
    # Combined Fundamental
    info = {'forwardPE': 20, 'pledgedPercent': 0.04}
    assert calculate_fundamental_score(info) == 30.0

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
        'Open': close,
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
    # It should be 70.0 now
    assert result['score'] == 70.0

def test_calculate_combined_score():
    # Mock DF that should give 70 pts
    dates = pd.date_range(start='2023-01-01', periods=100)
    close = [100 + (i**1.2) for i in range(100)]
    volume = [1000] * 99 + [5000]
    df = pd.DataFrame({
        'Open': close,
        'High': [c + 2 for c in close],
        'Low': [c - 2 for c in close],
        'Close': close,
        'Volume': volume
    }, index=dates)
    
    # Mock Info that should give 30 pts
    info = {'forwardPE': 20, 'pledgedPercent': 0.01}
    
    result = calculate_combined_score(df, info)
    
    assert result['score'] == 100.0
    assert result['technical_score'] == 70.0
    assert result['fundamental_score'] == 30.0

def test_calculate_combined_score_clipping():
    # Test negative fundamental score clipping
    dates = pd.date_range(start='2023-01-01', periods=100)
    close = [100] * 100
    volume = [1000] * 100
    df = pd.DataFrame({
        'Open': close, 'High': close, 'Low': close, 'Close': close, 'Volume': volume
    }, index=dates)
    
    # High PE gives -5
    info = {'forwardPE': 200}
    
    result = calculate_combined_score(df, info)
    # Tech score will likely be 0 (no trend, no volume spike)
    # Combined = 0 + (-5) = -5, clipped to 0
    assert result['score'] == 0.0
    assert result['fundamental_score'] == -5.0
