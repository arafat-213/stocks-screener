from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.db.models import TechnicalSignal, FundamentalCache
from app.screens.base import get_latest_signal_date

def screen_low_debt_midcap(db: Session, timeframe: str = 'D'):
    """
    True midcaps (5,000–20,000 Cr) with low debt, positive FCF, and sustained profitability.
    Above 200 EMA required for trend context.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol
    ).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.above_200ema == True,
            FundamentalCache.market_cap_category == 'midcap',
            FundamentalCache.de_check_passed == True,
            FundamentalCache.fcf_positive == True,
            FundamentalCache.profitability_streak_passed == True,
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    return results

def screen_undervalued_fundamentals(db: Session, timeframe: str = 'D'):
    """
    Low PEG (<1.5), high ROE (>15%), dividend yield, EV/EBITDA < 20.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol
    ).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.above_200ema == True,
            FundamentalCache.peg_ratio > 0,
            FundamentalCache.peg_ratio <= 1.5,
            FundamentalCache.roe >= 0.15,
            FundamentalCache.ev_to_ebitda < 20,
            FundamentalCache.dividend_yield > 0,
            FundamentalCache.de_check_passed == True
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results

def screen_steady_compounders(db: Session, timeframe: str = 'D'):
    """
    High ROCE (>15%) with consistent dividend history above 200 EMA.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol
    ).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.above_200ema == True,
            FundamentalCache.roce >= 0.15,
            FundamentalCache.dividend_consistency == True,
            FundamentalCache.profitability_streak_passed == True
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results
