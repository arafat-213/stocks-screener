from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from app.db.models import TechnicalSignal
import datetime

def get_latest_signal_date(db: Session, timeframe: str = 'D') -> datetime.date:
    """
    Returns the most recent *market date* (as datetime.date) for which we have signals for the given timeframe.
    """
    latest = db.query(
        func.max(TechnicalSignal.date)
    ).filter(
        TechnicalSignal.timeframe == timeframe
    ).scalar()

    if latest:
        if isinstance(latest, datetime.datetime):
            return latest.date()
        if isinstance(latest, datetime.date):
            return latest
        if isinstance(latest, str):
            # SQLite may return a string like '2023-10-27 00:00:00.000000'
            return datetime.date.fromisoformat(latest.split(' ')[0])

    return datetime.date.today()
