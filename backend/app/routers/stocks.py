import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import (
    FundamentalCache,
    PipelineError,
    PipelineRun,
    Stock,
    TechnicalSignal,
)
from app.db.session import get_db
from app.pipeline.ohlcv_cache import OHLCVCache
from app.pipeline.rs_ranks import compute_rs_ranks
from app.pipeline.trade_setup import compute_trade_setup
from app.screens.base import get_latest_signal_date
from app.tasks import execute_pipeline_task

router = APIRouter(prefix="/stocks", tags=["stocks"])
logger = logging.getLogger(__name__)


@router.get("/")
def get_stocks(
    db: Session = Depends(get_db),
    sector: str | None = None,
    industry: str | None = None,
    limit: int = 100,
):
    query = db.query(Stock)
    if sector:
        query = query.filter(Stock.sector == sector)
    if industry:
        query = query.filter(Stock.industry == industry)

    stocks = query.limit(limit).all()
    return stocks


@router.get("/{symbol}")
def get_stock_detail(symbol: str, db: Session = Depends(get_db)):
    symbol_upper = symbol.upper()
    stock = db.query(Stock).filter(Stock.symbol == symbol_upper).first()

    if not stock:
        # Try stripping suffix
        bare_symbol = symbol_upper.split(".")[0]
        stock = db.query(Stock).filter(Stock.symbol == bare_symbol).first()
        if stock:
            symbol_upper = bare_symbol

    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    clean_symbol = symbol_upper

    # 1. Get latest signals across D, W, M
    latest_signals = (
        db.query(TechnicalSignal)
        .filter(TechnicalSignal.symbol == clean_symbol)
        .order_by(TechnicalSignal.date.desc())
        .all()
    )

    scores_map = {}
    for sig in latest_signals:
        if sig.timeframe not in scores_map:
            scores_map[sig.timeframe] = {
                "score": sig.entry_score,
                "ema_signal": sig.ema_signal,
                "rsi": sig.rsi,
                "rsi_signal": sig.rsi_signal,
                "macd": sig.macd,
                "volume_signal": sig.volume_signal,
                "rs_score": sig.rs_score,
                "adx": sig.adx,
                "momentum_1m": sig.momentum_1m,
                "momentum_3m": sig.momentum_3m,
                "momentum_6m": sig.momentum_6m,
                "momentum_12m": sig.momentum_12m,
                "resistance": sig.resistance_level,
                "week52_high": sig.week52_high,
                "week52_low": sig.week52_low,
                "volume_breakout": sig.volume_breakout,
                "is_consolidating": sig.is_consolidating,
                "above_200ema": sig.above_200ema,
                "ema5_level": sig.ema5_level,
                "ema13_level": sig.ema13_level,
                "ema20_level": sig.ema20_level,
                "ema26_level": sig.ema26_level,
            }

    # 2. Get score history (Daily)
    history = (
        db.query(TechnicalSignal)
        .filter(TechnicalSignal.symbol == clean_symbol)
        .filter(TechnicalSignal.timeframe == "D")
        .order_by(TechnicalSignal.date.asc())
        .limit(250)
        .all()
    )
    score_history = [
        {"date": h.date.isoformat(), "score": h.entry_score} for h in history
    ]

    # 3. Get latest fundamentals
    fund = (
        db.query(FundamentalCache)
        .filter(FundamentalCache.symbol == clean_symbol)
        .first()
    )
    fundamentals = {}
    if fund:
        fundamentals = {
            "pe": None,
            "pb": None,
            "roe": fund.roe,
            "roce": fund.roce,
            "debt_equity": fund.de_ratio,
            "market_cap": stock.market_cap,
            "pledged_percent": None,
        }
        from app.db.models import FundamentalData

        latest_fund_data = (
            db.query(FundamentalData)
            .filter(FundamentalData.symbol == clean_symbol)
            .order_by(FundamentalData.date.desc())
            .first()
        )
        if latest_fund_data:
            fundamentals["pe"] = latest_fund_data.pe
            fundamentals["pb"] = latest_fund_data.pb
            fundamentals["pledged_percent"] = latest_fund_data.pledged_percent
            if fundamentals["roe"] is None:
                fundamentals["roe"] = latest_fund_data.roe

    # 4. Get OHLCV Chart Data
    ohlcv = []
    cache = OHLCVCache()
    try:
        df = cache.get(clean_symbol)
        if df is not None and not df.empty:
            for index, row in df.iterrows():
                ohlcv.append(
                    {
                        "time": int(index.timestamp()),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"]),
                    }
                )
    except Exception as e:
        logger.error(f"Error fetching OHLCV for {clean_symbol}: {e}")

    # 5. Get Trade Setup
    setup = None
    daily_sig = (
        db.query(TechnicalSignal)
        .filter(TechnicalSignal.symbol == clean_symbol)
        .filter(TechnicalSignal.timeframe == "D")
        .order_by(TechnicalSignal.date.desc())
        .first()
    )
    if daily_sig:
        setup = compute_trade_setup(daily_sig)

    return {
        "symbol": clean_symbol,
        "name": stock.name,
        "sector": stock.sector,
        "industry": stock.industry,
        "ohlcv": ohlcv,
        "scores": scores_map,
        "score_history": score_history,
        "fundamentals": fundamentals,
        "setup": setup,
    }


