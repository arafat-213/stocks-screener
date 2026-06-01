import datetime
import json
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.backtest.engine import BacktestConfig, run_backtest
from app.db import models
from app.db.session import SessionLocal, get_db

router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    score_threshold: float = Field(
        default=60.0,
        ge=0,
        le=100,
        description=(
            "Signal quality bar on a 0–100 intention scale. "
            "Automatically normalised: the max possible score is 70, so a threshold of 60 becomes an effective "
            "35 (50% of 70). "
            "Note: the MACD same-day cap (8 pts) means a fresh EMA+MACD cross without "
            "volume scores ~38, which requires this threshold to be ≤54 to pass."
        ),
    )
    holding_days: int = Field(
        default=35,  # was 30; 5 extra days for 1.5R targets
        ge=1,
        le=252,
    )
    stop_loss_pct: float = Field(
        default=7.0, ge=0, le=50, description="0 disables stop-loss."
    )
    target_pct: float = Field(
        default=0.0, ge=0, le=200, description="0 disables profit target."
    )
    trailing_stop_pct: float = Field(
        default=0.0,
        ge=0,
        le=50,
        description="Percentage drop from peak to trigger exit.",
    )
    require_volume_breakout: bool = Field(
        default=False,
        description="Requires volume > 2x SMA20 for entry. The tier gate (EMA cross/pullback) already enforces signal quality.",
    )
    use_regime_filter: bool = True
    require_weekly_confirmation: bool = Field(
        default=False,
        description="Requires the Weekly timeframe to be bullish (RSI > 50, price > EMA26) "
        "before entering a Daily signal. The regime filter already provides macro "
        "context; enable this for additional confirmation at the cost of signal frequency.",
    )
    require_monthly_confirmation: bool = Field(
        default=False,
        description="Additionally requires the Monthly signal to be bullish.",
    )
    atr_multiplier: float = Field(
        default=2.0, ge=1.0, le=10.0, description="Multiplier for ATR-based stop loss."
    )
    risk_reward_ratio: float = Field(
        default=1.5,
        ge=0.5,
        le=10.0,
        description="1.5R target is reachable within 35 days on NSE momentum setups. "
        "2.0R requires 12-16% move in 30 days — only top 20% of trades qualify.",
    )
    use_atr_stops: bool = Field(
        default=True, description="Use ATR-based stop loss instead of fixed percentage."
    )
    use_atr_trailing_stop: bool = Field(
        default=True,
        description="Re-enabled. Activates at 1R gain, trails 1 ATR below peak.",
    )
    atr_trailing_multiplier: float = Field(
        default=1.0,  # was 1.5 — tighter trail locks in more profit
        ge=0.5,
        le=5.0,
        description=(
            "Trail 1.0 ATR below the peak. With activation=2.5, first-fire floor = +1.5 ATR. "
            "Keep < activation to ensure positive profit on every trail exit."
        ),
    )
    atr_trailing_activation: float = Field(
        default=2.5,
        ge=0.5,
        le=5.0,
        description=(
            "Activate after 2.5 ATR gain. With atr_multiplier=2.0 and risk_reward=1.5, "
            "target is at 3.0 ATR — trail activates at 83% of target distance. "
            "Floor = activation - multiplier = 1.5 ATR profit when first fired."
        ),
    )
    use_partial_exits: bool = Field(
        default=False,
        description="Disabled. Doubles cost drag per setup; ATR trailing stop is superior.",
    )
    use_signal_invalidation_exit: bool = Field(
        default=False,
        description="Exit if close drops >3% below entry for 2 consecutive bars.",
    )
    invalidation_threshold_pct: float = Field(default=3.0, ge=1.0, le=10.0)
    require_consolidation: bool = Field(
        default=True,
        description=(
            "Only enter signals where the prior 15 bars had a High-Low range ≤12%. "
            "Prevents chasing EMA crosses that occur after large moves."
        ),
    )
    consolidation_bars: int = Field(default=15, ge=5, le=30)
    use_pullback_entry: bool = Field(
        default=True,
        description=(
            "For bullish_cross signals: wait up to 8 bars for price to pull back to EMA20 "
            "before entering. Dramatically improves entry price vs. chasing at next-day open. "
            "Signals that don't pull back within 8 bars are skipped."
        ),
    )
    pullback_max_wait_bars: int = Field(default=8, ge=1, le=15)
    pullback_tolerance_pct: float = Field(
        default=3.0,  # was 2.0 — 2% is too tight for NSE mid/smallcap volatility
        ge=0.5,
        le=5.0,
        description="How close to EMA20 price must come to trigger pullback entry (%).",
    )
    screen_signal_mode: bool = Field(
        default=False,
        description=(
            "Model B: Use screen qualification dates directly as entry signals. "
            "Bypasses technical filters (EMA cross, volume, RSI, consolidation) "
            "since the screen already validated quality. Use for Momentum/Value/Quality screens. "
            "Leave False for event-driven screens (actionable-entries) where EMA-cross timing is preferred."
        ),
    )
    screen_membership_window_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description=(
            "Model A only: How many calendar days back to look for screen membership "
            "relative to a technical signal date. Ensures symbols are only traded while "
            "actively meeting screen criteria."
        ),
    )
    screen_reentry_gap_days: int = Field(
        default=60,
        ge=7,
        le=365,
        description=(
            "Model B only: Minimum calendar days gap required before the same stock "
            "can generate a new signal from screen re-qualification. Prevents "
            "excessive trades when a stock stays in a screen for months."
        ),
    )
    screen_driven_rsi_max: float = Field(
        default=75.0,
        ge=50.0,
        le=90.0,
        description=(
            "Model B only: Maximum RSI at screen qualification date. "
            "Prevents entering momentum stocks at peak overbought extension."
        ),
    )
    consolidation_max_range_pct: float = Field(default=12.0, ge=5.0, le=25.0)
    min_adx: float = Field(
        default=25.0,
        ge=0,
        le=50,
        description="Minimum ADX required to enter a trade. 0 disables the filter.",
    )
    symbol_limit: Optional[int] = Field(default=None, ge=1, le=500)
    screen_slug: Optional[str] = Field(
        default=None, description="Slug of the screen to filter symbols by."
    )
    date_from: Optional[str] = None  # "YYYY-MM-DD"
    date_to: Optional[str] = None  # "YYYY-MM-DD"
    starting_capital: float = Field(default=1000000.0, ge=10000)
    position_size: float = Field(default=10000.0, ge=100)
    use_volatility_sizing: bool = Field(
        default=True,
        description=(
            "When True, sizes each position so a stop-loss hit risks "
            "risk_per_trade_pct% of starting_capital. Requires ATR data. "
            "Falls back to flat position_size when ATR is unavailable."
        ),
    )
    risk_per_trade_pct: float = Field(
        default=0.5,
        ge=0.1,
        le=5.0,
        description="0.5% risk per trade. At 333 trades/5y, reduces turnover to sustainable levels.",
    )
    max_position_pct: float = Field(
        default=5.0,
        ge=1.0,
        le=50.0,
        description="Cap at 5% of capital. With 333 trades/5y, 10% cap created 16.6% cost drag.",
    )
    max_concurrent_positions: int = Field(
        default=0,
        ge=0,
        le=50,
        description="Maximum open positions at any time. 0 = unlimited. Enable only after baseline >150 trades is validated.",
    )
    max_sector_positions: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Maximum open positions in a single sector. 0 = unlimited.",
    )


