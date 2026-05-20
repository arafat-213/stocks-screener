from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.db.models import TechnicalSignal, FundamentalCache
from app.screens.base import get_latest_signal_date

def screen_momentum_monsters(db: Session, timeframe: str = 'D'):
    """
    rs_score >= 80, momentum_3m >= 15, adx >= 25, above_200ema, RSI not overbought.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.rs_score).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.rs_score >= 80.0,
            TechnicalSignal.momentum_3m >= 15.0,
            TechnicalSignal.adx >= 25.0,
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.rsi < 78,
        )
    ).order_by(TechnicalSignal.rs_score.desc()).all()
    
    return results

def screen_value_with_momentum(db: Session, timeframe: str = 'D'):
    """
    PEG < 2.0, recent 1-month momentum >= 5%, rising EMA20, above 200 EMA.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol
    ).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.rsi < 75,
            FundamentalCache.peg_ratio > 0,
            FundamentalCache.peg_ratio < 2.0,
            TechnicalSignal.momentum_1m >= 5.0,
            TechnicalSignal.ema_slope_20 > 0.0,
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results

def screen_ema_crossover_signals(db: Session, timeframe: str = 'D'):
    """
    Fresh EMA5/13 bullish cross today with ADX >= 20 and above 200 EMA.
    These are the exact signals the backtest engine trades — useful as a daily watchlist.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.ema_signal == 'bullish_cross',
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.adx >= 20.0,
            TechnicalSignal.rsi >= 40,
            TechnicalSignal.rsi < 70,
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results

def screen_volume_surge(db: Session, timeframe: str = 'D'):
    """
    Volume breakout (>2x 20-day average on a green day) with bullish EMA alignment.
    High-conviction entry signals — volume confirms institutional participation.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.volume_breakout == True,
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.is_bullish == True,
            TechnicalSignal.rsi >= 40,
            TechnicalSignal.rsi < 75,
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results

def screen_rsi_recovery(db: Session, timeframe: str = 'D'):
    """
    RSI crossed above 40 (from below 35 recently implied by rsi_signal), price above EMA20, above 200 EMA.
    Early-stage recovery plays.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.rsi_signal.in_(['bullish_recovery', 'bullish_recovery_confirmed']),
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.rsi >= 35,
            TechnicalSignal.rsi <= 60, # hasn't run away yet
            TechnicalSignal.ema_slope_20 > 0,
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results
