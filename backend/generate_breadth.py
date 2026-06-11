import logging

import pandas as pd
import pandas_ta_classic  # noqa
from sqlalchemy.orm import Session

from app.db.models import MarketBreadth, Stock
from app.db.session import SessionLocal
from app.pipeline.ohlcv_cache import OHLCVCache

# Setup basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_ohlcv_cache = OHLCVCache()


def generate_market_breadth(lookback_days: int = 2500):
    """
    Calculates market breadth (Nifty 500 proxy) based on the top 500 stocks by market cap.
    Stores daily % of stocks above their 200 EMA in the market_breadth table.
    """
    db: Session = SessionLocal()
    try:
        # 1. Identify "Nifty 500" proxy: Top 500 stocks by Market Cap
        logger.info("Identifying top 500 stocks by market cap...")
        top_stocks = (
            db.query(Stock.symbol)
            .filter(Stock.market_cap.isnot(None))
            .order_by(Stock.market_cap.desc())
            .limit(500)
            .all()
        )
        symbols = [s[0] for s in top_stocks]

        if not symbols:
            logger.error("No stocks found in database to calculate breadth.")
            return

        logger.info(f"Using {len(symbols)} stocks for breadth calculation.")

        # 2. Load all OHLCV data into a massive matrix for vectorized calculation
        all_data = {}

        processed_count = 0
        for sym in symbols:
            df = _ohlcv_cache.get(sym, period="10y")
            if df is not None and not df.empty:
                # Ensure naive index
                if df.index.tz is not None:
                    df.index = df.index.tz_convert(None)

                # Calculate 200 EMA
                df.ta.ema(length=200, append=True)
                if "EMA_200" in df.columns:
                    # Keep only Close and EMA_200 to save memory
                    all_data[sym] = df[["Close", "EMA_200"]]
                    processed_count += 1

            if (len(all_data) % 50) == 0 and len(all_data) > 0:
                logger.info(f"Loaded {len(all_data)} stocks...")

        if not all_data:
            logger.error("Failed to load any stock data for breadth.")
            return

        logger.info(
            f"Data loaded for {len(all_data)} stocks. Calculating daily breadth..."
        )

        # 3. Create a combined DataFrame of (Close > EMA200) booleans
        # This is a memory-intensive operation but fast.
        bool_map = {}
        for sym, df in all_data.items():
            bool_map[sym] = (df["Close"] > df["EMA_200"]).astype(float)

        combined_bools = pd.DataFrame(bool_map)

        # Calculate row-wise mean (percentage of stocks above 200 EMA)
        # count() ignores NaNs, so we only average stocks that had data that day
        breadth_series = (
            combined_bools.sum(axis=1) / combined_bools.count(axis=1)
        ) * 100
        count_series = combined_bools.count(axis=1)

        # Ensure unique dates (in case of index artifacts)
        breadth_series.index = [
            d.date() if hasattr(d, "date") else d for d in breadth_series.index
        ]
        count_series.index = [
            d.date() if hasattr(d, "date") else d for d in count_series.index
        ]

        breadth_series = breadth_series.groupby(breadth_series.index).mean()
        count_series = count_series.groupby(count_series.index).max()

        # 4. Save to Database
        logger.info(
            f"Calculation complete. Saving {len(breadth_series)} days of breadth data..."
        )

        # Clear existing data to avoid conflicts on re-run
        db.query(MarketBreadth).delete()

        breadth_records = []
        for dt, val in breadth_series.items():
            if pd.isna(val):
                continue

            date_only = dt.date() if hasattr(dt, "date") else dt
            breadth_records.append(
                {
                    "date": date_only,
                    "breadth_pct": float(val),
                    "stock_count": int(count_series.loc[dt]),
                }
            )

        # Bulk insert
        db.bulk_insert_mappings(MarketBreadth, breadth_records)
        db.commit()
        logger.info("Successfully updated market_breadth table.")

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to generate market breadth: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    generate_market_breadth()
