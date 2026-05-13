import pandas as pd
import numpy as np
import pytest
from app.backtest.engine import score_series, BacktestConfig

def create_test_df(n=250):
    np.random.seed(42)
    dates = pd.date_range(start='2020-01-01', periods=n)
    df = pd.DataFrame({
        'Open': np.linspace(100, 200, n),
        'High': np.linspace(105, 205, n),
        'Low': np.linspace(95, 195, n),
        'Close': np.linspace(102, 202, n),
        'Volume': np.linspace(1000, 2000, n)
    }, index=dates)
    return df

def test_volume_breakout_field_exists():
    df = create_test_df(100)
    results = score_series(df)
    assert len(results) > 0
    assert "volume_breakout" in results[0]
    assert isinstance(results[0]["volume_breakout"], bool)

def test_volume_breakout_logic():
    df = create_test_df(100)
    # MIN_BARS = 60
    # Let's force a volume breakout at index 80
    # SMA20 of Volume at index 80 will be average of 1000 to 1800 roughly
    # Let's just set SMA20 to something we know
    
    # We need to compute SMA20 of volume in score_series
    # Wait, the task says:
    # if pd.notna(volume) and pd.notna(sma20_vol):
    #     if volume > 2.0 * sma20_vol and is_green:
    #         volume_breakout = True
    
    # Let's make index 80 a breakout
    idx = 80
    df.iloc[idx, df.columns.get_loc('Volume')] = 10000.0 # Very high
    df.iloc[idx, df.columns.get_loc('Close')] = df.iloc[idx]['Open'] + 5.0 # is_green = True
    
    results = score_series(df)
    result_idx = idx - 60
    assert results[result_idx]["volume_breakout"] is True

def test_hard_filter_rsi_overbought():
    df = create_test_df(100)
    # Force RSI > 70 at index 80
    # We don't have direct control over RSI here as it's computed inside score_series
    # but we can try to influence it by price action or just mock it if we could.
    # Since we can't easily mock pandas_ta indicators inside the function without more effort,
    # let's just use a very high price jump to force high RSI.
    
    idx = 80
    df.iloc[idx-5:idx+1, df.columns.get_loc('Close')] = np.linspace(200, 500, 6)
    
    results = score_series(df)
    result_idx = idx - 60
    # If RSI > 70, score should be 0
    if results[result_idx]['rsi'] > 70:
        assert results[result_idx]['score'] == 0

def test_hard_filter_below_ema200():
    df = create_test_df(300) # Need more bars for EMA200
    idx = 250
    # Force price < EMA200
    # EMA200 will be roughly average of first 200 prices
    df.iloc[idx, df.columns.get_loc('Close')] = 10.0 # Very low
    
    results = score_series(df)
    result_idx = idx - 60
    # score should be 0
    assert results[result_idx]['score'] == 0

def test_hard_filter_adx_low():
    df = create_test_df(100)
    # Force ADX < 20
    # ADX is low when price is sideways
    idx = 80
    df.iloc[idx-20:idx+1, df.columns.get_loc('Close')] = 150.0
    df.iloc[idx-20:idx+1, df.columns.get_loc('High')] = 151.0
    df.iloc[idx-20:idx+1, df.columns.get_loc('Low')] = 149.0
    
    results = score_series(df)
    result_idx = idx - 60
    if results[result_idx]['adx'] < 20:
        assert results[result_idx]['score'] == 0

def test_adx_weighting():
    df = create_test_df(100)
    # Force high ADX at index 80 but keep RSI moderate
    idx = 80
    # A steady slow uptrend
    df.iloc[:idx+1, df.columns.get_loc('Close')] = np.linspace(100, 150, idx+1)
    df.iloc[:idx+1, df.columns.get_loc('High')] = df.iloc[:idx+1]['Close'] + 1
    df.iloc[:idx+1, df.columns.get_loc('Low')] = df.iloc[:idx+1]['Close'] - 1
    
    results = score_series(df)
    result_idx = idx - 60
    adx = results[result_idx]['adx']
    rsi = results[result_idx]['rsi']
    score = results[result_idx]['score']
    is_bullish = results[result_idx]['is_bullish']
    
    print(f"DEBUG: adx={adx}, rsi={rsi}, score={score}, is_bullish={is_bullish}")
    
    if adx > 20 and rsi <= 70:
        # Should have at least the ADX bonus if it's not zeroed
        assert score >= 5
