from sqlalchemy.orm import Session, aliased
from sqlalchemy import and_, cast, Date, func
from app.db.models import TechnicalSignal, Stock
from app.screens.base import get_latest_signal_date

def screen_mtf_confluence(db: Session, timeframe: str = 'D', target_date=None):
    """
    All three timeframes (Daily, Weekly, Monthly) simultaneously bullish.
    This is the strongest signal in the system — rare but high conviction.
    Weekly and Monthly bullish mean RSI>50 + price>EMA26 on those timeframes.
    
    Fix: Instead of joining on exact date (which fails because W/M signals 
    are on Sundays/Month-ends), we join on the most recent signal for each symbol.
    """
    date_d = target_date if target_date else get_latest_signal_date(db, 'D')

    # Subqueries to find the latest signal <= date_d for each timeframe
    latest_weekly_date = (
        db.query(func.max(TechnicalSignal.date))
        .filter(TechnicalSignal.timeframe == 'W', TechnicalSignal.date <= date_d)
        .scalar_subquery()
    )
    latest_monthly_date = (
        db.query(func.max(TechnicalSignal.date))
        .filter(TechnicalSignal.timeframe == 'M', TechnicalSignal.date <= date_d)
        .scalar_subquery()
    )

    daily = aliased(TechnicalSignal)
    weekly = aliased(TechnicalSignal)
    monthly = aliased(TechnicalSignal)

    results = (
        db.query(daily.symbol, daily.entry_score)
        .join(Stock, daily.symbol == Stock.symbol)
        .join(
            weekly,
            and_(
                daily.symbol == weekly.symbol,
                weekly.date == latest_weekly_date,
                weekly.timeframe == 'W',
                weekly.is_bullish == True,
            ),
        )
        .join(
            monthly,
            and_(
                daily.symbol == monthly.symbol,
                monthly.date == latest_monthly_date,
                monthly.timeframe == 'M',
                monthly.is_bullish == True,
            ),
        )
        .filter(
            and_(
                func.date(daily.date) == date_d,
                daily.timeframe == 'D',
                daily.is_bullish == True,
                daily.above_200ema == True,
                daily.rsi >= 40,
                daily.rsi < 75,
            )
        )
        .order_by(daily.entry_score.desc())
        .all()
    )
    return results

def screen_sector_leaders(db: Session, timeframe: str = 'D', target_date=None):
    """
    Top 3 stocks by RS score within each sector.
    Useful for sector rotation — buy the leaders when rotating into a sector.
    Requires at least one sector assigned to the stock.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)

    ranked = (
        db.query(
            TechnicalSignal.symbol,
            TechnicalSignal.rs_score,
            TechnicalSignal.entry_score,
            Stock.sector,
            func.rank()
            .over(
                partition_by=Stock.sector,
                order_by=TechnicalSignal.rs_score.desc(),
            )
            .label("sector_rank"),
        )
        .join(Stock, TechnicalSignal.symbol == Stock.symbol)
        .filter(
            and_(
                func.date(TechnicalSignal.date) == date,
                TechnicalSignal.timeframe == timeframe,
                TechnicalSignal.above_200ema == True,
                TechnicalSignal.is_bullish == True,
                TechnicalSignal.rs_score.isnot(None),
                Stock.sector.isnot(None),
            )
        )
        .subquery()
    )

    results = (
        db.query(ranked.c.symbol, ranked.c.rs_score)
        .filter(ranked.c.sector_rank <= 3)
        .order_by(ranked.c.sector.asc(), ranked.c.rs_score.desc())
        .all()
    )
    return results

def screen_fresh_52w_breakout(db: Session, timeframe: str = 'D', target_date=None):
    """
    Price just broke above 52-week high (within +3%) with volume confirmation.
    This is a pure price-action momentum entry — stock is in price discovery.
    Not a value play; only for momentum traders comfortable with no overhead resistance.
    """
    date = target_date if target_date else get_latest_signal_date(db, timeframe)

    results = (
        db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score)
        .join(Stock, TechnicalSignal.symbol == Stock.symbol)
        .filter(
            and_(
                func.date(TechnicalSignal.date) == date,
                TechnicalSignal.timeframe == timeframe,
                TechnicalSignal.pct_from_52w_high >= -1.0,  # within 1% below or above
                TechnicalSignal.pct_from_52w_high <= 3.0,   # not too extended past breakout
                TechnicalSignal.volume_breakout == True,
                TechnicalSignal.above_200ema == True,
                TechnicalSignal.rsi >= 50,
                TechnicalSignal.rsi < 80,
                TechnicalSignal.adx >= 20,
            )
        )
        .order_by(TechnicalSignal.entry_score.desc())
        .all()
    )
    return results
