import pandas_ta as ta
import pandas as pd
from app.pipeline.utils import to_float

def calculate_fundamental_score(info: dict, fund_cache=None) -> float:
    """
    Calculates fundamental score (Max 30 pts budget)
    - PE: 10 pts (Max if PE < 25, 0 if PE > 60)
    - Pledge: 5 pts (Max if Pledge == 0, 0 if Pledge > 20%)
    - ROE: 5 pts (Max if ROE > 15%)
    - ROCE: 5 pts (Max if ROCE > 15%)
    - Debt/Equity: 5 pts (Max if D/E < 0.5)
    """
    if info is None:
        info = {}
        
    score = 0.0
    
    # 1. PE Score (Max 10 pts)
    pe = to_float(info.get('forwardPE') or info.get('trailingPE'))
    if pe is not None:
        if pe < 25:
            score += 10
        elif pe < 40:
            score += 6
        elif pe < 60:
            score += 2
            
    # 2. Promoter Pledge (Max 5 pts)
    # yfinance pledgedPercent is usually a float (e.g. 0.05 for 5%)
    pledged = to_float(info.get('pledgedPercent'))
    if pledged is not None:
        if pledged == 0:
            score += 5
        elif pledged < 0.10:
            score += 3
        elif pledged < 0.20:
            score += 1

    # 3. ROE Score (Max 5 pts)
    roe = None
    if fund_cache and fund_cache.roe is not None:
        roe = fund_cache.roe
    else:
        roe = to_float(info.get('returnOnEquity'))
    
    if roe is not None:
        if roe > 0.15:
            score += 5
        elif roe > 0.10:
            score += 2

    # 4. ROCE Score (Max 5 pts)
    roce = None
    if fund_cache and fund_cache.roce is not None:
        roce = fund_cache.roce
    
    if roce is not None:
        if roce > 0.15:
            score += 5
        elif roce > 0.10:
            score += 2

    # 5. Debt/Equity Score (Max 5 pts)
    de = None
    if fund_cache and fund_cache.de_ratio is not None:
        de = fund_cache.de_ratio
    else:
        de = to_float(info.get('debtToEquity'))
        if de is not None and de > 5: # Handle percentage format (e.g. 50 instead of 0.5)
            de = de / 100.0
            
    if de is not None:
        if de < 0.5:
            score += 5
        elif de < 1.0:
            score += 2
            
    return float(score)

