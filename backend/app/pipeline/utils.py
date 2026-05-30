import datetime
import logging

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


FIELD_KEYWORDS = {
    "net_income": [
        "net income",
        "net earnings",
        "profit after tax",
        "pat",
        "net income from continuing operations",
    ],
    "revenue": ["total revenue", "revenue", "total operating revenue", "net sales"],
    "ebit": ["ebit", "operating income", "operating profit"],
    "total_assets": ["total assets"],
    "current_liab": ["current liabilities", "total current liabilities"],
    "op_cashflow": [
        "operating cash flow",
        "cash from operations",
        "net cash from operating",
    ],
    "capex": ["capital expenditure", "purchase of fixed assets", "capex"],
}


def to_float(val, default=None):
    """Safely converts a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def get_financial_row(df: pd.DataFrame, field_key: str) -> pd.Series | None:
    """
    Extracts a row from a yfinance financial DataFrame using ordered keyword matching.
    Looks up keywords for field_key, checks each keyword (case-insensitive) against index.
    Returns the first matching row as a Series, or None if no match.
    """
    if df is None or df.empty or field_key not in FIELD_KEYWORDS:
        return None

    keywords = FIELD_KEYWORDS[field_key]
    # Clean index labels: strip whitespace and lower case
    cleaned_index = [str(idx).strip().lower() for idx in df.index]

    for kw in keywords:
        kw_lower = kw.lower().strip()
        for i, idx_val in enumerate(cleaned_index):
            if kw_lower == idx_val or kw_lower in idx_val:
                logger.debug(
                    f"Matched financial row: '{df.index[i]}' for key '{field_key}' using keyword '{kw}'"
                )
                return df.iloc[i]

    logger.warning(
        f"Failed to find financial row for key '{field_key}'. Available index: {list(df.index)}"
    )
    return None


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
