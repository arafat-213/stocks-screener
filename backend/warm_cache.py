import pandas as pd


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


import logging
import random
import time

from sqlalchemy.orm import Session

from app.db.models import Stock
from app.db.session import SessionLocal
from app.pipeline.ohlcv_cache import OHLCVCache

# Setup basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def warm_cache():
    """
    Iterates through all stocks in the database and fetches 5-year OHLCV data
    to populate the local Parquet cache. Includes rate-limiting to avoid yfinance bans.
    """
    db: Session = SessionLocal()
    cache = OHLCVCache()

    try:
        # Get all symbols
        stocks = db.query(Stock.symbol).all()
        symbols = [s[0] for s in stocks]
        total_symbols = len(symbols)

        logger.info(f"Starting cache warming for {total_symbols} symbols.")

        success_count = 0
        fail_count = 0
        skip_count = 0

        for i, symbol in enumerate(symbols, 1):
            path = cache._file_path(symbol)
            if path.exists():
                if has_5y_data(path):
                    logger.info(
                        f"[{i}/{total_symbols}] Skipping {symbol} (already has 5y data)"
                    )
                    skip_count += 1
                    continue
                else:
                    logger.info(
                        f"[{i}/{total_symbols}] Data for {symbol} is less than 5y, forcing refresh..."
                    )
                    path.unlink(missing_ok=True)

            logger.info(f"[{i}/{total_symbols}] Fetching 5y data for {symbol}...")

            try:
                # Force 5y period
                df = cache.get(symbol, period="5y")

                if df is not None and not df.empty:
                    success_count += 1
                else:
                    logger.warning(f"No data returned for {symbol}")
                    fail_count += 1

            except Exception as e:
                logger.error(f"Error fetching {symbol}: {e}")
                fail_count += 1

            # Rate limiting logic
            # Average delay ~1.5 seconds per symbol
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
