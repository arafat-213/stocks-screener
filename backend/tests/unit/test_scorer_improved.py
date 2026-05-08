import pytest
import pandas as pd
import numpy as np
from app.pipeline.scorer import calculate_technical_score

def test_momentum_indicators():
    # Need at least 253 rows for 12m momentum (252 bars)
    dates = pd.date_range(start='2020-01-01', periods=300)
    # Price starts at 100 and increases by 1 each day
    close = [float(100 + i) for i in range(300)]
    df = pd.DataFrame({'Close': close, 'Open': close, 'High': close, 'Low': close, 'Volume': 1000.0}, index=dates)
    
    result = calculate_technical_score(df)
    
    # 1m momentum (21 bars ago): (close_now / close_21_ago - 1) * 100
    close_now = 399.0
    close_21_ago = close[300-22] # 100 + 278 = 378
    
    expected_1m = (399.0 / 378.0 - 1) * 100
    assert pytest.approx(result['momentum_1m']) == expected_1m
    
    # 3m momentum (63 bars ago) -> iloc[-64]
    close_63_ago = close[300-64] # 100 + 236 = 336
    expected_3m = (399.0 / 336.0 - 1) * 100
    assert pytest.approx(result['momentum_3m']) == expected_3m
    
    # 6m momentum (126 bars ago) -> iloc[-127]
    close_126_ago = close[300-127] # 100 + 173 = 273
    expected_6m = (399.0 / 273.0 - 1) * 100
    assert pytest.approx(result['momentum_6m']) == expected_6m
    
    # 12m momentum (252 bars ago) -> iloc[-253]
    close_252_ago = close[300-253] # 100 + 47 = 147
    expected_12m = (399.0 / 147.0 - 1) * 100
    assert pytest.approx(result['momentum_12m']) == expected_12m

def test_momentum_insufficient_data():
    df = pd.DataFrame({'Close': [100.0] * 50, 'Open': [100.0] * 50, 'High': [100.0] * 50, 'Low': [100.0] * 50, 'Volume': [1000.0] * 50})
    result = calculate_technical_score(df)
    assert result.get('momentum_12m') is None
    assert result.get('momentum_6m') is None
    assert result.get('momentum_1m') is not None # 50 > 21

def test_adx_ema_indicators():
    dates = pd.date_range(start='2020-01-01', periods=300)
    # Steady trend for ADX
    close = [float(100 + i) for i in range(300)]
    high = [float(c + 1) for c in close]
    low = [float(c - 1) for c in close]
    df = pd.DataFrame({'Close': close, 'Open': close, 'High': high, 'Low': low, 'Volume': 1000.0}, index=dates)
    
    result = calculate_technical_score(df)
    
    assert result['adx'] is not None
    assert result['above_200ema'] is True
    assert result['ema_slope_20'] is not None
    assert result['ema_slope_20'] > 0

def test_52w_stats_and_resistance():
    dates = pd.date_range(start='2020-01-01', periods=300)
    # Price is 100 for first 250 days, then jumps to 200
    close = [100.0] * 250 + [200.0] * 50
    df = pd.DataFrame({'Close': close, 'Open': close, 'High': close, 'Low': close, 'Volume': 1000.0}, index=dates)
    
    result = calculate_technical_score(df)
    
    assert result['week52_high'] == 200.0
    assert result['week52_low'] == 100.0
    assert result['pct_from_52w_high'] == 0.0
    assert result['pct_from_52w_low'] == 100.0
    
    # Resistance: iloc[-260:-20].max()
    # close[-260] is close[40] = 100.0
    # close[-20] is close[280] = 200.0
    # max([100.0]*210 + [200.0]*30) = 200.0
    # Wait, if close is 200.0 from 250 onwards, then from 250 to 280 (30 bars) it is 200.0
    assert result['resistance_level'] == 200.0
    assert result['pct_from_resistance'] == 0.0

def test_volume_breakout():
    df = pd.DataFrame({
        'Close': [100.0] * 20 + [110.0],
        'Open': [100.0] * 21,
        'High': [100.0] * 21,
        'Low': [100.0] * 21,
        'Volume': [100.0] * 20 + [300.0] # 3x SMA20
    })
    result = calculate_technical_score(df)
    assert result['volume_breakout'] is True

    # Test not green
    df.loc[20, 'Close'] = 90.0
    result = calculate_technical_score(df)
    assert result['volume_breakout'] is False

def test_insufficient_data_guards():
    df = pd.DataFrame({
        'Close': [100.0] * 10, 'Open': [100.0] * 10, 'High': [101.0] * 10, 'Low': [99.0] * 10, 'Volume': [1000.0] * 10
    })
    result = calculate_technical_score(df)
    assert result.get('adx') is None
    assert result.get('above_200ema') is None
    assert result.get('week52_high') is None
    assert result.get('resistance_level') is None
    assert result.get('momentum_1m') is None
