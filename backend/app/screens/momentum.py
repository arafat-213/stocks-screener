from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.db.models import TechnicalSignal, FundamentalCache
from app.screens.base import get_latest_signal_date

def screen_momentum_monsters(db: Session, timeframe: str = 'D'):
    """
    rs_score >= 80, momentum_3m >= 15, adx >= 25, above_200ema.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.rs_score).filter(
        and_(
            TechnicalSignal.date == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.rs_score >= 80.0,
            TechnicalSignal.momentum_3m >= 15.0,
            TechnicalSignal.adx >= 25.0,
            TechnicalSignal.above_200ema == True
        )
    ).order_by(TechnicalSignal.rs_score.desc()).all()
    
    return results

def screen_value_with_momentum(db: Session, timeframe: str = 'D'):
    """
    peg_ratio < 2.0, momentum_1m >= 5, ema_slope_20 > 0.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol
    ).filter(
        and_(
            TechnicalSignal.date == date,
            TechnicalSignal.timeframe == timeframe,
            FundamentalCache.peg_ratio < 2.0,
            TechnicalSignal.momentum_1m >= 5.0,
            TechnicalSignal.ema_slope_20 > 0.0
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results
