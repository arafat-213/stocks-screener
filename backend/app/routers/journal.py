from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db import models
from pydantic import BaseModel
from typing import List, Optional
import datetime

router = APIRouter(prefix="/journal", tags=["journal"])

class TradeEntryCreate(BaseModel):
    symbol: str
    entry_price: float
    shares: int
    stop_loss: float
    target: float
    signal_date: Optional[datetime.date] = None
    entry_date: Optional[datetime.date] = datetime.date.today()
    watchlist_id: Optional[int] = None
    notes: Optional[str] = None

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
