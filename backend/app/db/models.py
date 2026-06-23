import datetime
import uuid

from sqlalchemy import (
    JSON,
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
from sqlalchemy.ext.mutable import MutableList
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
    date = Column(DateTime(timezone=True), nullable=False)
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
    ema_slope_21 = Column(Float, nullable=True)

    # EMA Levels
    ema5_level = Column(Float, nullable=True)
    ema13_level = Column(Float, nullable=True)
    ema21_level = Column(Float, nullable=True)

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

    scored_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    __table_args__ = (
        UniqueConstraint("symbol", "date", "timeframe"),
        Index("ix_ts_timeframe_date", "timeframe", "date"),
        Index("ix_ts_symbol_timeframe_date", "symbol", "timeframe", "date"),
        Index(
            "ix_ts_screener_core",
            "timeframe",
            "date",
            "above_200ema",
            "is_bullish",
            "is_consolidating",
        ),
        Index("ix_ts_rs_score", "rs_score"),
        Index("ix_ts_above_200ema", "above_200ema"),
    )


class FundamentalData(Base):
    __tablename__ = "fundamental_data"
    date = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
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

    retry_after = Column(DateTime(timezone=True), nullable=True)
    fetch_attempts = Column(Integer, default=0)
    last_error = Column(String, nullable=True)
    force_refresh = Column(Boolean, default=False)

    last_updated = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    cache_version = Column(Integer, default=1)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    run_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
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
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True), nullable=True)


class PipelineError(Base):
    __tablename__ = "pipeline_errors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("pipeline_runs.run_id"), nullable=False)
    symbol = Column(String, nullable=True)
    phase = Column(String, nullable=False)
    error_type = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    occurred_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

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
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    status = Column(String, nullable=False)
    config = Column(Text, nullable=False)
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
    max_drawdown_duration = Column(Integer, nullable=True)
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
    regime_map_json = Column(Text, nullable=True)


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("backtest_runs.run_id"), nullable=False)
    symbol = Column(String, nullable=False)
    sector = Column(String, nullable=True)
    signal_date = Column(Date, nullable=False)
    entry_date = Column(Date, nullable=False)
    exit_date = Column(Date, nullable=False)
    exit_reason = Column(String, nullable=False)
    signal_score = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    return_pct = Column(Float, nullable=False)
    rsi_at_signal = Column(Float, nullable=True)
    adx_at_signal = Column(Float, nullable=True)
    ema_signal = Column(String, nullable=True)
    position_size = Column(Float, nullable=True)

    regime_at_signal = Column(Integer, nullable=True)
    regime_at_entry = Column(Integer, nullable=True)
    regime_at_exit = Column(Integer, nullable=True)
    market_breadth_at_entry = Column(Float, nullable=True)
    consolidation_bars_at_signal = Column(Integer, nullable=True)
    pullback_depth_pct = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_bt_run_id", "run_id"),
        Index("ix_bt_run_id_exit_reason", "run_id", "exit_reason"),
    )


class SectorSnapshot(Base):
    __tablename__ = "sector_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    sector = Column(String, nullable=False)
    avg_rs = Column(Float, nullable=True)
    avg_momentum_3m = Column(Float, nullable=True)
    bullish_pct = Column(Float, nullable=True)
    stock_count = Column(Integer, nullable=True)
    __table_args__ = (UniqueConstraint("date", "sector"),)


class PaperPortfolio(Base):
    __tablename__ = "paper_portfolio"
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    name = Column(String, nullable=False, default="default")
    starting_capital = Column(Float, nullable=False, default=1000000.0)
    is_active = Column(Boolean, default=True)


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_portfolio.id"), nullable=False)
    symbol = Column(String, nullable=False)
    sector = Column(String, nullable=True)
    strategy_tags = Column(MutableList.as_mutable(JSON), default=[])

    signal_date = Column(Date, nullable=False)
    signal_score = Column(Float, nullable=True)
    ema_signal = Column(String, nullable=True)
    atr_at_signal = Column(Float, nullable=True)
    ema21_at_signal = Column(Float, nullable=True)

    status = Column(String, nullable=False, default="pending")
    wait_days_elapsed = Column(Integer, default=0)
    pending_highest_closeness_pct = Column(Float, default=999.0)
    is_invalidated = Column(Boolean, default=False)

    entry_date = Column(Date, nullable=True)
    entry_price = Column(Float, nullable=True)
    entry_type = Column(String, nullable=True)
    position_size = Column(Float, nullable=True)
    shares = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    highest_price = Column(Float, nullable=True)
    atr_trail_active = Column(Boolean, default=False)

    opened_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_pp_portfolio_status", "portfolio_id", "status"),
        Index("ix_pp_symbol", "symbol"),
    )