def calculate_technical_score(df: pd.DataFrame, timeframe: str = 'D') -> dict:
    """
    Calculates technical sub-score (Max 70 pts)
    - EMA Alignment: 20 pts
    - MACD: 20 pts
    - RSI 14: 15 pts
    - Volume: 15 pts
    
    Timeframe tiered logic for is_bullish:
    - 'D': strict alignment
    - 'W': RSI > 50 and Price > EMA26
    - 'M': RSI > 50 and (Price > EMA13 or Price > EMA26)
    """
    if len(df) < 1:
        return {
            "score": 0.0, "rsi": 0.0, "macd": 0.0, "ema_signal": "neutral",
            "volume_signal": "neutral", "rsi_signal": "neutral", "is_bullish": False,
            "ema5_level": None, "ema13_level": None, "ema20_level": None, "ema26_level": None,
            "atr": None,
            "momentum_1m": None, "momentum_3m": None, "momentum_6m": None, "momentum_12m": None,
            "adx": None, "above_200ema": None, "ema_slope_20": None
        }

    # Ensure we don't modify the original dataframe in a way that affects caller
    df = df.copy()
        
    # Calculate Indicators using pandas-ta
    df.ta.ema(length=5, append=True)
    df.ta.ema(length=13, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=26, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.adx(length=14, append=True)
    # Use explicit name for volume SMA to avoid collision with price SMA
    if 'Volume' in df.columns:
        df['VOL_SMA_20'] = df['Volume'].rolling(window=20).mean()
    else:
        df['VOL_SMA_20'] = pd.Series(dtype='float64')
    
    # EMA Slope (20 periods)
    # df.ta.ema(length=20, append=True) was already called above
    ema20_col = 'EMA_20'
    ema_slope_20 = None
    if ema20_col in df.columns and len(df) >= 6:
        v1 = df[ema20_col].iloc[-1]
        v6 = df[ema20_col].iloc[-6]
        if pd.notna(v1) and pd.notna(v6):
            ema_slope_20 = float((v1 - v6) / 5)

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    
    score = 0
    ema_signal = "neutral"
    volume_signal = "neutral"
    rsi_signal = "neutral"
    is_bullish = False
    
    ema5 = latest.get('EMA_5')
    ema13 = latest.get('EMA_13')
    ema20 = latest.get('EMA_20')
    ema26 = latest.get('EMA_26')
    ema200 = latest.get('EMA_200')
    price = latest.get('Close')
    macd_line = latest.get('MACD_12_26_9')
    signal_line = latest.get('MACDs_12_26_9')
    rsi = latest.get('RSI_14')
    prev_rsi = prev.get('RSI_14')
    atr = latest.get('ATRr_14')
    adx = latest.get('ADX_14')
    
    # Momentum (lookback from full df)
    momentum_1m  = ((price / df['Close'].iloc[-22]  - 1) * 100) if len(df) >= 22  else None
    momentum_3m  = ((price / df['Close'].iloc[-64]  - 1) * 100) if len(df) >= 64  else None
    momentum_6m  = ((price / df['Close'].iloc[-127] - 1) * 100) if len(df) >= 127 else None
    momentum_12m = ((price / df['Close'].iloc[-253] - 1) * 100) if len(df) >= 253 else None

    # Above 200 EMA
    above_200ema = (price > ema200) if pd.notna(ema200) else None

    # 52-Week High/Low and Resistance
    week52_high = None
    week52_low = None
    pct_from_52w_high = None
    pct_from_52w_low = None
    resistance_level = None
    pct_from_resistance = None
    
    if len(df) >= 252:
        recent_252 = df['Close'].tail(252)
        week52_high = float(recent_252.max())
        week52_low = float(recent_252.min())
        pct_from_52w_high = (price / week52_high - 1) * 100
        pct_from_52w_low = (price / week52_low - 1) * 100
        
    # Resistance: Highest close in the year prior to the last 20 bars
    if len(df) >= 260:
        resistance_level = float(df['Close'].iloc[-260:-20].max())
        pct_from_resistance = (price / resistance_level - 1) * 100

    # Volume Breakout (2x 20-day SMA on green day)
    volume_breakout = False
    volume = latest.get('Volume')
    sma20_vol = latest.get('VOL_SMA_20')
    is_green = (latest.get('Close') > latest.get('Open')) if pd.notna(latest.get('Close')) and pd.notna(latest.get('Open')) else False
    if pd.notna(volume) and pd.notna(sma20_vol):
        if volume > 2.0 * sma20_vol and is_green:
            volume_breakout = True

    min_bars = 24 if timeframe == 'M' else 60
    if len(df) >= min_bars:
        if timeframe == 'D':
            # 1. EMA Alignment (Tiered Scoring)
            prev_ema5 = prev.get('EMA_5')
            prev_ema13 = prev.get('EMA_13')

            fresh_ema_cross = (
                pd.notna(ema5) and pd.notna(ema13) and
                pd.notna(prev_ema5) and pd.notna(prev_ema13) and
                ema5 > ema13 and prev_ema5 <= prev_ema13
            )

            pullback_to_ema20 = (
                pd.notna(ema20) and pd.notna(price) and
                pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and
                ema5 > ema13 > ema26 and
                abs(price - ema20) / ema20 < 0.02
            )

            if fresh_ema_cross:
                score += 20
                ema_signal = "bullish_cross"
            elif pullback_to_ema20:
                score += 15
                ema_signal = "bullish_pullback"
            elif pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and ema5 > ema13 > ema26 and price > ema26:
                score += 8
                ema_signal = "bullish"
            elif pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and ema5 < ema13 < ema26:
                ema_signal = "bearish"
                
            # 2. MACD (15 pts — decoupled from EMA cross)
            # When EMA cross and MACD cross occur on the same bar they measure
            # the same price event. Cap the combined MACD bonus to 8 pts in that
            # case to avoid awarding 35 pts for a single momentum burst.
            prev_macd = prev.get('MACD_12_26_9')
            prev_signal_line = prev.get('MACDs_12_26_9')

            if pd.notna(macd_line) and pd.notna(signal_line):
                fresh_macd_cross = (
                    pd.notna(prev_macd) and pd.notna(prev_signal_line) and
                    macd_line > signal_line and prev_macd <= prev_signal_line
                )
                if fresh_macd_cross and fresh_ema_cross:
                    # Correlated same-day event: award partial credit only
                    score += 8
                elif fresh_macd_cross:
                    score += 15
                elif macd_line > signal_line and macd_line > 0:
                    score += 10
                elif macd_line > signal_line and macd_line < 0:
                    score += 5
                
            # 3. RSI 14 (15 pts)
            if pd.notna(rsi) and pd.notna(prev_rsi):
                # Check for recovery in last 5 days
                recent_rsi = df['RSI_14'].tail(5)
                was_oversold = any(recent_rsi < 30)
                
                recovering = was_oversold and rsi > 30 and pd.notna(ema20) and price > ema20
                crossing_50 = prev_rsi <= 50 and rsi > 50
                
                if recovering and fresh_ema_cross:
                    score += 15   # capped at RSI budget; EMA cross already scored separately
                    rsi_signal = "bullish_recovery_confirmed"
                elif recovering:
                    score += 15
                    rsi_signal = "bullish_recovery"
                elif crossing_50:
                    score += 10
                    rsi_signal = "bullish_crossing"
                elif 50 < rsi <= 65:
                    score += 5
                    rsi_signal = "bullish_strong"
                elif 65 < rsi <= 68:
                    score += 0 # Extended RSI — not penalised but not rewarded; momentum may be exhausted
                    rsi_signal = "bullish_extended"
                elif rsi > 68:
                    pass
                
            # 4. Volume (15 pts)
            # (Note: we already checked volume_breakout above, but this is for the 70pt score)
            if pd.notna(volume) and pd.notna(sma20_vol):
                if volume > 2.0 * sma20_vol and is_green:
                    score += 15
                    volume_signal = "bullish"
            
            # 5. Trend Quality: ADX + 3-Month Momentum (max 5 pts)
            # ADX alone measures current trend strength; combining it with recent
            # momentum ensures we're rewarding continuation moves, not temporary spikes.
            trend_pts = 0
            if pd.notna(adx):
                if adx >= 35:
                    trend_pts += 3
                elif adx >= 25:
                    trend_pts += 2
                elif adx >= 20:
                    trend_pts += 1
            if momentum_3m is not None:
                if momentum_3m > 15:
                    trend_pts += 2
                elif momentum_3m > 5:
                    trend_pts += 1
            score += min(trend_pts, 5)  # Cap at 5 to preserve 70pt max
                    
            # Define is_bullish for D
            is_bullish = (
                (fresh_ema_cross or pullback_to_ema20 or 
                 (pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and ema5 > ema13 > ema26)) and
                pd.notna(macd_line) and pd.notna(signal_line) and macd_line > signal_line and
                pd.notna(rsi) and rsi > 45
            )

        elif timeframe == 'W':
            # Pure technical trend indicator (max 70 pts)
            is_bullish = (pd.notna(rsi) and rsi > 50 and pd.notna(ema26) and price > ema26)
            score = 70.0 if is_bullish else 0.0
            ema_signal = "bullish" if is_bullish else "neutral"

        elif timeframe == 'M':
            # Pure technical trend indicator (max 70 pts)
            is_bullish = (pd.notna(rsi) and rsi > 50 and (
                (pd.notna(ema13) and price > ema13) or (pd.notna(ema26) and price > ema26)
            ))
            score = 70.0 if is_bullish else 0.0
            ema_signal = "bullish" if is_bullish else "neutral"
        
    return {
        "score": float(score),
        "rsi": float(rsi) if pd.notna(rsi) else 0.0,
        "macd": float(macd_line) if pd.notna(macd_line) else 0.0,
        "ema_signal": ema_signal,
        "volume_signal": volume_signal,
        "rsi_signal": rsi_signal,
        "is_bullish": bool(is_bullish),
        "ema5_level": float(ema5) if pd.notna(ema5) else None,
        "ema13_level": float(ema13) if pd.notna(ema13) else None,
        "ema20_level": float(ema20) if pd.notna(ema20) else None,
        "ema26_level": float(ema26) if pd.notna(ema26) else None,
        "atr": float(atr) if pd.notna(atr) else None,
        "momentum_1m": float(momentum_1m) if momentum_1m is not None else None,
        "momentum_3m": float(momentum_3m) if momentum_3m is not None else None,
        "momentum_6m": float(momentum_6m) if momentum_6m is not None else None,
        "momentum_12m": float(momentum_12m) if momentum_12m is not None else None,
        "adx": float(adx) if pd.notna(adx) else None,
        "above_200ema": bool(above_200ema) if above_200ema is not None else None,
        "ema_slope_20": float(ema_slope_20) if ema_slope_20 is not None else None,
        "week52_high": week52_high,
        "week52_low": week52_low,
        "pct_from_52w_high": float(pct_from_52w_high) if pct_from_52w_high is not None else None,
        "pct_from_52w_low": float(pct_from_52w_low) if pct_from_52w_low is not None else None,
        "resistance_level": resistance_level,
        "pct_from_resistance": float(pct_from_resistance) if pct_from_resistance is not None else None,
        "volume_breakout": bool(volume_breakout),
    }


def calculate_combined_score(df: pd.DataFrame, info: dict, timeframe: str = 'D', fund_cache=None) -> dict:
    """
    Combines Technical and Fundamental scores.
    Final Score range: 0-100.
    
    - 'D': Technical (max 70 pts) + Fundamental (max 30 pts) = 100 pts.
    - 'W'/'M': Pure technical trend indicator (max 70 pts).
    """
    ta_data = calculate_technical_score(df, timeframe=timeframe)
    
    fund_score = 0.0
    if timeframe == 'D':
        fund_score = calculate_fundamental_score(info, fund_cache=fund_cache)
    
    combined_score = ta_data['score'] + fund_score
    
    # Hard Filter: RSI must not be overbought (> 80)
    # 70-80 is the normal territory for strong trending stocks; only cap true extremes.
    if ta_data.get('rsi', 0) > 80:
        combined_score = 0.0
        
    # Ensure final score is in range 0-100
    combined_score = max(0.0, min(100.0, combined_score))
    
    # Update dict with combined results
    ta_data['technical_score'] = ta_data['score']
    ta_data['fundamental_score'] = fund_score
    ta_data['score'] = combined_score
    ta_data['combined_score'] = combined_score
    
    return ta_data

