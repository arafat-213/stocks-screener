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

def simulate_trades(symbol: str, sector: str, df: pd.DataFrame, scored_dates: list[dict], config: BacktestConfig):
    """
    Simulates trades based on scored signals.
    Entry: Next day's Open.
    Exit: SL, Target, or Holding Period.
    """
    trades = []
    last_exit_idx = -1
    
    # Pre-map dates to indices for faster lookup
    date_to_idx = {date: i for i, date in enumerate(df.index)}
    
    for signal in scored_dates:
        signal_date = signal['date']
        signal_idx = date_to_idx.get(signal_date)
        
        if signal_idx is None or signal_idx <= last_exit_idx:
            continue
            
        if signal['score'] >= config.score_threshold:
            # Entry: Next trading day's Open price
            entry_idx = signal_idx + 1
            if entry_idx >= len(df):
                break
                
            entry_price = df.iloc[entry_idx]['Open']
            entry_date = df.index[entry_idx]
            
            # Exit conditions
            exit_price = None
            exit_date = None
            exit_reason = 'holding_period'
            
            stop_loss_pct = config.stop_loss_pct
            target_pct = config.target_pct
            
            stop_loss_price = entry_price * (1 - stop_loss_pct / 100) if stop_loss_pct > 0 else 0
            target_price = entry_price * (1 + target_pct / 100) if target_pct > 0 else float('inf')
            
            # Walk forward up to config.holding_days
            final_idx = min(entry_idx + config.holding_days - 1, len(df) - 1)
            
            for k in range(entry_idx, final_idx + 1):
                day_low = df.iloc[k]['Low']
                day_high = df.iloc[k]['High']
                
                # Check Stop Loss first (conservative)
                if day_low <= stop_loss_price:
                    exit_price = stop_loss_price
                    exit_date = df.index[k]
                    exit_reason = 'stop_loss'
                    last_exit_idx = k
                    break
                
                # Check Profit Target
                if day_high >= target_price:
                    exit_price = target_price
                    exit_date = df.index[k]
                    exit_reason = 'target'
                    last_exit_idx = k
                    break
            
            if exit_price is None:
                # Exit on last day's Close
                exit_idx = final_idx
                exit_price = df.iloc[exit_idx]['Close']
                exit_date = df.index[exit_idx]
                exit_reason = 'holding_period'
                last_exit_idx = exit_idx
                
            return_pct = ((exit_price - entry_price) / entry_price) * 100
            
            trades.append(TradeResult(
                symbol=symbol,
                sector=sector,
                signal_date=signal_date.date() if hasattr(signal_date, 'date') else signal_date,
                entry_date=entry_date.date() if hasattr(entry_date, 'date') else entry_date,
                exit_date=exit_date.date() if hasattr(exit_date, 'date') else exit_date,
                exit_reason=exit_reason,
                signal_score=signal['score'],
                entry_price=float(entry_price),
                exit_price=float(exit_price),
                return_pct=float(return_pct),
                rsi_at_signal=signal['rsi'],
                adx_at_signal=signal['adx'],
                ema_signal=signal['ema_signal']
            ))
            
    return trades

def compute_metrics(trades: list[TradeResult], benchmark_data: pd.DataFrame, config: BacktestConfig):
    """
    Calculates aggregate metrics and equity curve.
    Fixed position size: ₹10,000 per trade.
    """
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "median_return_pct": 0.0,
            "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "total_return_pct": 0.0,
            "benchmark_return_pct": 0.0,
            "equity_curve": []
        }
        
    returns = [t.return_pct for t in trades]
    total_trades = len(trades)
    wins = [r for r in returns if r > 0]
    win_rate = (len(wins) / total_trades) * 100
    
    avg_return_pct = sum(returns) / total_trades
    median_return_pct = float(pd.Series(returns).median())
    best_trade_pct = max(returns)
    worst_trade_pct = min(returns)
    
    # Strategy total return = sum of all trade returns (simplified as requested)
    total_return_pct = sum(returns)
    
    # Sharpe Ratio (simplified, assuming 0 risk-free rate)
    if len(returns) > 1:
        std_dev = pd.Series(returns).std()
        sharpe_ratio = (avg_return_pct / std_dev) * (252**0.5) if std_dev > 0 else 0
    else:
        sharpe_ratio = 0.0
        
    # Benchmark return
    benchmark_return_pct = 0.0
    if benchmark_data is not None and len(benchmark_data) > 1:
        start_price = benchmark_data.iloc[0]['Close']
        end_price = benchmark_data.iloc[-1]['Close']
        benchmark_return_pct = ((end_price - start_price) / start_price) * 100
        
    # Equity Curve Construction
    # We use ₹10,000 per trade. 
    # To start at the same base, we use total_trades * 10,000 as initial capital.
    base_capital = total_trades * 10000
    
    # Strategy returns by exit date
    strat_returns_by_date = {}
    for t in trades:
        d = t.exit_date
        # Profit/Loss in absolute rupees
        pl = (t.return_pct / 100) * 10000
        strat_returns_by_date[d] = strat_returns_by_date.get(d, 0) + pl
        
    equity_curve = []
    cumulative_pl = 0.0
    
    if benchmark_data is not None:
        first_bench_price = benchmark_data.iloc[0]['Close']
        
        for date, row in benchmark_data.iterrows():
            d = date.date()
            cumulative_pl += strat_returns_by_date.get(d, 0.0)
            
            # Scaled benchmark: (Price / StartPrice) * BaseCapital
            bench_equity = (row['Close'] / first_bench_price) * base_capital
            
            equity_curve.append({
                "date": d.isoformat(),
                "equity": float(base_capital + cumulative_pl),
                "benchmark_equity": float(bench_equity)
            })
    
    # Max Drawdown from equity curve
    max_drawdown_pct = 0.0
    if equity_curve:
        equities = [pt['equity'] for pt in equity_curve]
        peak = equities[0]
        for e in equities:
            if e > peak:
                peak = e
            dd = (peak - e) / peak * 100 if peak > 0 else 0
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd
                
    return {
        "total_trades": total_trades,
        "win_rate": float(win_rate),
        "avg_return_pct": float(avg_return_pct),
        "median_return_pct": float(median_return_pct),
        "best_trade_pct": float(best_trade_pct),
        "worst_trade_pct": float(worst_trade_pct),
        "max_drawdown_pct": float(max_drawdown_pct),
        "sharpe_ratio": float(sharpe_ratio),
        "total_return_pct": float(total_return_pct),
        "benchmark_return_pct": float(benchmark_return_pct),
        "equity_curve": equity_curve
    }
