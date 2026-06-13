import json
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.utils import sanitize_for_json
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    rsi_min: float = Field(default=35.0, ge=0, le=100)
    rsi_max: float = Field(default=65.0, ge=0, le=100)
    score_threshold: float = Field(
        default=55.0,
        ge=0,
        le=100,
        description=(
            "Minimum signal quality score (0–100 scale). The practical score ceiling "
            "is ~97 due to the same-day EMA/MACD correlation cap. Default 55 ≈ 56% of max. "
            "At 55, a fresh EMA cross with ADX ≥ 25 and above 200EMA but no volume "
            "scores roughly 58–62 and will pass. A weak cross with no MACD confirmation "
            "and no trend scores ~35 and will be filtered."
        ),
    )
    holding_days: int = Field(
        default=50,
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
    max_pct_from_52w_high: float = Field(
        default=0.0,
        description="0.0 = disabled. Negative values = max distance below 52w high.",
    )
    use_regime_position_scaling: bool = True
    regime_bull_rsi_threshold: float = Field(default=60.0, ge=50.0, le=90.0)
    regime_bear_rsi_threshold: float = Field(default=45.0, ge=30.0, le=60.0)
    regime_adx_threshold: float = Field(default=20.0, ge=0.0, le=50.0)
    regime_adx_floor: float = Field(default=15.0, ge=0.0, le=100.0)
    min_market_breadth_pct: float = Field(default=40.0, ge=0.0, le=100.0)
    regime_bull_position_pct: float = Field(default=12.0, ge=1.0, le=100.0)
    regime_neutral_position_pct: float = Field(default=7.0, ge=0.0, le=100.0)
    regime_bear_position_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    regime_confirmation_days: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of consecutive days a regime must hold before switching. Prevents whipsaws.",
    )
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
    initial_stop_atr_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=10.0,
        description="ATR multiplier for the INITIAL stop loss anchoring.",
    )
    risk_reward_ratio: float = Field(
        default=2.5,
        ge=0.5,
        le=10.0,
        description="2.5R target aligns with high-conviction trend initiation setups.",
    )
    use_atr_stops: bool = Field(
        default=True, description="Use ATR-based stop loss instead of fixed percentage."
    )
    use_atr_trailing_stop: bool = Field(
        default=True,
        description="Re-enabled. Activates at 1R gain, trails 1 ATR below peak.",
    )
    atr_trailing_multiplier: float = Field(
        default=1.0,
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
            "Activate after 2.5 ATR gain. With atr_multiplier=2.0 and risk_reward=2.5, "
            "target is at 4.5 ATR — trail activates midway to target. "
            "Floor = activation - multiplier = 0.5 ATR profit when first fired."
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
            "For bullish_pullback signals: wait up to 8 bars for price to pull back to EMA21 "
            "before entering. Dramatically improves entry price vs. buying immediately at next-day open. "
            "Signals that don't pull back within 8 bars are skipped."
        ),
    )
    use_pullback_fallback: bool = Field(
        default=False,
        description=(
            "If true, enter on the open of the last wait bar if price got within 8% of EMA21 but never touched it."
        ),
    )
    pullback_max_wait_bars: int = Field(default=8, ge=1, le=15)
    pullback_tolerance_pct: float = Field(
        default=3.0,
        ge=0.5,
        le=5.0,
        description="How close to EMA21 price must come to trigger pullback entry (%).",
    )
    pullback_ema21_threshold_pct: float = Field(
        default=3.0,
        ge=1.0,
        le=5.0,
        description="Distance from EMA21 to qualify as a 'bullish_pullback' signal (%).",
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
    max_signal_volatility_mult: float = Field(default=1.5, ge=0.5, le=5.0)
    min_adx: float = Field(
        default=25.0,
        ge=0,
        le=50,
        description="Minimum ADX required to enter a trade. 0 disables the filter.",
    )
    tier1_adx_threshold: float = Field(
        default=30.0,
        ge=0,
        le=100,
        description="ADX required for Tier 1 classification.",
    )
    min_signal_tier: int = Field(
        default=2,
        ge=1,
        le=3,
        description="1: Strict (Both Vol + ADX), 2: Relaxed (Either).",
    )

    symbol_limit: Optional[int] = Field(default=None, ge=1, le=2500)
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
        default=3.0,
        ge=0.1,
        le=5.0,
        description="3.0% risk per trade. Scaled for regime-based aggression.",
    )
    max_position_pct: float = Field(
        default=20.0,
        ge=1.0,
        le=50.0,
        description="Cap at 20% of capital to allow meaningful concentration in bull regimes.",
    )
    max_concurrent_positions: int = Field(
        default=0,
        ge=0,
        le=50,
        description="Maximum open positions at any time. 0 = unlimited. Enable only after baseline >150 trades is validated.",
    )
    max_sector_positions: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum open positions in a single sector. 0 = unlimited.",
    )

    # Indicator Weights (Phase 3 & 4)
    ema_weight: float = Field(default=28.5, ge=0, le=100)
    macd_weight: float = Field(default=21.5, ge=0, le=100)
    rsi_weight: float = Field(default=21.5, ge=0, le=100)
    volume_weight: float = Field(default=21.5, ge=0, le=100)
    trend_weight: float = Field(default=7.0, ge=0, le=100)
    ema200_weight: float = Field(default=7.0, ge=0, le=100)

    # State Engine (Phase 4)
    rsi_overbought_threshold: float = Field(default=80.0, ge=50, le=100)
    use_state_based_exits: bool = Field(default=True)


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
        "regime_map_json": run.regime_map_json,
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
            "max_drawdown_duration": run.max_drawdown_duration,
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

    # Trigger Celery task
    from app.tasks import execute_backtest_task

    execute_backtest_task.delay(run_id, request.model_dump())

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
    result = [_serialize_run(r, include_curve=False) for r in runs]
    return sanitize_for_json(result)


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
    result = _serialize_run(run, include_curve=True)
    return sanitize_for_json(result)


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

    result = {
        "total": total,
        "page": page,
        "page_size": page_size,
        "trades": [_serialize_trade(t) for t in trades],
    }
    return sanitize_for_json(result)
