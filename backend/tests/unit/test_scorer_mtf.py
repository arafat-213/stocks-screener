import pytest
import pandas as pd
import numpy as np
from app.pipeline.scorer import calculate_technical_score, calculate_combined_score

def create_sample_df(rows=100, bullish=True):
    """Helper to create a sample dataframe with indicators if needed, or raw price data."""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=rows)
    t = np.arange(rows)
    if bullish:
        # Accelerating trend ensures MACD > Signal
        close = 100 + 1 * t + 0.01 * (t**2)
    else:
        # Decelerating trend ensures MACD < Signal
        close = 200 - 1 * t - 0.01 * (t**2)
    
    df = pd.DataFrame({
        'Open': close - 1,
        'High': close + 2,
        'Low': close - 2,
        'Close': close,
        'Volume': [1000] * rows
    }, index=dates)
    return df

def test_daily_scorer_is_bullish():
    """Daily timeframe should include is_bullish in output."""
    df = create_sample_df(bullish=True)
    # Mocking price and EMAs to satisfy daily is_bullish logic:
    # is_bullish = (macd_line > signal_line and macd_line > 0 and ema5 > ema13 > ema26 and price > ema26)
    # Our create_sample_df(bullish=True) should naturally create this alignment after pandas-ta runs.
    
    result = calculate_technical_score(df, timeframe='D')
    assert "is_bullish" in result
    assert isinstance(result["is_bullish"], bool)

def test_weekly_scorer_logic():
    """Weekly timeframe uses RSI > 50 and Price > EMA26."""
    df = create_sample_df(bullish=True)
    # In bullish df, RSI will be high (>50) and Price will be above EMA26
    result = calculate_technical_score(df, timeframe='W')
    
    assert result["is_bullish"] is True
    assert result["score"] == 70.0

    # Bearish case
    df_bear = create_sample_df(bullish=False)
    result_bear = calculate_technical_score(df_bear, timeframe='W')
    assert result_bear["is_bullish"] is False
    assert result_bear["score"] == 0.0

def test_monthly_scorer_logic():
    """Monthly timeframe uses RSI > 50 and (Price > EMA13 or Price > EMA26)."""
    df = create_sample_df(bullish=True)
    result = calculate_technical_score(df, timeframe='M')
    
    assert result["is_bullish"] is True
    assert result["score"] == 70.0

    # Bearish case
    df_bear = create_sample_df(bullish=False)
    result_bear = calculate_technical_score(df_bear, timeframe='M')
    assert result_bear["is_bullish"] is False
    assert result_bear["score"] == 0.0

def test_combined_score_timeframe_handling():
    """Combined score should skip fundamental score if timeframe != 'D'."""
    df = create_sample_df(bullish=True)
    info = {"forwardPE": 10, "pledgedPercent": 0.0} # Should give 30 fundamental points
    
    # Daily: should include fundamental
    res_d = calculate_combined_score(df, info, timeframe='D')
    assert res_d["fundamental_score"] == 30.0
    assert res_d["score"] > 70.0 # technical + fundamental
    
    # Weekly: should NOT include fundamental
    res_w = calculate_combined_score(df, info, timeframe='W')
    assert res_w["fundamental_score"] == 0.0
    assert res_w["score"] == 70.0 # Just technical (capped at 70 for bullish W/M)
