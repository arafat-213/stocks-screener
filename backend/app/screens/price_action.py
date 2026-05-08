from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.db.models import TechnicalSignal, Stock
from app.screens.base import get_latest_signal_date

def screen_52w_high(db: Session, timeframe: str = 'D'):
    """
    pct_from_52w_high between -5% and 0%, sort by closeness to high.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal).filter(
        and_(
            TechnicalSignal.date == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.pct_from_52w_high >= -5.0,
            TechnicalSignal.pct_from_52w_high <= 0.0
        )
    ).order_by(TechnicalSignal.pct_from_52w_high.desc()).all()
    
    return [(r.symbol, r.pct_from_52w_high) for r in results]

def screen_52w_low(db: Session, timeframe: str = 'D'):
    """
    pct_from_52w_low between 0% and 10%, sort by closeness to low.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal).filter(
        and_(
            TechnicalSignal.date == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.pct_from_52w_low >= 0.0,
            TechnicalSignal.pct_from_52w_low <= 10.0
        )
    ).order_by(TechnicalSignal.pct_from_52w_low.asc()).all()
    
    return [(r.symbol, r.pct_from_52w_low) for r in results]

def screen_near_breakout(db: Session, timeframe: str = 'D'):
    """
    pct_from_resistance between -3% and 0%, volume breakout OR ema slope > 0.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal).filter(
        and_(
            TechnicalSignal.date == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.pct_from_resistance >= -3.0,
            TechnicalSignal.pct_from_resistance <= 0.0,
            or_(
                TechnicalSignal.volume_breakout == True,
                TechnicalSignal.ema_slope_20 > 0.0
            )
        )
    ).order_by(TechnicalSignal.pct_from_resistance.desc()).all()
    
    return [(r.symbol, r.pct_from_resistance) for r in results]
