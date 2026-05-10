from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.session import get_db
from app.db.models import TechnicalSignal, PipelineRun, Stock, FundamentalData, FundamentalCache
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.fetcher import fetch_stock_data
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

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

from pydantic import BaseModel
from app.db.session import SessionLocal

class ScreenerRequest(BaseModel):
    limit: int | None = None

def run_pipeline_wrapper(limit: int | None):
    db = SessionLocal()
    try:
        run_pipeline(db, limit=limit)
    finally:
        db.close()

@router.post("/screener/run")
def trigger_screener(request: ScreenerRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Concurrency Guard
    existing_run = db.query(PipelineRun).filter(PipelineRun.status == "running").first()
    if existing_run:
        logger.error(f"Pipeline already running: {existing_run.run_id}")
        raise HTTPException(status_code=409, detail="Pipeline is already running")
        
    background_tasks.add_task(run_pipeline_wrapper, limit=request.limit)
    return {"message": f"Pipeline started{' with limit ' + str(request.limit) if request.limit else ''}"}

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
