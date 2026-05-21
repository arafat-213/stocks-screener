from sqlalchemy.orm import Session
from sqlalchemy import and_, cast, Date, func, Float, Integer
from app.db.models import TechnicalSignal, Stock, SectorSnapshot
from app.screens.base import get_latest_signal_date
import datetime

def compute_sector_rotation(db: Session) -> list[dict]:
    """
    Computes sector-level aggregates from latest daily signals and persists them.
    Called from the pipeline after rs_ranks. Returns sorted sector data.
    """
    date = get_latest_signal_date(db, 'D')

    rows = (
        db.query(
            Stock.sector,
            func.avg(TechnicalSignal.rs_score).label("avg_rs"),
            func.avg(TechnicalSignal.momentum_3m).label("avg_momentum_3m"),
            func.avg(
                func.cast(func.cast(TechnicalSignal.is_bullish, Integer), Float)
            ).label("bullish_pct"),
            func.count(TechnicalSignal.symbol).label("stock_count"),
        )
        .join(Stock, TechnicalSignal.symbol == Stock.symbol)
        .filter(
            and_(
                func.date(TechnicalSignal.date) == date,
                TechnicalSignal.timeframe == 'D',
                TechnicalSignal.rs_score.isnot(None),
                Stock.sector.isnot(None),
            )
        )
        .group_by(Stock.sector)
        .having(func.count(TechnicalSignal.symbol) >= 3) # ignore micro-sectors
        .order_by(func.avg(TechnicalSignal.rs_score).desc())
        .all()
    )

    results = []
    for row in rows:
        snap = db.query(SectorSnapshot).filter_by(date=date, sector=row.sector).first()
        if not snap:
            snap = SectorSnapshot(date=date, sector=row.sector)
            db.add(snap)
        
        snap.avg_rs = float(row.avg_rs) if row.avg_rs else None
        snap.avg_momentum_3m = float(row.avg_momentum_3m) if row.avg_momentum_3m else None
        snap.bullish_pct = float(row.bullish_pct * 100) if row.bullish_pct else None
        snap.stock_count = int(row.stock_count)
        
        results.append({
            "sector": row.sector,
            "avg_rs": snap.avg_rs,
            "avg_momentum_3m": snap.avg_momentum_3m,
            "bullish_pct": snap.bullish_pct,
            "stock_count": snap.stock_count,
        })
    
    db.commit()
    return results

def screen_hot_sectors(db: Session, timeframe: str = 'D'):
    """
    Returns top stocks from the top 3 sectors by average RS score.
    Combines sector rotation signal with individual stock quality.
    """
    date = get_latest_signal_date(db, timeframe)
    snapshot_date = db.query(func.max(SectorSnapshot.date)).scalar()
    
    if not snapshot_date:
        return []

    top_sectors = (
        db.query(SectorSnapshot.sector)
        .filter(SectorSnapshot.date == snapshot_date)
        .order_by(SectorSnapshot.avg_rs.desc())
        .limit(3)
        .subquery()
    )

    results = (
        db.query(TechnicalSignal.symbol, TechnicalSignal.entry_score)
        .join(Stock, TechnicalSignal.symbol == Stock.symbol)
        .filter(
            and_(
                func.date(TechnicalSignal.date) == date,
                TechnicalSignal.timeframe == timeframe,
                TechnicalSignal.above_200ema == True,
                TechnicalSignal.is_bullish == True,
                TechnicalSignal.rs_score >= 60,
                Stock.sector.in_(top_sectors),
            )
        )
        .order_by(TechnicalSignal.rs_score.desc())
        .all()
    )
    return results
