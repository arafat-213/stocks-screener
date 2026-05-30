import logging
import random
import time

import pandas as pd
from sqlalchemy.orm import Session

from app.db.models import Stock
from app.db.session import SessionLocal
from app.pipeline.ohlcv_cache import OHLCVCache

# Setup basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def has_5y_data(path):
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return False

        first_date = df.index[0]
        if hasattr(first_date, "tzinfo") and first_date.tzinfo is not None:
            first_date = first_date.tz_localize(None)

        last_date = df.index[-1]
        if hasattr(last_date, "tzinfo") and last_date.tzinfo is not None:
            last_date = last_date.tz_localize(None)

        # Check if the date span is roughly 5 years (allowing some margin for weekends/holidays, > 4.5 years = 1640 days)
        days_span = (last_date - first_date).days
        return days_span >= 1640
    except Exception as e:
        logger.warning(f"Error checking {path}: {e}")
        return False


def warm_cache():
    """
    Iterates through all stocks in the database and fetches 5-year OHLCV data
    to populate the local Parquet cache. Includes rate-limiting to avoid yfinance bans.
    """
    db: Session = SessionLocal()
    cache = OHLCVCache()

    try:
        stocks = db.query(Stock).all()
        logger.info(f"Found {len(stocks)} stocks to check.")

        success_count = 0
        fail_count = 0
        skip_count = 0

        for i, stock in enumerate(stocks):
            symbol = stock.symbol
            # Check if we already have sufficient data
            path = cache._get_path(symbol)
            if cache.exists(symbol) and has_5y_data(path):
                skip_count += 1
                continue

            logger.info(
                f"[{i + 1}/{len(stocks)}] Fetching 5y data for {symbol} (Reason: Missing or incomplete)"
            )
            try:
                # Fetching 5y ensures we have enough for 200 EMA + 52w highs
                df = cache.fetch_and_save(symbol, period="5y")
                if not df.empty:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
                fail_count += 1

            # Dynamic sleep to respect yfinance/Yahoo Finance limits
            # For ~1700 missing symbols, this adds ~42 minutes of pure sleep time,
            # bringing total execution to roughly 1-1.5 hours.
            sleep_time = random.uniform(1.0, 2.0)

            # Add a longer pause every 100 requests
            if i % 100 == 0:
                logger.info("Taking a brief pause to respect rate limits (30s)...")
                sleep_time = 30.0

            time.sleep(sleep_time)

    finally:
        db.close()
        logger.info("Cache warming complete.")
        logger.info(
            f"Success: {success_count}, Failed: {fail_count}, Skipped: {skip_count}"
        )
        stats = cache.stats()
        logger.info(f"Cache Stats: {stats}")


if __name__ == "__main__":
    warm_cache()