@router.get("/{symbol}/history")
def get_stock_history(
    symbol: str, timeframe: str = "D", limit: int = 250, db: Session = Depends(get_db)
):
    symbol_upper = symbol.upper()
    # Check if stock exists to resolve correct symbol
    stock = db.query(Stock).filter(Stock.symbol == symbol_upper).first()
    if not stock:
        bare_symbol = symbol_upper.split(".")[0]
        stock = db.query(Stock).filter(Stock.symbol == bare_symbol).first()
        if stock:
            symbol_upper = bare_symbol

    clean_symbol = symbol_upper

    signals = (
        db.query(TechnicalSignal)
        .filter(TechnicalSignal.symbol == clean_symbol)
        .filter(TechnicalSignal.timeframe == timeframe)
        .order_by(TechnicalSignal.date.desc())
        .limit(limit)
        .all()
    )

    return signals


@router.get("/{symbol}/chart")
def get_chart_data(symbol: str, db: Session = Depends(get_db)):
    """
    Returns OHLCV data from local Parquet cache for charting.
    """
    symbol_upper = symbol.upper()
    stock = db.query(Stock).filter(Stock.symbol == symbol_upper).first()
    if not stock:
        bare_symbol = symbol_upper.split(".")[0]
        stock = db.query(Stock).filter(Stock.symbol == bare_symbol).first()
        if stock:
            symbol_upper = bare_symbol

    clean_symbol = symbol_upper

    cache = OHLCVCache()
    try:
        df = cache.get(clean_symbol)
        if df is None or df.empty:
            return []

        # Convert to lightweight-charts format
        chart_data = []
        for index, row in df.iterrows():
            chart_data.append(
                {
                    "time": int(index.timestamp()),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                }
            )
        return chart_data
    except Exception as e:
        logger.error(f"Chart data error for {clean_symbol}: {e}")
        return []


@router.get("/{symbol}/cache-status")
def get_cache_status(symbol: str, db: Session = Depends(get_db)):
    symbol_upper = symbol.upper()
    stock = db.query(Stock).filter(Stock.symbol == symbol_upper).first()
    if not stock:
        bare_symbol = symbol_upper.split(".")[0]
        stock = db.query(Stock).filter(Stock.symbol == bare_symbol).first()
        if stock:
            symbol_upper = bare_symbol

    clean_symbol = symbol_upper

    cache = OHLCVCache()
    try:
        exists = cache.exists(clean_symbol)
        if not exists:
            return {"exists": False}

        df = cache.get(clean_symbol)
        return {
            "exists": True,
            "rows": len(df),
            "start": df.index[0].isoformat(),
            "end": df.index[-1].isoformat(),
            "last_modified": cache.get_modified_time(clean_symbol),
        }
    except Exception as e:
        return {"exists": False, "error": str(e)}


