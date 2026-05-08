from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models import TechnicalSignal
import datetime

def get_latest_signal_date(db: Session, timeframe: str = 'D') -> datetime.date:
    """Returns the most recent date for which we have signals for the given timeframe."""
    latest = db.query(func.max(TechnicalSignal.date)).filter(
        TechnicalSignal.timeframe == timeframe
    ).scalar()
    return latest.date() if latest else datetime.date.today()
