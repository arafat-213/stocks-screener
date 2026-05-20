from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from app.db.models import TechnicalSignal, Stock
from app.screens.base import get_latest_signal_date

def screen_52w_high(db: Session, timeframe: str = 'D'):
    """
    Within 5% of 52-week high, above 200 EMA, and still bullish.
    Avoids stocks in distribution that happen to be near old highs.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.pct_from_52w_high >= -5.0,
            TechnicalSignal.pct_from_52w_high <= 0.0,
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.is_bullish == True,
            TechnicalSignal.rsi < 78, # exclude overbought
        )
    ).order_by(TechnicalSignal.pct_from_52w_high.desc()).all()
    
    return [(r.symbol, r.pct_from_52w_high) for r in results]

def screen_52w_low(db: Session, timeframe: str = 'D'):
    """
    Stocks within 15% of 52-week low but showing early recovery:
    RSI has bounced from oversold (<35) and price is above EMA20.
    Useful as a watchlist for potential reversals, not direct entry signals.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.pct_from_52w_low >= 0.0,
            TechnicalSignal.pct_from_52w_low <= 15.0,
            TechnicalSignal.rsi >= 35, # bounced off oversold territory
            TechnicalSignal.rsi <= 55, # not yet overbought — early recovery
            TechnicalSignal.ema_slope_20 > 0, # EMA20 turning up
        )
    ).order_by(TechnicalSignal.rsi.asc()).all()
    
    return [(r.symbol, r.pct_from_52w_low) for r in results]

def screen_near_breakout(db: Session, timeframe: str = 'D'):
    """
    Within 3% below key resistance with volume breakout OR rising EMA slope.
    Requires bullish daily signal to avoid false breakout setups.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.pct_from_resistance >= -3.0,
            TechnicalSignal.pct_from_resistance <= 0.5, # slight leeway past resistance
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.is_bullish == True,
            TechnicalSignal.rsi < 75,
            or_(
                TechnicalSignal.volume_breakout == True,
                TechnicalSignal.ema_slope_20 > 0.0
            )
        )
    ).order_by(TechnicalSignal.pct_from_resistance.desc()).all()
    
    return [(r.symbol, r.pct_from_resistance) for r in results]