@router.get("/fundamentals/{symbol}")
def get_fundamental_cache(symbol: str, db: Session = Depends(get_db)):
    symbol_upper = symbol.upper()
    stock = db.query(Stock).filter(Stock.symbol == symbol_upper).first()
    if not stock:
        bare_symbol = symbol_upper.split(".")[0]
        stock = db.query(Stock).filter(Stock.symbol == bare_symbol).first()
        if stock:
            symbol_upper = bare_symbol

    clean_symbol = symbol_upper

    cache = (
        db.query(FundamentalCache)
        .filter(FundamentalCache.symbol == clean_symbol)
        .first()
    )
    if not cache:
        return {"exists": False}

    return {
        "symbol": clean_symbol,
        "last_updated": cache.last_updated,
        "retry_after": cache.retry_after,
        "fetch_attempts": cache.fetch_attempts,
        "last_error": cache.last_error,
        "force_refresh": cache.force_refresh,
        "cache_version": cache.cache_version,
    }


class ScreenerRequest(BaseModel):
    limit: int | None = None
    resume_run_id: str | None = None


@router.post("/screener/run")
def trigger_screener(request: ScreenerRequest, db: Session = Depends(get_db)):
    # Concurrency Guard
    existing_run = db.query(PipelineRun).filter(PipelineRun.status == "running").first()
    if existing_run and not request.resume_run_id:
        logger.error(f"Pipeline already running: {existing_run.run_id}")
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    execute_pipeline_task.delay(
        limit=request.limit, resume_run_id=request.resume_run_id
    )
    return {
        "message": "Pipeline task queued",
        "limit": request.limit,
        "resume_run_id": request.resume_run_id,
    }


@router.get("/pipeline/errors")
def get_pipeline_errors(
    run_id: str,
    phase: str | None = None,
    error_type: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(PipelineError).filter(PipelineError.run_id == run_id)
    if phase:
        query = query.filter(PipelineError.phase == phase)
    if error_type:
        query = query.filter(PipelineError.error_type == error_type)

    errors = query.order_by(PipelineError.occurred_at.desc()).limit(100).all()
    return errors


@router.post("/pipeline/recompute-rs")
def recompute_rs(date: str | None = None, db: Session = Depends(get_db)):
    if date:
        try:
            target_date = datetime.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
            )
    else:
        target_date = get_latest_signal_date(db)

    if not target_date:
        raise HTTPException(status_code=404, detail="No signals found to recompute")

    logger.info(f"Triggering RS rank recomputation for {target_date}")
    compute_rs_ranks(db, target_date)
    return {"message": f"RS ranks recomputed for {target_date}"}


@router.get("/{symbol}/trade-setup")
def get_trade_setup(symbol: str, db: Session = Depends(get_db)):
    symbol_upper = symbol.upper()
    stock = db.query(Stock).filter(Stock.symbol == symbol_upper).first()
    if not stock:
        bare_symbol = symbol_upper.split(".")[0]
        stock = db.query(Stock).filter(Stock.symbol == bare_symbol).first()
        if stock:
            symbol_upper = bare_symbol

    clean_symbol = symbol_upper

    # Get latest Daily signal
    signal = (
        db.query(TechnicalSignal)
        .filter(TechnicalSignal.symbol == clean_symbol)
        .filter(TechnicalSignal.timeframe == "D")
        .order_by(TechnicalSignal.date.desc())
        .first()
    )

    if not signal:
        raise HTTPException(status_code=404, detail="No daily signal found for symbol")

    setup = compute_trade_setup(signal)
    return setup


# routers/stocks.py — temporary cleanup endpoint, remove after use


@router.delete("/alerts/clear-failed")
def clear_failed_alerts(db: Session = Depends(get_db)):
    """Removes alert log entries where the email never actually sent."""
    from app.db.models import AlertLog

    deleted = db.query(AlertLog).filter(AlertLog.email_id.is_(None)).delete()
    db.commit()
    return {"deleted": deleted}