class PaperTrade(Base):
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
    pnl = Column(Float, nullable=False)
    exit_reason = Column(String, nullable=False)
    signal_score = Column(Float, nullable=True)
    ema_signal = Column(String, nullable=True)
    holding_days = Column(Integer, nullable=False)
    strategy_tags = Column(MutableList.as_mutable(JSON), default=[])
    closed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    __table_args__ = (Index("ix_pt_portfolio_id", "portfolio_id"),)


class AlertLog(Base):
    __tablename__ = "alert_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    signal_date = Column(Date, nullable=False)
    alert_type = Column(String, nullable=False)
    quality_tier = Column(String(1), nullable=True)
    entry_score = Column(Float, nullable=True)
    sent_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    email_id = Column(String, nullable=True)

    __table_args__ = (
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
    status = Column(String, nullable=False, default="watching")

    __table_args__ = (
        UniqueConstraint("symbol", "signal_date"),
        Index("ix_watchlist_status", "status"),
    )


class TradeJournal(Base):
    __tablename__ = "trade_journal"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    watchlist_id = Column(Integer, ForeignKey("watchlist.id"), nullable=True)

    signal_date = Column(Date, nullable=True)
    entry_date = Column(Date, nullable=False, default=datetime.date.today)
    entry_price = Column(Float, nullable=False)
    shares = Column(Integer, nullable=False)
    position_value = Column(Float, nullable=False)

    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    quality_tier = Column(String(1), nullable=True)
    signal_score = Column(Float, nullable=True)

    exit_date = Column(Date, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)
    pnl = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)

    status = Column(String, nullable=False, default="open")
    notes = Column(Text, nullable=True)
    source = Column(String, nullable=False, default="manual")
    external_id = Column(Integer, nullable=True)
    strategy_tags = Column(MutableList.as_mutable(JSON), default=[])

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    __table_args__ = (
        Index("ix_tj_status", "status"),
        Index("ix_tj_symbol", "symbol"),
    )


class DailyDigestLog(Base):
    __tablename__ = "daily_digest_logs"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    regime_bullish = Column(Boolean, nullable=False, default=True)
    new_signals = Column(JSON, default=list)
    opened_positions = Column(JSON, default=list)
    closed_positions = Column(JSON, default=list)
    trail_moved = Column(JSON, default=list)
    warnings = Column(JSON, default=list)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class PaperV2Portfolio(Base):
    """v2-native paper book for the S3 forward probation (specs/v3/11 §6).

    Distinct from the v1 ``paper_portfolio`` (swing-trade, symbol/ATR/EMA) which
    is left untouched — v1 removal is a separate later sprint (11 §2/§9). This
    book is ISIN-keyed and mirrors ``backtest_v2`` portfolio state.
    """

    __tablename__ = "paper_v2_portfolio"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, default="s3_probation")
    starting_capital = Column(Float, nullable=False, default=1000000.0)
    cash = Column(Float, nullable=False, default=1000000.0)
    is_active = Column(Boolean, nullable=False, default=True)
    # Last trading date whose daily post-close job was applied (the replay clock, 11 §4c).
    last_processed_date = Column(Date, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


class PaperV2Position(Base):
    """An open S3 paper holding — mirrors ``backtest_v2.schemas.Position`` plus the
    selection metadata and the last-seen ``adj_factor`` the 11 §5e CA-reconciliation
    needs to detect a moving back-adjustment anchor on a held name.
    """

    __tablename__ = "paper_v2_positions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_v2_portfolio.id"), nullable=False)
    isin = Column(String, nullable=False)
    symbol = Column(String, nullable=False)

    # Portfolio state (backtest_v2 Position).
    shares = Column(Float, nullable=False)
    cost_basis = Column(Float, nullable=False)  # adjusted-space avg cost incl. fees
    last_price = Column(Float, nullable=True)  # close_tr at last MTM
    entry_date = Column(Date, nullable=False)
    days_held = Column(Integer, nullable=False, default=0)

    # Selection metadata at entry (S3 ranking).
    rank = Column(Integer, nullable=True)
    composite_score = Column(Float, nullable=True)
    target_weight = Column(Float, nullable=True)
    regime_state_at_entry = Column(String, nullable=True)

    # Last back-adjustment factor seen for this ISIN; a change vs. the freshly
    # appended series signals a CA hit that day → 11 §5e rescale before the stop check.
    last_adj_factor = Column(Float, nullable=False, default=1.0)

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("portfolio_id", "isin", name="uq_paper_v2_pos_portfolio_isin"),
        Index("ix_paper_v2_pos_portfolio", "portfolio_id"),
    )


