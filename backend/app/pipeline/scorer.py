import pandas_ta as ta
import pandas as pd
from app.pipeline.utils import to_float

def calculate_fundamental_score(info: dict) -> float:
    """
    Calculates fundamental score (Max 30 pts)
    - P/E Score (Max 20 pts):
        pe < 25: +20
        pe < 50: +15
        pe < 100: +5
        pe >= 100: -5
        pe is None: +0
    - Promoter Pledge (Max 10 pts):
        pledged < 5%: +10
        pledged < 15%: +5
        pledged < 20%: +2
        Otherwise (>= 20% or None): +0
    """
    score = 0
    
    # P/E Score (Max 20 pts)
    pe = to_float(info.get('forwardPE') or info.get('trailingPE'))
    if pe is not None:
        if pe < 25:
            score += 20
        elif pe < 50:
            score += 15
        elif pe < 100:
            score += 5
        elif pe >= 100:
            score -= 5
            
    # Promoter Pledge (Max 10 pts)
    # yfinance pledgedPercent is usually a float (e.g. 0.05 for 5%)
    pledged = to_float(info.get('pledgedPercent'))
    if pledged is not None:
        if pledged < 0.05:
            score += 10
        elif pledged < 0.15:
            score += 5
        elif pledged < 0.20:
            score += 2
            
    return float(score)

def calculate_technical_score(df: pd.DataFrame) -> dict:
    """
    Calculates technical sub-score (Max 70 pts)
    - EMA Alignment: 20 pts
    - MACD: 20 pts
    - RSI 14: 15 pts
    - Volume: 15 pts
    """
    if len(df) < 60:
        return {
            "score": 0.0, 
            "rsi": 0.0, 
            "macd": 0.0, 
            "ema_signal": "neutral", 
            "volume_signal": "neutral",
            "rsi_signal": "neutral"
        }
        
    # Ensure we don't modify the original dataframe in a way that affects caller
    df = df.copy()
        
    # Calculate Indicators using pandas-ta
    df.ta.ema(length=5, append=True)
    df.ta.ema(length=13, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=26, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.rsi(length=14, append=True)
    # Use explicit name for volume SMA to avoid collision with price SMA
    df['VOL_SMA_20'] = df['Volume'].rolling(window=20).mean()
    
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    
    score = 0
    ema_signal = "neutral"
    volume_signal = "neutral"
    rsi_signal = "neutral"
    
    # 1. EMA Alignment (20 pts)
    # Bullish: EMA_5 > EMA_13 > EMA_26 AND Price > EMA_26
    ema5 = latest.get('EMA_5')
    ema13 = latest.get('EMA_13')
    ema26 = latest.get('EMA_26')
    price = latest.get('Close')
    if pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26):
        if ema5 > ema13 > ema26 and price > ema26:
            score += 20
            ema_signal = "bullish"
        elif ema5 < ema13 < ema26:
            ema_signal = "bearish"
        
    # 2. MACD (20 pts)
    # Bullish: MACD > Signal AND MACD > 0
    macd_line = latest.get('MACD_12_26_9')
    signal_line = latest.get('MACDs_12_26_9')
    if pd.notna(macd_line) and pd.notna(signal_line):
        if macd_line > signal_line and macd_line > 0:
            score += 20
        
    # 3. RSI 14 (15 pts)
    # Better RSI usage: 
    # - Recovery from <30 AND price > EMA20
    # - Crossing 50 from below
    rsi = latest.get('RSI_14')
    prev_rsi = prev.get('RSI_14')
    ema20 = latest.get('EMA_20')
    
    if pd.notna(rsi) and pd.notna(prev_rsi):
        # Check for recovery in last 5 days
        recent_rsi = df['RSI_14'].tail(5)
        was_oversold = any(recent_rsi < 30)
        
        recovering = was_oversold and rsi > 30 and price > ema20
        crossing_50 = prev_rsi <= 50 and rsi > 50
        
        if recovering:
            score += 15
            rsi_signal = "bullish_recovery"
        elif crossing_50:
            score += 15
            rsi_signal = "bullish_crossing"
        elif rsi > 50:
            # Maintain some points for strong RSI even if not a "new" signal
            score += 5
            rsi_signal = "bullish_strong"
        
    # 4. Volume (15 pts)
    # Better Volume usage:
    # - Volume > 1.5x 20-day avg AND candle is green
    volume = latest.get('Volume')
    sma20_vol = latest.get('VOL_SMA_20')
    is_green = latest.get('Close') > latest.get('Open')
    
    if pd.notna(volume) and pd.notna(sma20_vol):
        if volume > 1.5 * sma20_vol and is_green:
            score += 15
            volume_signal = "bullish"
        
    return {
        "score": float(score),
        "rsi": float(rsi) if pd.notna(rsi) else 0.0,
        "macd": float(macd_line) if pd.notna(macd_line) else 0.0,
        "ema_signal": ema_signal,
        "volume_signal": volume_signal,
        "rsi_signal": rsi_signal
    }

def calculate_combined_score(df: pd.DataFrame, info: dict) -> dict:
    """
    Combines Technical (70%) and Fundamental (30%) scores.
    Final Score range: 0-100.
    """
    ta_data = calculate_technical_score(df)
    fund_score = calculate_fundamental_score(info)
    
    combined_score = ta_data['score'] + fund_score
    # Ensure final score is in range 0-100
    combined_score = max(0.0, min(100.0, combined_score))
    
    # Update dict with combined results
    ta_data['technical_score'] = ta_data['score']
    ta_data['fundamental_score'] = fund_score
    ta_data['score'] = combined_score
    
    return ta_data
