import datetime
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

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
    timeframe = Column(String(1), nullable=False)  # 'D', 'W', 'M'
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

    # Consolidation
    is_consolidating = Column(Boolean, nullable=True, default=None)

    scored_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "date", "timeframe"),
        # Covers every screen query: WHERE timeframe='D' AND date(date)=X
        Index("ix_ts_timeframe_date", "timeframe", "date"),
        # Covers per-symbol history queries and stock detail page
        Index("ix_ts_symbol_timeframe_date", "symbol", "timeframe", "date"),
        # Covers above_200ema + is_bullish filter combos used in most screens
        Index(
            "ix_ts_screener_core",
            "timeframe",
            "date",
            "above_200ema",
            "is_bullish",
            "is_consolidating",
        ),
    )


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
    __table_args__ = (PrimaryKeyConstraint("date", "symbol"),)


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
    run_id = Column(String, ForeignKey("pipeline_runs.run_id"), primary_key=True)
    phase = Column(String, primary_key=True)
    completed_symbols = Column(Text)  # JSON array of symbols
    started_at = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)


class PipelineError(Base):
    __tablename__ = "pipeline_errors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("pipeline_runs.run_id"), nullable=False)
    symbol = Column(String, nullable=True)
    phase = Column(String, nullable=False)
    error_type = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    occurred_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (Index("ix_pe_run_id", "run_id"),)


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
    symbol = Column(String, ForeignKey("stocks.symbol"), nullable=False)
    timeframe = Column(String(1), nullable=False)  # 'D', 'W', 'M'
    rank = Column(Integer)
    score_used = Column(Float)
    quality_tier = Column(String(1), nullable=True)
    computed_at = Column(Date, default=datetime.date.today)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    run_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(
        String, nullable=False
    )  # 'pending', 'running', 'complete', 'failed'
    config = Column(Text, nullable=False)  # JSON string
    symbols_total = Column(Integer, default=0)
    symbols_done = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    total_trades = Column(Integer, nullable=True)
    winning_trades = Column(Integer, nullable=True)
    win_rate = Column(Float, nullable=True)
    avg_return_pct = Column(Float, nullable=True)
    median_return_pct = Column(Float, nullable=True)
    best_trade_pct = Column(Float, nullable=True)
    worst_trade_pct = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    total_return_pct = Column(Float, nullable=True)
    gross_return_pct = Column(Float, nullable=True)
    total_cost_drag_pct = Column(Float, nullable=True)
    benchmark_return_pct = Column(Float, nullable=True)
    equity_curve_json = Column(Text, nullable=True)
    starting_capital = Column(Float, nullable=True)
    position_size = Column(Float, nullable=True)
    expectancy = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    avg_win_pct = Column(Float, nullable=True)
    avg_loss_pct = Column(Float, nullable=True)
    exit_breakdown_json = Column(Text, nullable=True)


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("backtest_runs.run_id"), nullable=False)
    symbol = Column(String, nullable=False)
    sector = Column(String, nullable=True)
    signal_date = Column(Date, nullable=False)
    entry_date = Column(Date, nullable=False)
    exit_date = Column(Date, nullable=False)
    exit_reason = Column(
        String, nullable=False
    )  # 'holding_period', 'stop_loss', 'target'
    signal_score = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    return_pct = Column(Float, nullable=False)
    rsi_at_signal = Column(Float, nullable=True)
    adx_at_signal = Column(Float, nullable=True)
    ema_signal = Column(String, nullable=True)

    __table_args__ = (
        # Every trade fetch is filtered by run_id — this index is critical
        Index("ix_bt_run_id", "run_id"),
        Index("ix_bt_run_id_exit_reason", "run_id", "exit_reason"),
    )


class SectorSnapshot(Base):
    __tablename__ = "sector_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    sector = Column(String, nullable=False)
    avg_rs = Column(Float, nullable=True)  # average RS percentile in sector
    avg_momentum_3m = Column(Float, nullable=True)
    bullish_pct = Column(Float, nullable=True)  # % of stocks in sector that are bullish
    stock_count = Column(Integer, nullable=True)
    __table_args__ = (UniqueConstraint("date", "sector"),)


class PaperPortfolio(Base):
    __tablename__ = "paper_portfolio"
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    name = Column(String, nullable=False, default="default")
    starting_capital = Column(Float, nullable=False, default=1000000.0)
    is_active = Column(Boolean, default=True)


