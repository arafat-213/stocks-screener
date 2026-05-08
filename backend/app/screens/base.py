from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models import TechnicalSignal
import datetime

def get_latest_signal_date(db: Session, timeframe: str = 'D'):
    """Returns the most recent date (as datetime) for which we have signals for the given timeframe."""
    latest = db.query(func.max(TechnicalSignal.date)).filter(
        TechnicalSignal.timeframe == timeframe
    ).scalar()
    if latest:
        return latest
    # Fallback to today midnight
    return datetime.datetime.combine(datetime.date.today(), datetime.time.min)