class PaperV2PendingFill(Base):
    """The persisted pending-fills queue (11 §3e). A decision at day D's close
    queues a row here; the next session's post-close job executes it at D+1's open
    and marks it ``filled`` — reproducing the engine's D→D+1 fill discipline across
    process restarts.
    """

    __tablename__ = "paper_v2_pending_fills"
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_v2_portfolio.id"), nullable=False)
    isin = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)  # buy | sell | trim
    qty = Column(Float, nullable=False)  # shares (positive)
    reason = Column(
        String, nullable=False
    )  # rebalance | catastrophic_stop | force_exit
    # Pre-trade holding of the position this fill acts on, captured at decision time
    # (shares held BEFORE the queued fill applies; 0 for a fresh entry). Lets the viz
    # render "holding (Δ)" — e.g. a trim shows "10 (-2)", a full exit "25 (-25)" — which
    # cannot be reconstructed historically from qty alone once the position has moved on.
    holding_before = Column(Float, nullable=True)
    # Regime overlay's deployable fraction on the decision day (1.0 = risk-on; the
    # configured risk_off_floor, default 0.0, = risk-off / full cash). Persisted so the
    # log can flag a regime-driven risk-off rebalance vs a routine one (the cause, not
    # the post-fill exposure effect). Same for every fill queued on that day.
    deployable_fraction = Column(Float, nullable=True)

    decision_date = Column(Date, nullable=False)  # day D close that queued it
    # Decision-close price the order was sized against (11 §3e). Buys need it to
    # rebuild target notional (qty × price) when the queue is rehydrated after a
    # restart; without it a rehydrated buy collapses to zero notional and is dropped.
    decision_price = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending | filled

    # Populated on execution (next session's open).
    fill_date = Column(Date, nullable=True)
    fill_price = Column(Float, nullable=True)
    cost_rupees = Column(Float, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    __table_args__ = (
        Index("ix_paper_v2_fill_portfolio_status", "portfolio_id", "status"),
    )


class PaperV2DailySnapshot(Base):
    """Per-day NAV snapshot for the S3 probation book (specs/v3/11 viz, V11.1).

    The engine produces a ``backtest_v2.schemas.DailySnapshot`` every processed day
    and discards it; this table persists it (plus the benchmark level) so the
    read-only ``/v2/paper/nav`` curve can render the full since-inception equity
    curve with a go-live divider — without any live price fetch. One row per
    processed trading day, idempotent on ``(portfolio_id, date)`` (Pipeline Law).
    """

    __tablename__ = "paper_v2_daily_snapshot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_v2_portfolio.id"), nullable=False)
    date = Column(Date, nullable=False)  # the processed trading day
    equity = Column(Float, nullable=False)  # cash + Σ shares·close_tr  (NAV)
    cash = Column(Float, nullable=False)
    invested_value = Column(Float, nullable=False)  # Σ shares·close_tr
    exposure = Column(Float, nullable=False)  # invested_value / equity  (0–1)
    n_positions = Column(Integer, nullable=False)
    # Nifty200 Mom30 TRI close on this date (deployment benchmark, 08 §10). Nullable:
    # a day with no index point (gap) stores NULL and the FE skips it in the overlay.
    index_level = Column(Float, nullable=True)
    is_forward = Column(Boolean, nullable=False, default=False)  # date >= go_live

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "date", name="uq_paper_v2_snap_portfolio_date"
        ),
        Index("ix_paper_v2_snap_portfolio_date", "portfolio_id", "date"),
    )


class PaperV2ParityCheck(Base):
    """Persisted monthly shadow-parity report (specs/v3/11 §2/§7.1, V11.2).

    The daily task computes a ``paper_v2.parity.ParityReport`` at each forward
    month-end and only logs it; this table durably records it so the read-only
    ``/v2/paper/parity`` badge can reflect the latest fidelity check (and the
    history strip can show a BREAK that reset the 6-month clock). Idempotent on
    ``(portfolio_id, as_of)``.
    """

    __tablename__ = "paper_v2_parity_check"
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_v2_portfolio.id"), nullable=False)
    as_of = Column(Date, nullable=False)  # rebalance date the check ran on
    passed = Column(Boolean, nullable=False)
    max_dev_bps = Column(Float, nullable=False)  # vs PARITY_TOL_BPS (25.0)
    tol_bps = Column(Float, nullable=False, default=25.0)
    breaches = Column(JSON, nullable=True)  # [[isin, dev_bps], ...]
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "as_of", name="uq_paper_v2_parity_portfolio_asof"
        ),
        Index("ix_paper_v2_parity_portfolio_asof", "portfolio_id", "as_of"),
    )


class MarketBreadth(Base):
    __tablename__ = "market_breadth"
    date = Column(Date, primary_key=True)
    breadth_pct = Column(Float, nullable=False)
    stock_count = Column(Integer, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
