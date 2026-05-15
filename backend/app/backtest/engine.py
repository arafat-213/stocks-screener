import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional
import datetime
import json
import logging
import traceback
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.pipeline.scorer import calculate_fundamental_score, calculate_technical_score
from app.db.models import BacktestRun, BacktestTrade, TechnicalSignal, Stock, FundamentalCache
from app.pipeline.fetcher import fetch_stock_data

logger = logging.getLogger(__name__)

@dataclass
class BacktestConfig:
    score_threshold: float = 45.0      # minimum score to trigger a trade
    holding_days: int = 20             # trading days to hold
    stop_loss_pct: float = 7.0         # exit if price drops this % (0 = disabled)
    target_pct: float = 0.0            # exit if price rises this % (0 = disabled)
    trailing_stop_pct: float = 0.0     # NEW: percentage drop from highest price
    require_volume_breakout: bool = False # NEW: require volume > 2x SMA20
    use_regime_filter: bool = True     # NEW: Nifty > 50 EMA filter
    atr_multiplier: float = 2.0        # Multiplier for ATR-based stop loss
    risk_reward_ratio: float = 2.0     # Target profit as multiple of risk
    use_atr_stops: bool = False        # Whether to use ATR for stops/targets
    include_fundamentals: bool = False  # use current fundamental data
    timeframe: str = 'D'               # 'D' only for now
    date_from: datetime.date = None    # filter signals after this date
    date_to: datetime.date = None      # filter signals before this date
    symbol_limit: int = None           # limit number of symbols to process
    screen_slug: Optional[str] = None  # New field
    starting_capital: float = 1000000.0
    position_size: float = 10000.0

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
    Uses calculate_technical_score as the single source of truth.
    O(n^2) implementation: for each bar, compute technical score on slice.
    """
    if df is None or len(df) < 60:
        return []

    # Fundamental Score (computed once since we only have current data)
    fund_score = 0.0
    if config and config.include_fundamentals and fund_cache:
        fund_score = calculate_fundamental_score(None, fund_cache=fund_cache)

    results = []
    MIN_BARS = 60
    
    # Iterate from MIN_BARS to end
    for i in range(MIN_BARS, len(df)):
        bar_df = df.iloc[:i+1]
        ta_data = calculate_technical_score(bar_df, timeframe='D')
        
        price = float(bar_df['Close'].iloc[-1])
        open_price = float(bar_df['Open'].iloc[-1])
        total_score = ta_data['score'] + fund_score

        # Hard Filter: Price must be above 200 EMA
        if ta_data.get('above_200ema') == False:  # explicitly False, not None
            total_score = 0.0
        
        results.append({
            "date": df.index[i],
            "score": float(total_score),
            "is_bullish": bool(ta_data['is_bullish']),
            "rsi": float(ta_data['rsi']) if ta_data['rsi'] else 0.0,
            "adx": float(ta_data['adx']) if ta_data.get('adx') is not None else 0.0,
            "ema_signal": ta_data['ema_signal'],
            "volume_signal": ta_data['volume_signal'],
            "rsi_signal": ta_data['rsi_signal'],
            "close": price,
            "open": open_price,
            "volume_breakout": bool(ta_data.get('volume_breakout', False)),
            "atr": ta_data.get('atr')
        })
        
    return results

def simulate_trades(symbol: str, sector: str, df: pd.DataFrame, scored_dates: list[dict], config: BacktestConfig, regime_dict: dict = None):
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
        # Convert signal_date to datetime.date if it's a Timestamp or string
        compare_date = signal_date.date() if hasattr(signal_date, 'date') else signal_date
        if isinstance(compare_date, str):
             compare_date = datetime.datetime.strptime(compare_date, "%Y-%m-%d").date()

        # Date Filtering
        if config.date_from and compare_date < config.date_from:
            continue
        if config.date_to and compare_date > config.date_to:
            continue

        # Volume Breakout Filter
        if config.require_volume_breakout:
            if not signal.get('volume_breakout', False):
                continue

        signal_idx = date_to_idx.get(signal_date)
        
        if signal_idx is None or signal_idx <= last_exit_idx:
            continue
            
        if signal['score'] >= config.score_threshold:
            # Entry: Next trading day's Open price
            entry_idx = signal_idx + 1
            if entry_idx >= len(df):
                break
                
            entry_date = df.index[entry_idx]
            # Convert to date for regime check
            entry_compare_date = entry_date.date() if hasattr(entry_date, 'date') else entry_date
            
            # Regime Filter (on ENTRY date)
            if config.use_regime_filter and regime_dict is not None:
                if not regime_dict.get(entry_compare_date, False):
                    continue

            entry_price = df.iloc[entry_idx]['Open']
            
            # Exit conditions
            exit_price = None
            exit_date = None
            exit_reason = 'holding_period'
            
            if config.use_atr_stops and signal.get('atr'):
                atr = signal['atr']
                stop_loss_price = entry_price - (config.atr_multiplier * atr)
                target_price = entry_price + (config.atr_multiplier * config.risk_reward_ratio * atr)
            else:
                stop_loss_pct = config.stop_loss_pct
                target_pct = config.target_pct
                stop_loss_price = entry_price * (1 - stop_loss_pct / 100) if stop_loss_pct > 0 else 0
                target_price = entry_price * (1 + target_pct / 100) if target_pct > 0 else float('inf')
            
            # Walk forward up to config.holding_days
            final_idx = min(entry_idx + config.holding_days - 1, len(df) - 1)
            
            highest_price_since_entry = entry_price
            
            for k in range(entry_idx, final_idx + 1):
                day_low = df.iloc[k]['Low']
                day_high = df.iloc[k]['High']
                day_open = df.iloc[k]['Open']
                
                highest_price_since_entry = max(highest_price_since_entry, day_high)
                
                # Check Stop Loss first (conservative)
                if day_low <= stop_loss_price:
                    exit_price = stop_loss_price
                    exit_date = df.index[k]
                    exit_reason = 'stop_loss'
                    last_exit_idx = k
                    break
                    
                # Check Trailing Stop
                if config.trailing_stop_pct > 0:
                    trailing_stop_price = highest_price_since_entry * (1 - config.trailing_stop_pct / 100)
                    if day_low <= trailing_stop_price:
                        # If it gapped down below stop, exit at open
                        exit_price = min(trailing_stop_price, day_open)
                        exit_date = df.index[k]
                        exit_reason = 'trailing_stop'
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
    Uses starting_capital and position_size from config.
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
    winning_trades = [r for r in returns if r > 0]
    win_rate = len(winning_trades) / total_trades
    
    avg_return_pct = sum(returns) / total_trades
    median_return_pct = float(pd.Series(returns).median())
    best_trade_pct = max(returns)
    worst_trade_pct = min(returns)
    
    # Updated PnL and Total Return logic
    total_pnl = sum((r / 100) * config.position_size for r in returns)
    total_return_pct = (total_pnl / config.starting_capital) * 100 if config.starting_capital > 0 else 0.0
    
    # Benchmark return
    benchmark_return_pct = 0.0
    if benchmark_data is not None and len(benchmark_data) > 1:
        start_price = benchmark_data.iloc[0]['Close']
        end_price = benchmark_data.iloc[-1]['Close']
        benchmark_return_pct = ((end_price - start_price) / start_price) * 100
        
    # Equity Curve Construction
    strat_returns_by_date = {}
    for t in trades:
        d = t.exit_date
        # Profit/Loss in absolute rupees
        pl = (t.return_pct / 100) * config.position_size
        strat_returns_by_date[d] = strat_returns_by_date.get(d, 0) + pl
        
    equity_curve = []
    cumulative_pl = 0.0
    
    if benchmark_data is not None:
        first_bench_price = benchmark_data.iloc[0]['Close']
        
        for date, row in benchmark_data.iterrows():
            d = date.date()
            cumulative_pl += strat_returns_by_date.get(d, 0.0)
            
            # Scaled benchmark: (Price / StartPrice) * config.starting_capital
            bench_equity = (row['Close'] / first_bench_price) * config.starting_capital
            
            equity_curve.append({
                "date": d.isoformat(),
                "equity": float(config.starting_capital + cumulative_pl),
                "benchmark_equity": float(bench_equity)
            })
    
    # Updated Sharpe Ratio using daily returns from equity curve
    sharpe_ratio = 0.0
    if len(equity_curve) > 1:
        equity_series = pd.Series([pt['equity'] for pt in equity_curve])
        daily_returns = equity_series.pct_change().dropna()
        if not daily_returns.empty and daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)

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
        "winning_trades": len(winning_trades),
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

def run_backtest(db: Session, run_id: str, config: BacktestConfig):
    """
    Main orchestrator for the backtest.
    """
    logger.info(f"Starting backtest {run_id}")
    run = db.query(BacktestRun).filter(BacktestRun.run_id == run_id).first()
    if not run:
        logger.error(f"BacktestRun {run_id} not found")
        return

    try:
        # Update status to running
        run.status = 'running'
        db.commit()

        # 1. Fetch benchmark data (^NSEI)
        logger.info("Fetching benchmark data (^NSEI)")
        benchmark_df, _ = fetch_stock_data("^NSEI", append_ns=False, period='3y', fetch_info=False)
        if benchmark_df is not None and benchmark_df.index.tz is not None:
            benchmark_df.index = benchmark_df.index.tz_localize(None)

        regime_dict = {}
        if benchmark_df is not None and not benchmark_df.empty:
            benchmark_df.ta.ema(length=50, append=True)
            # Map index date to boolean
            valid = benchmark_df[benchmark_df['EMA_50'].notna()]
            regime_dict = dict(zip(
                valid.index.date,
                valid['Close'] > valid['EMA_50']
            ))

        # 2. Select symbols
        symbol_query = (
            db.query(TechnicalSignal.symbol)
            .group_by(TechnicalSignal.symbol)
            .order_by(func.max(TechnicalSignal.date).desc())
            .all()
        )
        symbols = [row[0] for row in symbol_query]
        if config.symbol_limit:
            symbols = symbols[:config.symbol_limit]
        
        run.symbols_total = len(symbols)
        db.commit()

        all_trades = []
        symbols_processed = 0

        # Pre-fetch sector info if needed
        stocks_info = {s.symbol: s.sector for s in db.query(Stock).all()}
        # Pre-fetch fundamental cache if needed
        fund_caches = {}
        if config.include_fundamentals:
            fund_caches = {c.symbol: c for c in db.query(FundamentalCache).all()}

        for symbol in symbols:
            try:
                # Fetch historical OHLCV
                df, _ = fetch_stock_data(symbol, period='3y', fetch_info=False)
                if df is None or df.empty:
                    continue
                
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)

                fund_cache = fund_caches.get(symbol)
                
                # Run scoring
                scored_dates = score_series(df, fund_cache=fund_cache, config=config)
                
                # Run simulation
                sector = stocks_info.get(symbol, "Unknown")
                trades = simulate_trades(symbol, sector, df, scored_dates, config, regime_dict=regime_dict)
                
                # Save trades to DB
                db_trades = []
                for t in trades:
                    db_trade = BacktestTrade(
                        run_id=run_id,
                        symbol=t.symbol,
                        sector=t.sector,
                        signal_date=t.signal_date,
                        entry_date=t.entry_date,
                        exit_date=t.exit_date,
                        exit_reason=t.exit_reason,
                        signal_score=t.signal_score,
                        entry_price=t.entry_price,
                        exit_price=t.exit_price,
                        return_pct=t.return_pct,
                        rsi_at_signal=t.rsi_at_signal,
                        adx_at_signal=t.adx_at_signal,
                        ema_signal=t.ema_signal
                    )
                    db_trades.append(db_trade)
                    all_trades.append(t)

                if db_trades:
                    db.bulk_save_objects(db_trades)

                symbols_processed += 1
                
                # Periodic commits
                if symbols_processed % 10 == 0:
                    db.commit()
                
                if symbols_processed % 5 == 0:
                    run.symbols_done = symbols_processed
                    db.commit()

            except Exception as e:
                logger.error(f"Error processing symbol {symbol}: {e}")
                logger.error(traceback.format_exc())
                continue

        # 3. Finalize
        logger.info(f"Computing final metrics for {len(all_trades)} trades")

        # Slice benchmark data to match backtest range
        if all_trades and benchmark_df is not None:
            first_entry = min(t.entry_date for t in all_trades)
            effective_from = config.date_from or first_entry
            effective_to = config.date_to or datetime.date.today()

            benchmark_df = benchmark_df[
              (benchmark_df.index.normalize() >= pd.Timestamp(effective_from)) &
              (benchmark_df.index.normalize() <= pd.Timestamp(effective_to))
            ]

        metrics = compute_metrics(all_trades, benchmark_df, config)
        
        # Update run with results
        run.total_trades = metrics['total_trades']
        run.winning_trades = metrics['winning_trades']
        run.win_rate = metrics['win_rate']
        run.avg_return_pct = metrics['avg_return_pct']
        run.median_return_pct = metrics['median_return_pct']
        run.best_trade_pct = metrics['best_trade_pct']
        run.worst_trade_pct = metrics['worst_trade_pct']
        run.max_drawdown_pct = metrics['max_drawdown_pct']
        run.sharpe_ratio = metrics['sharpe_ratio']
        run.total_return_pct = metrics['total_return_pct']
        run.benchmark_return_pct = metrics['benchmark_return_pct']
        run.equity_curve_json = json.dumps(metrics['equity_curve'])
        
        run.symbols_done = len(symbols)
        run.status = 'complete'
        db.commit()
        logger.info(f"Backtest {run_id} completed successfully")

    except Exception as e:
        db.rollback()
        logger.error(f"Backtest {run_id} failed: {e}")
        logger.error(traceback.format_exc())
        run.status = 'failed'
        run.error_message = str(e)
        db.commit()