def _serialize_run(run: models.BacktestRun, include_curve: bool) -> dict:
    config = json.loads(run.config) if run.config else {}
    result = {
        "run_id": run.run_id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "status": run.status,
        "config": config,
        "starting_capital": run.starting_capital,
        "position_size": run.position_size,
        "progress": {
            "symbols_done": run.symbols_done or 0,
            "symbols_total": run.symbols_total or 0,
            "pct": round(
                (run.symbols_done or 0) / max(run.symbols_total or 1, 1) * 100, 1
            ),
        },
        "error_message": run.error_message,
        "metrics": None,
    }
    if run.status == "complete":
        result["metrics"] = {
            "total_trades": run.total_trades,
            "winning_trades": run.winning_trades,
            "win_rate": run.win_rate,
            "avg_return_pct": run.avg_return_pct,
            "median_return_pct": run.median_return_pct,
            "best_trade_pct": run.best_trade_pct,
            "worst_trade_pct": run.worst_trade_pct,
            "max_drawdown_pct": run.max_drawdown_pct,
            "sharpe_ratio": run.sharpe_ratio,
            "total_return_pct": run.total_return_pct,
            "gross_return_pct": run.gross_return_pct,
            "total_cost_drag_pct": run.total_cost_drag_pct,
            "benchmark_return_pct": run.benchmark_return_pct,
            "expectancy": run.expectancy,
            "profit_factor": run.profit_factor,
            "avg_win_pct": run.avg_win_pct,
            "avg_loss_pct": run.avg_loss_pct,
            "low_sample_warning": (run.total_trades or 0) < 100,
        }
        if run.exit_breakdown_json:
            result["metrics"]["exit_breakdown"] = json.loads(run.exit_breakdown_json)

        if include_curve and run.equity_curve_json:
            result["equity_curve"] = json.loads(run.equity_curve_json)
    return result


def _serialize_trade(trade: models.BacktestTrade):
    return {
        "id": trade.id,
        "symbol": trade.symbol,
        "sector": trade.sector,
        "signal_date": trade.signal_date.isoformat() if trade.signal_date else None,
        "entry_date": trade.entry_date.isoformat() if trade.entry_date else None,
        "exit_date": trade.exit_date.isoformat() if trade.exit_date else None,
        "exit_reason": trade.exit_reason,
        "signal_score": trade.signal_score,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "return_pct": trade.return_pct,
        "rsi_at_signal": trade.rsi_at_signal,
        "adx_at_signal": trade.adx_at_signal,
        "ema_signal": trade.ema_signal,
    }


