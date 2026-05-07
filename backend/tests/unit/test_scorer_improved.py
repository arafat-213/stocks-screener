import pytest
import pandas as pd
import numpy as np
from app.pipeline.scorer import calculate_technical_score

def create_base_df(periods=100):
    dates = pd.date_range(start='2023-01-01', periods=periods)
    close = [100.0] * periods
    df = pd.DataFrame({
        'Open': close,
        'High': close,
        'Low': close,
        'Close': close,
        'Volume': [1000.0] * periods
    }, index=dates)
    return df

def test_rsi_recovery_score():
    """
    RSI recovering from <30 AND price > EMA20 should get score.
    """
    df = create_base_df(120)
    # Create a sharp downtrend to push RSI < 30
    close = [100.0] * 70
    for i in range(20):
        close.append(close[-1] * 0.90) # 10% drop each day to be sure
    
    # Recover: massive spike to cross EMA20
    # Current price is approx 100 * (0.9^20) = 12.15
    # EMA20 will be much higher.
    # Let's just set the last few prices to something high.
    last_price = close[-1]
    close.append(last_price * 2.0)
    close.append(last_price * 3.0)
    close.append(last_price * 4.0)
    
    # Update DF
    df = pd.DataFrame({
        'Open': [c * 0.95 for c in close],
        'High': [c * 1.05 for c in close],
        'Low': [c * 0.90 for c in close],
        'Close': close,
        'Volume': [1000.0] * len(close)
    })
    
    result = calculate_technical_score(df)
    assert result['rsi_signal'] == "bullish_recovery"

def test_ema_alignment_with_price_score():
    """
    EMA5 > EMA13 > EMA26 AND price > EMA26 should get pts.
    If price <= EMA26, it should get 0 or less for EMA component.
    """
    df = create_base_df(120)
    # Create a strong uptrend to get the stack
    close = [100.0]
    for i in range(110):
        close.append(close[-1] * 1.01)
    
    # Pull back on last day: price drops below EMA26
    # EMA26 will be roughly the average of last 26 days.
    # Let's just drop price significantly.
    close.append(close[-1] * 0.8) # 20% crash
    
    df = pd.DataFrame({
        'Open': close,
        'High': [c * 1.01 for c in close],
        'Low': [c * 0.99 for c in close],
        'Close': close,
        'Volume': [1000.0] * len(close)
    })
    
    result = calculate_technical_score(df)
    # Even if stack is still bullish (EMA5 > EMA13 > EMA26), 
    # price > EMA26 check should fail.
    assert result['ema_signal'] == "neutral" # or "bullish" if it only looks at stack, but user wants price > EMA26

def test_volume_green_spike_score():
    """
    Volume > 1.5x 20-day avg AND candle is green should get 15 pts.
    """
    df = create_base_df(100)
    # Ensure last price is high enough for RSI > 50
    df.iloc[-1, df.columns.get_loc('Open')] = 104.0
    df.iloc[-1, df.columns.get_loc('Close')] = 105.0
    df.iloc[-1, df.columns.get_loc('Volume')] = 2000.0
    
    result = calculate_technical_score(df)
    assert result['volume_signal'] == "bullish"
    assert result['score'] >= 15.0
    
    # Now test RED candle spike - should NOT get points
    df.iloc[-1, df.columns.get_loc('Open')] = 106.0
    df.iloc[-1, df.columns.get_loc('Close')] = 105.0
    result = calculate_technical_score(df)
    assert result['volume_signal'] == "neutral"
