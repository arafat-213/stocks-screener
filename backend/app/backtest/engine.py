import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass
import datetime
from app.pipeline.scorer import calculate_fundamental_score

@dataclass
class BacktestConfig:
    score_threshold: float = 60.0      # minimum score to trigger a trade
    holding_days: int = 20             # trading days to hold
    stop_loss_pct: float = 7.0         # exit if price drops this % (0 = disabled)
    target_pct: float = 0.0            # exit if price rises this % (0 = disabled)
    include_fundamentals: bool = False  # use current fundamental data
    timeframe: str = 'D'               # 'D' only for now
    date_from: datetime.date = None    # filter signals after this date
    date_to: datetime.date = None      # filter signals before this date
    symbol_limit: int = None           # limit number of symbols to process

@dataclass
class TradeResult:
    symbol: str
    sector: str
    signal_date: datetime.date
    entry_date: datetime.date
    exit_date: datetime.date
    exit_reason: str          # 'holding_period' | 'stop_loss' | 'target'
    signal_score: float
    entry_price: float
    exit_price: float
    return_pct: float
    rsi_at_signal: float
    adx_at_signal: float
    ema_signal: str

def score_series(df: pd.DataFrame, fund_cache=None, config: BacktestConfig = None):
    """
    Computes technical and fundamental scores for a series of OHLCV data.
    O(n) implementation: compute indicators once, then iterate.
    """
    if df is None or len(df) < 60:
        return []

    # 1. Compute Indicators
    df = df.copy()
    df.ta.ema(length=5, append=True)
    df.ta.ema(length=13, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=26, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.adx(length=14, append=True)
    
    if 'Volume' in df.columns:
        df['VOL_SMA_20'] = df['Volume'].rolling(window=20).mean()
    else:
        df['VOL_SMA_20'] = pd.Series(dtype='float64')

    # Fundamental Score (computed once since we only have current data)
    fund_score = 0.0
    if config and config.include_fundamentals and fund_cache:
        # Mocking an 'info' dict since calculate_fundamental_score expects it
        # fund_cache should be an object with roe, roce, de_ratio etc.
        fund_score = calculate_fundamental_score(None, fund_cache=fund_cache)

    results = []
    MIN_BARS = 60
    
    # Pre-fetch column names to avoid repeated lookups
    ema5_col = 'EMA_5'
    ema13_col = 'EMA_13'
    ema20_col = 'EMA_20'
    ema26_col = 'EMA_26'
    macd_col = 'MACD_12_26_9'
    signal_col = 'MACDs_12_26_9'
    rsi_col = 'RSI_14'
    adx_col = 'ADX_14'
    vol_sma_col = 'VOL_SMA_20'
    
    # Iterate from MIN_BARS to end
    for i in range(MIN_BARS, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        score = 0.0
        ema_signal = "neutral"
        volume_signal = "neutral"
        rsi_signal = "neutral"
        is_bullish = False
        
        price = row['Close']
        open_price = row['Open']
        volume = row['Volume']
        
        ema5 = row.get(ema5_col)
        ema13 = row.get(ema13_col)
        ema20 = row.get(ema20_col)
        ema26 = row.get(ema26_col)
        macd_line = row.get(macd_col)
        signal_line = row.get(signal_col)
        rsi = row.get(rsi_col)
        prev_rsi = prev_row.get(rsi_col)
        adx = row.get(adx_col)
        sma20_vol = row.get(vol_sma_col)
        
        is_green = price > open_price
        
        # 1. EMA Alignment (20 pts)
        if pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26):
            if ema5 > ema13 > ema26 and price > ema26:
                score += 20
                ema_signal = "bullish"
            elif ema5 < ema13 < ema26:
                ema_signal = "bearish"
                
        # 2. MACD (20 pts)
        if pd.notna(macd_line) and pd.notna(signal_line):
            if macd_line > signal_line and macd_line > 0:
                score += 20
                
        # 3. RSI 14 (15 pts)
        if pd.notna(rsi) and pd.notna(prev_rsi):
            # was_oversold in last 5 bars
            recent_rsi = df[rsi_col].iloc[max(0, i-4):i+1]
            was_oversold = (recent_rsi < 30).any()
            
            recovering = was_oversold and rsi > 30 and pd.notna(ema20) and price > ema20
            crossing_50 = prev_rsi <= 50 and rsi > 50
            
            if recovering:
                score += 15
                rsi_signal = "bullish_recovery"
            elif crossing_50:
                score += 15
                rsi_signal = "bullish_crossing"
            elif rsi > 50:
                score += 5
                rsi_signal = "bullish_strong"
                
        # 4. Volume (15 pts)
        if pd.notna(volume) and pd.notna(sma20_vol):
            if volume > 1.5 * sma20_vol and is_green:
                score += 15
                volume_signal = "bullish"

        # is_bullish definition
        is_bullish = (
            pd.notna(macd_line) and macd_line > signal_line and macd_line > 0 and 
            pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and 
            ema5 > ema13 > ema26 and price > ema26
        )
        
        total_score = score + fund_score
        
        results.append({
            "date": df.index[i],
            "score": float(total_score),
            "is_bullish": bool(is_bullish),
            "rsi": float(rsi) if pd.notna(rsi) else 0.0,
            "adx": float(adx) if pd.notna(adx) else 0.0,
            "ema_signal": ema_signal,
            "volume_signal": volume_signal,
            "rsi_signal": rsi_signal,
            "close": float(price),
            "open": float(open_price)
        })
        
    return results
