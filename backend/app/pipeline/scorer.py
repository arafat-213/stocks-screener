import pandas_ta as ta
import pandas as pd

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
    pe = info.get('forwardPE') or info.get('trailingPE')
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
    pledged = info.get('pledgedPercent')
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
            "volume_signal": "neutral"
        }
        
    # Ensure we don't modify the original dataframe in a way that affects caller
    df = df.copy()
        
    # Calculate Indicators using pandas-ta
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
    
    # 1. EMA Alignment (20 pts)
    # Bullish: EMA_5 > EMA_13 > EMA_26
    ema5 = latest.get('EMA_5')
    ema13 = latest.get('EMA_13')
    ema26 = latest.get('EMA_26')
    if pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26):
        if ema5 > ema13 > ema26:
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
    # Bullish: RSI > 50 (Strong), > 40 (Recovery)
    rsi = latest.get('RSI_14')
    if pd.notna(rsi):
        if rsi > 50:
            score += 15
        elif rsi > 40:
            score += 5
        
    # 4. Volume (15 pts)
    # Bullish: Volume > 20-day SMA of Volume
    volume = latest.get('Volume')
    sma20_vol = latest.get('SMA_20')
    if pd.notna(volume) and pd.notna(sma20_vol):
        if volume > sma20_vol:
            score += 15
            volume_signal = "bullish"
        
    return {
        "score": float(score),
        "rsi": float(rsi) if pd.notna(rsi) else 0.0,
        "macd": float(macd_line) if pd.notna(macd_line) else 0.0,
        "ema_signal": ema_signal,
        "volume_signal": volume_signal
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
