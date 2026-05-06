import pandas_ta as ta
import pandas as pd

def calculate_technical_score(df: pd.DataFrame) -> dict:
    if len(df) < 60:
        return {"score": 0, "rsi": 0, "macd": 0, "ema_signal": "neutral", "volume_signal": "neutral"}
        
    # Calculate Indicators
    df.ta.ema(length=5, append=True)
    df.ta.ema(length=13, append=True)
    df.ta.ema(length=26, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.sma(close='Volume', length=20, append=True)
    
    latest = df.iloc[-1]
    
    score = 0
    ema_signal = "neutral"
    volume_signal = "neutral"
    
    # EMA Stack (25 points)
    if latest['EMA_5'] > latest['EMA_13'] > latest['EMA_26']:
        score += 25
        ema_signal = "bullish"
    elif latest['EMA_5'] < latest['EMA_13'] < latest['EMA_26']:
        ema_signal = "bearish"
        
    # MACD (25 points)
    macd_line = latest['MACD_12_26_9']
    signal_line = latest['MACDs_12_26_9']
    if macd_line > signal_line and macd_line > 0:
        score += 25
        
    # RSI (20 points)
    rsi = latest['RSI_14']
    if 40 <= rsi <= 60:
        score += 20 # Recovery zone
    elif rsi > 60:
        score += 10 # Overbought but strong
        
    # Volume (15 points)
    if latest['Volume'] > latest['SMA_20']:
        score += 15
        volume_signal = "bullish"
        
    # 52-week breakout proxy (15 points)
    high_52w = df['High'].tail(252).max()
    if latest['Close'] > (high_52w * 0.90):
        score += 15
        
    return {
        "score": score,
        "rsi": float(rsi) if not pd.isna(rsi) else 0.0,
        "macd": float(macd_line) if not pd.isna(macd_line) else 0.0,
        "ema_signal": ema_signal,
        "volume_signal": volume_signal
    }