class PaperPosition(Base):
    """
    A virtual position tracking state from signal (pending) to entry (open) to exit (closed).
    States: 'pending' | 'open' | 'closed' | 'expired'
    """

    __tablename__ = "paper_positions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_portfolio.id"), nullable=False)
    symbol = Column(String, nullable=False)
    sector = Column(String, nullable=True)

    # Discovery state
    signal_date = Column(Date, nullable=False)
    signal_score = Column(Float, nullable=True)
    ema_signal = Column(String, nullable=True)
    atr_at_signal = Column(Float, nullable=True)
    ema20_at_signal = Column(Float, nullable=True)

    # Pullback tracking (for 'pending' state)
    status = Column(String, nullable=False, default="pending")
    wait_days_elapsed = Column(Integer, default=0)
    pending_highest_closeness_pct = Column(
        Float, default=999.0
    )  # How close we got to EMA20
    is_invalidated = Column(Boolean, default=False)

    # Active state (for 'open' state)
    entry_date = Column(Date, nullable=True)
    entry_price = Column(Float, nullable=True)
    entry_type = Column(
        String, nullable=True
    )  # 'pullback_a' | 'momentum_b' | 'immediate'
    position_size = Column(Float, nullable=True)  # rupee value
    shares = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    highest_price = Column(Float, nullable=True)  # updated daily for trailing stop
    atr_trail_active = Column(Boolean, default=False)

    opened_at = Column(DateTime, default=datetime.datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    exit_reason = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_pp_portfolio_status", "portfolio_id", "status"),
        Index("ix_pp_symbol", "symbol"),
    )


class PaperTrade(Base):
    """A completed paper trade record."""

    __tablename__ = "paper_trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_portfolio.id"), nullable=False)
    symbol = Column(String, nullable=False)
    sector = Column(String, nullable=True)
    signal_date = Column(Date, nullable=False)
    entry_date = Column(Date, nullable=False)
    exit_date = Column(Date, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    shares = Column(Float, nullable=False)
    position_size = Column(Float, nullable=False)
    return_pct = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False)  # rupees
    exit_reason = Column(String, nullable=False)
    signal_score = Column(Float, nullable=True)
    ema_signal = Column(String, nullable=True)
    holding_days = Column(Integer, nullable=False)
    closed_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (Index("ix_pt_portfolio_id", "portfolio_id"),)


class AlertLog(Base):
    __tablename__ = "alert_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    signal_date = Column(Date, nullable=False)
    alert_type = Column(
        String, nullable=False
    )  # 'tier1_entry', 'tier2_entry', 'regime_change'
    quality_tier = Column(String(1), nullable=True)  # 'A', 'B', 'C'
    entry_score = Column(Float, nullable=True)
    sent_at = Column(DateTime, default=datetime.datetime.utcnow)
    email_id = Column(String, nullable=True)  # Resend message ID for debugging

    __table_args__ = (
        # Prevent duplicate alerts for same symbol+date+type
        UniqueConstraint("symbol", "signal_date", "alert_type"),
        Index("ix_alert_logs_sent_at", "sent_at"),
    )


class Watchlist(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, ForeignKey("stocks.symbol"), nullable=False)
    added_date = Column(Date, nullable=False, default=datetime.date.today)
    signal_date = Column(Date, nullable=False)

    alert_type = Column(String, nullable=True)
    quality_tier = Column(String(1), nullable=True)
    signal_score = Column(Float, nullable=True)
    planned_entry_low = Column(Float, nullable=True)
    planned_entry_high = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    status = Column(
        String, nullable=False, default="watching"
    )  # 'watching', 'entered', 'skipped', 'expired'

    __table_args__ = (
        UniqueConstraint("symbol", "signal_date"),
        Index("ix_watchlist_status", "status"),
    )


class TradeJournal(Base):
    __tablename__ = "trade_journal"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    watchlist_id = Column(Integer, ForeignKey("watchlist.id"), nullable=True)

    # Entry
    signal_date = Column(Date, nullable=True)
    entry_date = Column(Date, nullable=False, default=datetime.date.today)
    entry_price = Column(Float, nullable=False)
    shares = Column(Integer, nullable=False)
    position_value = Column(Float, nullable=False)

    # Risk Management
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    quality_tier = Column(String(1), nullable=True)
    signal_score = Column(Float, nullable=True)

    # Exit
    exit_date = Column(Date, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)  # 'stop', 'target', 'manual', 'trail'
    pnl = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)

    status = Column(String, nullable=False, default="open")  # 'open' | 'closed'
    notes = Column(Text, nullable=True)
    source = Column(String, nullable=False, default="manual")  # 'manual' | 'paper'
    external_id = Column(Integer, nullable=True)  # Links to PaperPosition.id
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        Index("ix_tj_status", "status"),
        Index("ix_tj_symbol", "symbol"),
    )
