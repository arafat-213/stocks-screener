from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db import models
from pydantic import BaseModel
from typing import List, Optional
import datetime
from app.pipeline.fetcher import fetch_market_snapshots

router = APIRouter(prefix="/journal", tags=["journal"])

class TradeEntryCreate(BaseModel):
    symbol: str
    entry_price: float
    shares: int
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    signal_date: Optional[datetime.date] = None
    entry_date: Optional[datetime.date] = datetime.date.today()
    watchlist_id: Optional[int] = None
    notes: Optional[str] = None

class TradeCloseRequest(BaseModel):
    exit_price: float
    exit_date: datetime.date
    exit_reason: str

@router.post("/")
def create_entry(data: TradeEntryCreate, db: Session = Depends(get_db)):
    db_entry = models.TradeJournal(
        **data.model_dump(),
        position_value=data.entry_price * data.shares,
        status='open'
    )
    db.add(db_entry)
    
    # Bridge: Update watchlist status if linked
    if data.watchlist_id:
        wl = db.query(models.Watchlist).filter(models.Watchlist.id == data.watchlist_id).first()
        if wl:
            wl.status = 'entered'
            
    db.commit()
    db.refresh(db_entry)
    return db_entry

@router.get("/open")
def get_open_trades(db: Session = Depends(get_db)):
    trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'open').all()
    if not trades:
        return []
    
    symbols = list(set([t.symbol for t in trades]))
    snapshots = fetch_market_snapshots(symbols)
    price_map = {s['symbol']: s['close'] for s in snapshots}
    
    results = []
    for t in trades:
        # Robust fallback: use entry_price if current_price is None or missing
        current_price = price_map.get(t.symbol) or t.entry_price
        
        unrealized_pnl = (current_price - t.entry_price) * t.shares
        
        live_return_pct = 0.0
        if t.entry_price > 0:
            live_return_pct = round(((current_price - t.entry_price) / t.entry_price) * 100, 2)
        
        # Distance calculations
        # dist_to_stop: % from current_price down to stop_loss
        dist_to_stop = 0.0
        if current_price > 0 and t.stop_loss is not None:
            dist_to_stop = round(((current_price - t.stop_loss) / current_price) * 100, 2)
            
        # dist_to_target: % from current_price up to target
        dist_to_target = 0.0
        if current_price > 0 and t.target is not None:
            dist_to_target = round(((t.target - current_price) / current_price) * 100, 2)
        
        trade_data = {
            "id": t.id,
            "symbol": t.symbol,
            "entry_date": t.entry_date,
            "entry_price": t.entry_price,
            "shares": t.shares,
            "position_value": t.position_value,
            "stop_loss": t.stop_loss,
            "target": t.target,
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "live_return_pct": live_return_pct,
            "dist_to_stop": dist_to_stop,
            "dist_to_target": dist_to_target,
            "notes": t.notes
        }
        results.append(trade_data)
        
    return results

@router.get("/closed")
def get_closed_trades(db: Session = Depends(get_db)):
    trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'closed').order_by(models.TradeJournal.exit_date.desc()).all()
    return trades

@router.patch("/{trade_id}/close")
def close_trade(trade_id: int, data: TradeCloseRequest, db: Session = Depends(get_db)):
    trade = db.query(models.TradeJournal).filter(models.TradeJournal.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    if trade.status == 'closed':
        raise HTTPException(status_code=400, detail="Trade already closed")
        
    trade.exit_price = data.exit_price
    trade.exit_date = data.exit_date
    trade.exit_reason = data.exit_reason
    trade.status = 'closed'
    
    # Calculations
    trade.pnl = (data.exit_price - trade.entry_price) * trade.shares
    
    trade.return_pct = 0.0
    if trade.entry_price > 0:
        trade.return_pct = round(((data.exit_price - trade.entry_price) / trade.entry_price) * 100, 2)
    
    if trade.entry_date:
        delta = data.exit_date - trade.entry_date
        trade.holding_days = delta.days
    
    db.commit()
    db.refresh(trade)
    return trade

@router.get("/stats")
def get_journal_stats(db: Session = Depends(get_db)):
    closed_trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'closed').all()
    open_trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'open').all()
    
    total_trades = len(closed_trades)
    winning_trades = len([t for t in closed_trades if (t.pnl or 0) > 0])
    total_pnl = sum([t.pnl or 0 for t in closed_trades])
    avg_return = round(sum([t.return_pct or 0 for t in closed_trades]) / total_trades, 2) if total_trades > 0 else 0
    
    # Calculate Unrealized PnL
    total_unrealized_pnl = 0.0
    if open_trades:
        symbols = list(set([t.symbol for t in open_trades]))
        snapshots = fetch_market_snapshots(symbols)
        price_map = {s['symbol']: s['close'] for s in snapshots}
        
        for t in open_trades:
            current_price = price_map.get(t.symbol) or t.entry_price
            total_unrealized_pnl += (current_price - t.entry_price) * t.shares
            
    return {
        "total_trades": total_trades,
        "win_rate": round((winning_trades / total_trades) * 100, 2) if total_trades > 0 else 0,
        "total_pnl": total_pnl,
        "avg_return": avg_return,
        "total_unrealized_pnl": total_unrealized_pnl,
        "open_positions": len(open_trades)
    }
