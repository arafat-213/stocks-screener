from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.session import get_db, SessionLocal
from app.db import models
from app.backtest.engine import run_backtest, BacktestConfig
from pydantic import BaseModel, Field
from typing import List, Optional
import datetime
import json
import uuid

router = APIRouter(prefix="/backtest", tags=["backtest"])

class BacktestRequest(BaseModel):
    score_threshold: float = Field(default=45.0, ge=0, le=100,
        description="Minimum score. Range 0-75 for tech-only, 0-100 with fundamentals. Crossover signals score ~45-55. Extended trend signals score ~20-35.")
    holding_days: int = Field(default=20, ge=1, le=252)
    stop_loss_pct: float = Field(default=7.0, ge=0, le=50,
        description="0 disables stop-loss.")
    target_pct: float = Field(default=0.0, ge=0, le=200,
        description="0 disables profit target.")
    trailing_stop_pct: float = Field(default=0.0, ge=0, le=50,
        description="Percentage drop from peak to trigger exit.")
    require_volume_breakout: bool = Field(default=False,
        description="If true, requires volume > 2x SMA20 for entry.")
    use_regime_filter: bool = Field(default=True,
        description="If true, only enters trades when Nifty is in a bull regime.")
    include_fundamentals: bool = False
    symbol_limit: Optional[int] = Field(default=None, ge=1, le=500)
    date_from: Optional[str] = None   # "YYYY-MM-DD"
    date_to: Optional[str] = None     # "YYYY-MM-DD"
    starting_capital: float = Field(default=1000000.0, ge=10000)
    position_size: float = Field(default=10000.0, ge=100)

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
            "pct": round((run.symbols_done or 0) / max(run.symbols_total or 1, 1) * 100, 1)
        },
        "error_message": run.error_message,
        "metrics": None
    }
    if run.status == 'complete':
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
            "benchmark_return_pct": run.benchmark_return_pct,
        }
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
        "ema_signal": trade.ema_signal
    }

@router.post("/run")
def start_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Starts a backtest as a background task.
    Returns run_id immediately; poll GET /api/backtest/{run_id} for status.
    """
    # Validate and parse dates
    date_from = datetime.date.fromisoformat(request.date_from) if request.date_from else None
    date_to   = datetime.date.fromisoformat(request.date_to)   if request.date_to   else None

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
        include_fundamentals=request.include_fundamentals,
        symbol_limit=request.symbol_limit,
        date_from=date_from,
        date_to=date_to,
        starting_capital=request.starting_capital,
        position_size=request.position_size
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
    runs = db.query(models.BacktestRun).order_by(desc(models.BacktestRun.created_at)).limit(20).all()
    return [_serialize_run(r, include_curve=False) for r in runs]

@router.get("/{run_id}")
def get_backtest_run(run_id: str, db: Session = Depends(get_db)):
    """
    Returns full run details including equity curve JSON.
    Poll this endpoint every 3s while status='running'.
    """
    run = db.query(models.BacktestRun).filter(models.BacktestRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _serialize_run(run, include_curve=True)

@router.get("/{run_id}/trades")
def get_backtest_trades(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    sort_by: str = Query(default='exit_date'),
    sort_dir: str = Query(default='desc'),
    exit_reason: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """
    Paginated trade list for a backtest run.
    Supports filtering by exit_reason ('holding_period', 'stop_loss', 'target').
    """
    run = db.query(models.BacktestRun).filter(models.BacktestRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    q = db.query(models.BacktestTrade).filter(models.BacktestTrade.run_id == run_id)
    if exit_reason:
        q = q.filter(models.BacktestTrade.exit_reason == exit_reason)

    total = q.count()

    # Sorting
    sort_col = getattr(models.BacktestTrade, sort_by, models.BacktestTrade.exit_date)
    q = q.order_by(desc(sort_col) if sort_dir == 'desc' else sort_col)

    trades = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "trades": [_serialize_trade(t) for t in trades]
    }
