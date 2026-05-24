from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from datetime import date
from typing import Optional

from app.db.session import get_db
from app.db.models import Watchlist, TechnicalSignal, FundamentalCache
from app.pipeline.trade_setup import compute_trade_setup

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

class WatchlistAddRequest(BaseModel):
    symbol: str
    signal_date: date

class WatchlistResponse(BaseModel):
    id: int
    symbol: str
    added_date: date
    signal_date: date
    quality_tier: Optional[str] = None
    signal_score: Optional[float] = None
    planned_entry_low: Optional[float] = None
    planned_entry_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    status: str

    class Config:
        from_attributes = True

@router.post("/", response_model=WatchlistResponse)
def add_to_watchlist(req: WatchlistAddRequest, db: Session = Depends(get_db)):
    # 1. Check if already exists
    existing = db.query(Watchlist).filter_by(
        symbol=req.symbol, signal_date=req.signal_date
    ).first()
    if existing:
        return existing

    # 2. Fetch TechnicalSignal for metadata
    # We look for 'D' timeframe signal on that date
    signal = db.query(TechnicalSignal).filter(
        TechnicalSignal.symbol == req.symbol,
        func.date(TechnicalSignal.date) == req.signal_date,
        TechnicalSignal.timeframe == 'D'
    ).first()

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found for this date and symbol")

    # 3. Derive metadata
    # quality_tier from FundamentalCache
    fund = db.query(FundamentalCache).filter_by(symbol=req.symbol).first()
    quality_tier = "C"
    if fund:
        if fund.profitability_streak_passed and fund.de_check_passed and fund.fcf_positive:
            quality_tier = "A"
        elif fund.profitability_streak_passed or fund.de_check_passed:
            quality_tier = "B"
    
    # trade setup levels
    setup = compute_trade_setup(signal)
    
    entry_low = setup["entry_zone"]["low"] if setup else None
    entry_high = setup["entry_zone"]["high"] if setup else None
    stop_loss = setup["stop_loss"] if setup else None
    target = setup["targets"][-1]["level"] if setup and setup.get("targets") else None

    # 4. Create Watchlist entry
    new_entry = Watchlist(
        symbol=req.symbol,
        signal_date=req.signal_date,
        quality_tier=quality_tier,
        signal_score=signal.entry_score,
        planned_entry_low=entry_low,
        planned_entry_high=entry_high,
        stop_loss=stop_loss,
        target=target,
        status="watching"
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    
    return new_entry
