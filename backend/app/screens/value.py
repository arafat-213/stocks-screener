from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.db.models import TechnicalSignal, FundamentalCache, Stock
from app.screens.base import get_latest_signal_date

def screen_low_debt_midcap(db: Session, timeframe: str = 'D'):
    """
    market cap < 20,000 Cr, de_check_passed, fcf_positive, profitability_streak_passed.
    """
    results = db.query(FundamentalCache.symbol).filter(
        and_(
            FundamentalCache.de_check_passed == True,
            FundamentalCache.fcf_positive == True,
            FundamentalCache.profitability_streak_passed == True
        )
    ).join(Stock, Stock.symbol == FundamentalCache.symbol).filter(
        Stock.market_cap < 20000 * 1e7 # 20,000 Cr (assuming market_cap is in absolute units, yfinance usually gives absolute)
        # Note: 20,000 Cr = 200,000,000,000. 1 Cr = 10^7.
    ).all()
    
    # We return them with a dummy score if not applicable, or join with TechnicalSignal to get entry_score
    date = get_latest_signal_date(db, timeframe)
    final_results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).filter(
        and_(
            TechnicalSignal.date == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.symbol.in_([r.symbol for r in results])
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()

    return final_results

def screen_undervalued_fundamentals(db: Session, timeframe: str = 'D'):
    """
    peg_ratio between 0 and 1.5, roe >= 0.15, dividend_yield > 0, ev_to_ebitda < 20, above_200ema, de_check_passed.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol
    ).filter(
        and_(
            TechnicalSignal.date == date,
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
    roce >= 0.15, dividend_consistency, above_200ema, profitability_streak_passed.
    """
    date = get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol
    ).filter(
        and_(
            TechnicalSignal.date == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.above_200ema == True,
            FundamentalCache.roce >= 0.15,
            FundamentalCache.dividend_consistency == True,
            FundamentalCache.profitability_streak_passed == True
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results
