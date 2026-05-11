from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, func
from app.db.session import get_db
from app.db.models import TechnicalSignal, PipelineRun, Stock, FundamentalData, FundamentalCache
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.fetcher import fetch_stock_data
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/stocks/search")
def search_stocks(q: str = "", db: Session = Depends(get_db)):
    if len(q) < 2:
        return []
        
    # Strip .NS (case-insensitive) for searching
    query = q.strip()
    if query.upper().endswith(".NS"):
        query = query[:-3]
    
    # Ordering: Exact symbol match, then symbol starts with, then name contains
    results = db.query(Stock).filter(
        or_(
            Stock.symbol.ilike(f"%{query}%"),
            Stock.name.ilike(f"%{query}%")
        )
    ).limit(50).all() 
    
    # Sort in Python for smart ordering
    query_upper = query.upper()
    def sort_key(s):
        if s.symbol == query_upper: return 0
        if s.symbol.startswith(query_upper): return 1
        if s.name.lower().startswith(query.lower()): return 2
        return 3
        
    sorted_results = sorted(results, key=sort_key)
    final_results = sorted_results[:15]
    
    return [
        {"symbol": s.symbol, "name": s.name, "sector": s.sector} 
        for s in final_results
    ]

@router.get("/stocks/top")
def get_top_stocks(db: Session = Depends(get_db)):
    scores = db.query(TechnicalSignal).filter(TechnicalSignal.timeframe == 'D').order_by(desc(TechnicalSignal.entry_score)).limit(20).all()
    return [{"symbol": s.symbol, "score": s.entry_score, "rsi": s.rsi, "signal": s.ema_signal} for s in scores]

@router.get("/stocks/{symbol}")
def get_stock_detail(symbol: str, db: Session = Depends(get_db)):
    # 1. Symbol Handling: Strip .NS for DB lookups
    clean_symbol = symbol.replace(".NS", "").upper()
    
    # 2. DB Lookup
    stock = db.query(Stock).filter(Stock.symbol == clean_symbol).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    # 3. Price Data: 1 year OHLCV
    hist, info = fetch_stock_data(clean_symbol, append_ns=True, period="1y")
    ohlcv = []
    if hist is not None and not hist.empty:
        # Convert index (DatetimeIndex) to date string
        hist.reset_index(inplace=True)
        for _, row in hist.iterrows():
            ohlcv.append({
                "time": row["Date"].strftime("%Y-%m-%d") if "Date" in row else row["index"].strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"])
            })

    # 4. Latest Scores (MTF)
    scores = {}
    for tf in ['D', 'W', 'M']:
        signal = db.query(TechnicalSignal).filter(
            TechnicalSignal.symbol == clean_symbol,
            TechnicalSignal.timeframe == tf
        ).order_by(desc(TechnicalSignal.date)).first()
        
        if signal:
            scores[tf] = {
                "score": signal.entry_score,
                "ema_signal": signal.ema_signal,
                "volume_signal": signal.volume_signal,
                "rsi_signal": signal.rsi_signal,
                "rsi": signal.rsi,
                "adx": signal.adx,
                "rs_score": signal.rs_score,
                "momentum_1m": signal.momentum_1m,
                "momentum_3m": signal.momentum_3m,
                "momentum_6m": signal.momentum_6m,
                "momentum_12m": signal.momentum_12m
            }
        else:
            scores[tf] = None

    # 5. Score History (Last 30 daily)
    history_signals = db.query(TechnicalSignal).filter(
        TechnicalSignal.symbol == clean_symbol,
        TechnicalSignal.timeframe == 'D'
    ).order_by(desc(TechnicalSignal.date)).limit(30).all()
    
    score_history = [
        {"date": s.date.strftime("%Y-%m-%d"), "score": s.entry_score} 
        for s in reversed(history_signals)
    ]

    # 6. Fundamentals
    fund_cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == clean_symbol).first()
    fund_data = db.query(FundamentalData).filter(FundamentalData.symbol == clean_symbol).order_by(desc(FundamentalData.date)).first()

    fundamentals = {
        "pe": fund_data.pe if fund_data else None,
        "roe": fund_data.roe if fund_data else None,
        "debt_equity": fund_cache.de_ratio if fund_cache else (fund_data.debt_equity if fund_data else None),
        "sector": fund_cache.sector if fund_cache else (stock.sector if stock else None),
        "eps_growth": fund_data.eps_growth if fund_data else None,
        "market_cap": fund_data.market_cap if fund_data else (stock.market_cap if stock else None)
    }

    return {
        "symbol": clean_symbol,
        "name": stock.name,
        "ohlcv": ohlcv,
        "scores": scores,
        "score_history": score_history,
        "fundamentals": fundamentals
    }

