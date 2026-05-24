from sqlalchemy.orm import Session
from sqlalchemy import and_, func, cast, Date
from app.db.models import TechnicalSignal, FundamentalCache, Stock
from app.screens.base import get_latest_signal_date

def screen_low_debt_midcap(db: Session, timeframe: str = 'D', target_date=None):
    """
    True midcaps (5,000–20,000 Cr) with low debt, positive FCF, and sustained profitability.
    Above 200 EMA required for trend context.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol
    ).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.is_bullish == True,
            TechnicalSignal.rsi >= 40,
            TechnicalSignal.rsi < 75,
            TechnicalSignal.ema_slope_20 > 0,
            FundamentalCache.market_cap_category == 'midcap',
            FundamentalCache.de_check_passed == True,
            FundamentalCache.fcf_positive == True,
            FundamentalCache.profitability_streak_passed == True,
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    return results

def screen_undervalued_fundamentals(db: Session, timeframe: str = 'D', target_date=None):
    """
    Low PEG (<1.5), high ROE (>15%), dividend yield, EV/EBITDA < 20.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol
    ).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.is_bullish == True,
            TechnicalSignal.rsi >= 40,
            TechnicalSignal.rsi < 75,
            TechnicalSignal.ema_slope_20 > 0,
            FundamentalCache.peg_ratio > 0,
            FundamentalCache.peg_ratio <= 1.5,
            FundamentalCache.roe >= 0.15,
            FundamentalCache.ev_to_ebitda < 20,
            FundamentalCache.dividend_yield > 0,
            FundamentalCache.de_check_passed == True
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results

def screen_steady_compounders(db: Session, timeframe: str = 'D', target_date=None):
    """
    High ROCE (>15%) with consistent dividend history above 200 EMA.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score).join(
        FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol
    ).filter(
        and_(
            func.date(TechnicalSignal.date) == date,
            TechnicalSignal.timeframe == timeframe,
            TechnicalSignal.above_200ema == True,
            TechnicalSignal.is_bullish == True,
            TechnicalSignal.rsi >= 40,
            TechnicalSignal.rsi < 75,
            TechnicalSignal.ema_slope_20 > 0,
            FundamentalCache.roce >= 0.15,
            FundamentalCache.dividend_consistency == True,
            FundamentalCache.profitability_streak_passed == True
        )
    ).order_by(TechnicalSignal.entry_score.desc()).all()
    
    return results

def screen_qarp(db: Session, timeframe: str = 'D', target_date=None):
    """
    Quality at Reasonable Price: high ROCE + ROE, PE < 35, low debt, profitability streak.
    The 'ideal compounder' filter.
    This is the closest equivalent to Screener.com's custom formula screens used by most serious retail investors.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = (
        db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score)
        .join(FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol)
        .join(Stock, TechnicalSignal.symbol == Stock.symbol)
        .filter(
            and_(
                func.date(TechnicalSignal.date) == date,
                TechnicalSignal.timeframe == timeframe,
                TechnicalSignal.above_200ema == True,
                TechnicalSignal.is_bullish == True,
                TechnicalSignal.rsi >= 40,
                TechnicalSignal.rsi < 75,
                TechnicalSignal.ema_slope_20 > 0,
                # Quality bar
                FundamentalCache.roce >= 0.15,
                FundamentalCache.roe >= 0.15,
                FundamentalCache.profitability_streak_passed == True,
                FundamentalCache.de_check_passed == True,
                FundamentalCache.fcf_positive == True,
                # Reasonable price (PEG or PEG-like constraint)
                FundamentalCache.peg_ratio > 0,
                FundamentalCache.peg_ratio <= 2.5,
            )
        )
        .order_by(TechnicalSignal.entry_score.desc())
        .all()
    )
    return results

def screen_dividend_growth(db: Session, timeframe: str = 'D', target_date=None):
    """
    Dividend yield > 1.5%, consistent dividend history, positive FCF, and above 200 EMA.
    Income + capital appreciation combination.
    Closest to Tickertape's 'Dividend Aristocrats' filter.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)
    results = (
        db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score)
        .join(FundamentalCache, TechnicalSignal.symbol == FundamentalCache.symbol)
        .filter(
            and_(
                func.date(TechnicalSignal.date) == date,
                TechnicalSignal.timeframe == timeframe,
                TechnicalSignal.above_200ema == True,
                TechnicalSignal.is_bullish == True,
                TechnicalSignal.ema_slope_20 > 0,
                TechnicalSignal.rsi >= 40,
                FundamentalCache.dividend_yield >= 0.015,  # 1.5%
                FundamentalCache.dividend_consistency == True,
                FundamentalCache.fcf_positive == True,
                FundamentalCache.profitability_streak_passed == True,
                FundamentalCache.de_check_passed == True,
                TechnicalSignal.rsi < 75,
            )
        )
        .order_by(FundamentalCache.dividend_yield.desc())
        .all()
    )
    return results