@router.post("/run")
def start_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Starts a backtest as a background task.
    Returns run_id immediately; poll GET /api/backtest/{run_id} for status.
    """
    # Validate and parse dates
    date_from = (
        datetime.date.fromisoformat(request.date_from) if request.date_from else None
    )
    date_to = datetime.date.fromisoformat(request.date_to) if request.date_to else None

    run_id = str(uuid.uuid4())

    # Save run record
    db_run = models.BacktestRun(
        run_id=run_id,
        status="pending",
        config=json.dumps(request.model_dump(), default=str),
        symbols_total=0,
        symbols_done=0,
        starting_capital=request.starting_capital,
        position_size=request.position_size,
    )
    db.add(db_run)
    db.commit()

    # Prepare config for engine
    config = BacktestConfig(
        score_threshold=request.score_threshold,
        holding_days=request.holding_days,
        stop_loss_pct=request.stop_loss_pct,
        target_pct=request.target_pct,
        trailing_stop_pct=request.trailing_stop_pct,
        require_volume_breakout=request.require_volume_breakout,
        use_regime_filter=request.use_regime_filter,
        require_weekly_confirmation=request.require_weekly_confirmation,
        require_monthly_confirmation=request.require_monthly_confirmation,
        atr_multiplier=request.atr_multiplier,
        risk_reward_ratio=request.risk_reward_ratio,
        use_atr_stops=request.use_atr_stops,
        use_atr_trailing_stop=request.use_atr_trailing_stop,
        atr_trailing_multiplier=request.atr_trailing_multiplier,
        atr_trailing_activation=request.atr_trailing_activation,
        use_partial_exits=request.use_partial_exits,
        use_signal_invalidation_exit=request.use_signal_invalidation_exit,
        invalidation_threshold_pct=request.invalidation_threshold_pct,
        min_adx=request.min_adx,
        symbol_limit=request.symbol_limit,
        screen_slug=request.screen_slug,
        date_from=date_from,
        date_to=date_to,
        starting_capital=request.starting_capital,
        position_size=request.position_size,
        use_volatility_sizing=request.use_volatility_sizing,
        risk_per_trade_pct=request.risk_per_trade_pct,
        max_position_pct=request.max_position_pct,
        max_concurrent_positions=request.max_concurrent_positions,
        max_sector_positions=request.max_sector_positions,
        require_consolidation=request.require_consolidation,
        use_pullback_entry=request.use_pullback_entry,
        pullback_max_wait_bars=request.pullback_max_wait_bars,
        pullback_tolerance_pct=request.pullback_tolerance_pct,
        consolidation_bars=request.consolidation_bars,
        consolidation_max_range_pct=request.consolidation_max_range_pct,
        screen_signal_mode=request.screen_signal_mode,
        screen_membership_window_days=request.screen_membership_window_days,
        screen_reentry_gap_days=request.screen_reentry_gap_days,
        screen_driven_rsi_max=request.screen_driven_rsi_max,
    )

    # Add to background tasks
    # We use SessionLocal() because run_backtest needs its own session in a separate thread
    def run_wrapper(rid, cfg):
        engine_db = SessionLocal()
        try:
            run_backtest(engine_db, rid, cfg)
        finally:
            engine_db.close()

    background_tasks.add_task(run_wrapper, run_id, config)

    return {"run_id": run_id, "status": "pending"}


@router.get("/runs")
def list_backtest_runs(db: Session = Depends(get_db)):
    """Returns the 20 most recent backtest runs (summary only, no trades)."""
    runs = (
        db.query(models.BacktestRun)
        .order_by(desc(models.BacktestRun.created_at))
        .limit(20)
        .all()
    )
    return [_serialize_run(r, include_curve=False) for r in runs]


@router.get("/{run_id}")
def get_backtest_run(run_id: str, db: Session = Depends(get_db)):
    """
    Returns full run details including equity curve JSON.
    Poll this endpoint every 3s while status='running'.
    """
    run = (
        db.query(models.BacktestRun).filter(models.BacktestRun.run_id == run_id).first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _serialize_run(run, include_curve=True)


@router.get("/{run_id}/trades")
def get_backtest_trades(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    sort_by: str = Query(default="exit_date"),
    sort_dir: str = Query(default="desc"),
    exit_reason: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Paginated trade list for a backtest run.
    Supports filtering by exit_reason ('holding_period', 'stop_loss', 'target').
    """
    run = (
        db.query(models.BacktestRun).filter(models.BacktestRun.run_id == run_id).first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    q = db.query(models.BacktestTrade).filter(models.BacktestTrade.run_id == run_id)
    if exit_reason:
        q = q.filter(models.BacktestTrade.exit_reason == exit_reason)

    total = q.count()

    # Sorting
    sort_col = getattr(models.BacktestTrade, sort_by, models.BacktestTrade.exit_date)
    q = q.order_by(desc(sort_col) if sort_dir == "desc" else sort_col)

    trades = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "trades": [_serialize_trade(t) for t in trades],
    }
