import datetime
import logging
import math

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import TechnicalSignal

logger = logging.getLogger(__name__)


def get_market_regime(db: Session, date: datetime.date) -> bool:
    """
    Queries regime from Nifty TechnicalSignal state.
    Falls back to True (don't suppress alerts) if not available.
    """
    signal = (
        db.query(TechnicalSignal)
        .filter(
            TechnicalSignal.symbol == "^NSEI",
            TechnicalSignal.timeframe == "D",
            func.date(TechnicalSignal.date) <= date,
        )
        .order_by(TechnicalSignal.date.desc())
        .first()
    )

    if not signal:
        return True

    return bool(signal.is_bullish)


def to_float(val, default=None):
    """Safely converts a value to float, returning default for NaN/Inf."""
    if val is None:
        return default
    try:
        f_val = float(val)
        if not math.isfinite(f_val):
            return default
        return f_val
    except (ValueError, TypeError):
        return default


def to_int(val, default=None):
    """Safely converts a value to int."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def to_bool(val, default=False):
    """Safely converts a value to bool."""
    if val is None:
        return default
    try:
        return bool(val)
    except (ValueError, TypeError):
        return default


def resample_ohlcv(
    df: pd.DataFrame, freq: str, drop_incomplete: bool = True
) -> pd.DataFrame:
    """
    Resamples OHLCV data to a different frequency.
    Volume is summed, Open is first, High is max, Low is min, Close is last.
    """
    if df.empty:
        return df

    ohlcv_agg = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }

    # Ensure columns exist before aggregating to avoid errors
    cols_to_agg = {k: v for k, v in ohlcv_agg.items() if k in df.columns}

    resampled = df.resample(freq).agg(cols_to_agg).dropna()

    if drop_incomplete and len(resampled) > 0:
        return resampled.iloc[:-1]

    return resampled
