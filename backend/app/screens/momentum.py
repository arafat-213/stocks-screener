from sqlalchemy import and_, or_, func, case as sa_case
from sqlalchemy.orm import Session
from app.db.models import TechnicalSignal, FundamentalCache, Stock
from app.screens.base import get_latest_signal_date

def screen_momentum_monsters(db: Session, timeframe: str = 'D', target_date=None):
    """
    rs_score >= 80, momentum_3m >= 15, adx >= 25, above_200ema, RSI not overbought.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.rs_score).join(
        Stock, TechnicalSignal.symbol == Stock.symbol
    ).filter(
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

def screen_value_with_momentum(db: Session, timeframe: str = 'D', target_date=None):
    """
    PEG < 2.0, recent 1-month momentum >= 5%, rising EMA20, above 200 EMA.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        Stock, TechnicalSignal.symbol == Stock.symbol
    ).join(
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

def screen_ema_crossover_signals(db: Session, timeframe: str = 'D', target_date=None):
    """
    Fresh EMA5/13 bullish cross today with ADX >= 20 and above 200 EMA.
    These are the exact signals the backtest engine trades — useful as a daily watchlist.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        Stock, TechnicalSignal.symbol == Stock.symbol
    ).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.ema_signal == 'bullish_cross',
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.adx >= 20.0,
            TechnicalSignal.rsi >= 35,
            TechnicalSignal.rsi < 70,
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results

def screen_volume_surge(db: Session, timeframe: str = 'D', target_date=None):
    """
    Volume breakout (>2x 20-day average on a green day) with bullish EMA alignment.
    High-conviction entry signals — volume confirms institutional participation.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        Stock, TechnicalSignal.symbol == Stock.symbol
    ).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.volume_breakout == True,
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.is_bullish == True,
            TechnicalSignal.rsi >= 35,
            TechnicalSignal.rsi < 75,
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results

def screen_rsi_recovery(db: Session, timeframe: str = 'D', target_date=None):
    """
    RSI crossed above 40 (from below 35 recently implied by rsi_signal), price above EMA20, above 200 EMA.
    Early-stage recovery plays.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        Stock, TechnicalSignal.symbol == Stock.symbol
    ).filter(
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

def screen_actionable_entries(db: Session, timeframe: str = 'D', target_date=None):
    """
    Ready-to-trade EMA crossover signals that pass the same gates as the
    backtested strategy: cross above 200 EMA, RSI 35-65 (35 allows RSI recovery setups that the backtest also trades), positive 12m momentum,
    prior consolidation, AND (volume breakout OR ADX >= 25).

    These are the signals to act on the next trading day.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = (
        db.query(
            TechnicalSignal.symbol, 
            TechnicalSignal.entry_score,
            sa_case(
                (
                    (FundamentalCache.profitability_streak_passed == True) & 
                    (FundamentalCache.de_check_passed == True) & 
                    (FundamentalCache.fcf_positive == True), 
                    'A'
                ),
                (
                    (FundamentalCache.profitability_streak_passed == True) | 
                    (FundamentalCache.de_check_passed == True), 
                    'B'
                ),
                else_='C'
            ).label('quality_tier')
        )
        .join(Stock, TechnicalSignal.symbol == Stock.symbol)
        .outerjoin(FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol)
        .filter(
            and_(
                func.date(TechnicalSignal.date) == date,
                TechnicalSignal.timeframe == timeframe,
                TechnicalSignal.ema_signal == 'bullish_cross',
                TechnicalSignal.above_200ema == True,
                TechnicalSignal.rsi >= 35,
                TechnicalSignal.rsi <= 65,
                TechnicalSignal.momentum_12m > 0,
                TechnicalSignal.is_consolidating == True,
                or_(
                    TechnicalSignal.volume_breakout == True,
                    TechnicalSignal.adx >= 25,
                ),
            )
        )
        .order_by(TechnicalSignal.entry_score.desc())
        .all()
    )
    return [(r.symbol, r.entry_score, r.quality_tier) for r in results]