@router.post("/stocks/{symbol}/refresh-cache")
def refresh_stock_cache(symbol: str, db: Session = Depends(get_db)):
    clean_symbol = symbol.replace(".NS", "").upper()
    cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == clean_symbol).first()
    if not cache:
        cache = FundamentalCache(symbol=clean_symbol)
        db.add(cache)
    
    cache.force_refresh = True
    cache.retry_after = None
    db.commit()
    return {"message": f"Force refresh scheduled for {clean_symbol}"}

@router.get("/stocks/{symbol}/cache-status")
def get_stock_cache_status(symbol: str, db: Session = Depends(get_db)):
    clean_symbol = symbol.replace(".NS", "").upper()
    cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == clean_symbol).first()
    if not cache:
        return {"status": "not_cached"}
    
    return {
        "symbol": clean_symbol,
        "last_updated": cache.last_updated,
        "retry_after": cache.retry_after,
        "fetch_attempts": cache.fetch_attempts,
        "last_error": cache.last_error,
        "force_refresh": cache.force_refresh,
        "cache_version": cache.cache_version
    }

from pydantic import BaseModel
from app.db.session import SessionLocal
from app.db.models import PipelineError

class ScreenerRequest(BaseModel):
    limit: int | None = None
    resume_run_id: str | None = None

def run_pipeline_wrapper(limit: int | None, resume_run_id: str | None = None):
    db = SessionLocal()
    try:
        run_pipeline(db, limit=limit, resume_run_id=resume_run_id)
    finally:
        db.close()

@router.post("/screener/run")
def trigger_screener(request: ScreenerRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Concurrency Guard
    existing_run = db.query(PipelineRun).filter(PipelineRun.status == "running").first()
    if existing_run and not request.resume_run_id:
        logger.error(f"Pipeline already running: {existing_run.run_id}")
        raise HTTPException(status_code=409, detail="Pipeline is already running")
        
    background_tasks.add_task(run_pipeline_wrapper, limit=request.limit, resume_run_id=request.resume_run_id)
    return {
        "message": f"Pipeline started",
        "limit": request.limit,
        "resume_run_id": request.resume_run_id
    }

@router.get("/pipeline/errors")
def get_pipeline_errors(
    run_id: str, 
    phase: str | None = None, 
    error_type: str | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(PipelineError).filter(PipelineError.run_id == run_id)
    if phase:
        query = query.filter(PipelineError.phase == phase)
    if error_type:
        query = query.filter(PipelineError.error_type == error_type)
    
    errors = query.order_by(PipelineError.occurred_at.desc()).limit(100).all()
    return errors

from app.pipeline.rs_ranks import compute_rs_ranks
from app.screens.base import get_latest_signal_date
import datetime

@router.post("/pipeline/recompute-rs")
def recompute_rs(
    date: str | None = None, 
    db: Session = Depends(get_db)
):
    if date:
        try:
            target_date = datetime.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        latest = get_latest_signal_date(db, timeframe='D')
        target_date = latest.date() if hasattr(latest, 'date') else latest
    
    summary = compute_rs_ranks(db, target_date)
    return summary

@router.post("/pipeline/stop")
def stop_pipeline(db: Session = Depends(get_db)):
    from app.pipeline.orchestrator import request_pipeline_stop
    request_pipeline_stop(db)
    return {"message": "Stop signal sent to pipeline"}

@router.get("/pipeline/status")
def get_pipeline_status(db: Session = Depends(get_db)):
    run = db.query(PipelineRun).order_by(desc(PipelineRun.timestamp)).first()
    if not run: return {"status": "idle"}
    return {"status": run.status, "last_run": run.timestamp, "scored": run.stocks_scored}
