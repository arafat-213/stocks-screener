from sqlalchemy import Column, String, Float, DateTime, PrimaryKeyConstraint, Text, Integer, Boolean, UniqueConstraint, Date, ForeignKey, func
from sqlalchemy.orm import declarative_base
import datetime
import uuid

Base = declarative_base()

class Stock(Base):
    __tablename__ = "stocks"
    symbol = Column(String, primary_key=True)
    name = Column(String)
    sector = Column(String)
    industry = Column(String)
    market_cap = Column(Float)

class TechnicalSignal(Base):
    __tablename__ = "technical_signals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False)
    symbol = Column(String, nullable=False)
    timeframe = Column(String(1), nullable=False) # 'D', 'W', 'M'
    is_bullish = Column(Boolean, nullable=False, default=False)
    entry_score = Column(Float)
    rsi = Column(Float)
    macd = Column(Float)
    ema_signal = Column(String)
    volume_signal = Column(String)
    rsi_signal = Column(String)
    atr = Column(Float, nullable=True)
    close_price = Column(Float, nullable=True)
    price_change_pct = Column(Float, nullable=True)
    
    # Momentum and Relative Strength
    momentum_1m = Column(Float, nullable=True)
    momentum_3m = Column(Float, nullable=True)
    momentum_6m = Column(Float, nullable=True)
    momentum_12m = Column(Float, nullable=True)
    rs_score = Column(Float, nullable=True)
    
    # Technical Indicators
    adx = Column(Float, nullable=True)
    above_200ema = Column(Boolean, nullable=True)
    ema_slope_20 = Column(Float, nullable=True)

    # EMA Levels
    ema5_level = Column(Float, nullable=True)
    ema13_level = Column(Float, nullable=True)
    ema20_level = Column(Float, nullable=True)
    ema26_level = Column(Float, nullable=True)
    
    # 52-Week Range and Resistance
    pct_from_52w_high = Column(Float, nullable=True)
    pct_from_52w_low = Column(Float, nullable=True)
    week52_high = Column(Float, nullable=True)
    week52_low = Column(Float, nullable=True)
    resistance_level = Column(Float, nullable=True)
    pct_from_resistance = Column(Float, nullable=True)
    
    # Volume Breakout
    volume_breakout = Column(Boolean, nullable=True, default=False)
    
    scored_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    __table_args__ = (UniqueConstraint('symbol', 'date', 'timeframe'),)

class FundamentalData(Base):
    __tablename__ = "fundamental_data"
    date = Column(DateTime, default=datetime.datetime.utcnow)
    symbol = Column(String)
    pe = Column(Float, nullable=True)
    pb = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    debt_equity = Column(Float, nullable=True)
    eps_growth = Column(Float, nullable=True)
    promoter_holding = Column(Float, nullable=True)
    pledged_percent = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    __table_args__ = (PrimaryKeyConstraint('date', 'symbol'),)

class FundamentalCache(Base):
    __tablename__ = "fundamental_cache"
    symbol = Column(String, primary_key=True)
    profitability_streak_passed = Column(Boolean)
    de_ratio = Column(Float)
    de_check_passed = Column(Boolean)
    pledged_data_missing = Column(Boolean, default=False)
    sector = Column(String)
    
    # Advanced Fundamental Metrics
    roce = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    peg_ratio = Column(Float, nullable=True)
    ev_to_ebitda = Column(Float, nullable=True)
    dividend_yield = Column(Float, nullable=True)
    price_to_fcf = Column(Float, nullable=True)
    earnings_growth_3y = Column(Float, nullable=True)
    fcf_positive = Column(Boolean, nullable=True)
    dividend_consistency = Column(Boolean, nullable=True)
    market_cap_category = Column(String(20), nullable=True)
    
    retry_after = Column(DateTime, nullable=True)
    fetch_attempts = Column(Integer, default=0)
    last_error = Column(String, nullable=True)
    force_refresh = Column(Boolean, default=False)
    
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)
    cache_version = Column(Integer, default=1)

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    run_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String)
    stocks_fetched = Column(Integer)
    stocks_scored = Column(Integer)
    total_symbols = Column(Integer, default=0)
    tier1_count = Column(Integer, default=0)
    tier2_count = Column(Integer, default=0)
    errors = Column(Text)
    stop_requested = Column(Boolean, default=False)

class PipelineCheckpoint(Base):
    __tablename__ = "pipeline_checkpoints"
    run_id = Column(String, ForeignKey('pipeline_runs.run_id'), primary_key=True)
    phase = Column(String, primary_key=True)  
    completed_symbols = Column(Text)  # JSON array of symbols
    started_at = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)

class PipelineError(Base):
    __tablename__ = "pipeline_errors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey('pipeline_runs.run_id'), nullable=False)
    symbol = Column(String, nullable=True)
    phase = Column(String, nullable=False)  
    error_type = Column(String, nullable=False)  
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    occurred_at = Column(DateTime, default=datetime.datetime.utcnow)

class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    date = Column(Date, primary_key=True)
    symbol = Column(String, primary_key=True)
    close = Column(Float)
    change_pct = Column(Float)

class ScreenResult(Base):
    __tablename__ = "screen_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    screen_slug = Column(String, nullable=False)
    symbol = Column(String, ForeignKey('stocks.symbol'), nullable=False)
    timeframe = Column(String(1), nullable=False) # 'D', 'W', 'M'
    rank = Column(Integer)
    score_used = Column(Float)
    computed_at = Column(Date, default=datetime.date.today)

class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    run_id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)
    status          = Column(String, nullable=False) # 'pending', 'running', 'complete', 'failed'
    config          = Column(Text, nullable=False)   # JSON string
    symbols_total   = Column(Integer, default=0)
    symbols_done    = Column(Integer, default=0)
    error_message   = Column(Text, nullable=True)
    total_trades     = Column(Integer, nullable=True)
    winning_trades   = Column(Integer, nullable=True)
    win_rate         = Column(Float, nullable=True)
    avg_return_pct   = Column(Float, nullable=True)
    median_return_pct = Column(Float, nullable=True)
    best_trade_pct   = Column(Float, nullable=True)
    worst_trade_pct  = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    sharpe_ratio     = Column(Float, nullable=True)
    total_return_pct = Column(Float, nullable=True)
    benchmark_return_pct = Column(Float, nullable=True)
    equity_curve_json = Column(Text, nullable=True)
    starting_capital = Column(Float, nullable=True)
    position_size    = Column(Float, nullable=True)
    expectancy = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    avg_win_pct = Column(Float, nullable=True)
    avg_loss_pct = Column(Float, nullable=True)
    exit_breakdown_json = Column(Text, nullable=True)

class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    run_id          = Column(String, ForeignKey('backtest_runs.run_id'), nullable=False)
    symbol          = Column(String, nullable=False)
    sector          = Column(String, nullable=True)
    signal_date     = Column(Date, nullable=False)
    entry_date      = Column(Date, nullable=False)
    exit_date       = Column(Date, nullable=False)
    exit_reason     = Column(String, nullable=False) # 'holding_period', 'stop_loss', 'target'
    signal_score    = Column(Float, nullable=False)
    entry_price     = Column(Float, nullable=False)
    exit_price      = Column(Float, nullable=False)
    return_pct      = Column(Float, nullable=False)
    rsi_at_signal   = Column(Float, nullable=True)
    adx_at_signal   = Column(Float, nullable=True)
    ema_signal      = Column(String, nullable=True)
