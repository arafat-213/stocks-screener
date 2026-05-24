import os
import logging
import pandas as pd
from pathlib import Path
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import TechnicalSignal

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
CACHE_DIR = os.environ.get("CACHE_DIR", str(Path(__file__).resolve().parent / "data"))
OHLCV_DIR = Path(CACHE_DIR) / "ohlcv"

def backfill_resistance():
    """
    Iterates over all OHLCV parquet files, calculates historical resistance levels,
    and updates the technical_signals table.
    """
    if not OHLCV_DIR.exists():
        logger.error(f"OHLCV directory not found at {OHLCV_DIR}")
        return

    parquet_files = list(OHLCV_DIR.glob("*.parquet"))
    total_files = len(parquet_files)
    
    logger.info(f"Found {total_files} symbols. Starting resistance backfill...")
    
    db: Session = SessionLocal()
    
    try:
        for idx, file_path in enumerate(parquet_files, 1):
            symbol = file_path.stem.replace("_", "^") if "_" in file_path.stem and "NS" not in file_path.stem else file_path.stem.replace("_", "/")
            
            logger.info(f"[{idx}/{total_files}] Processing {symbol}...")
            
            try:
                df = pd.read_parquet(file_path)
                if len(df) < 260:
                    continue
                    
                # Ensure datetime index
                if hasattr(df.index, 'tzinfo') and df.index.tzinfo is not None:
                    df.index = df.index.tz_localize(None)
                
                # Resistance: Highest close in the year prior to the last 20 bars (240 bar window)
                # Rolling max with a shift to exclude the most recent 20 bars
                # window=240, shift=20
                df['res_rolling'] = df['Close'].shift(20).rolling(window=240).max()
                df['pct_res'] = (df['Close'] / df['res_rolling'] - 1) * 100
                
                # Drop NaNs
                valid_df = df[df['pct_res'].notna()]
                
                if valid_df.empty:
                    continue

                # Prepare updates
                updates = []
                for date, row in valid_df.iterrows():
                    # We need to find the ID of the signal record to update
                    # This is a bit slow but necessary since we don't have IDs in parquet
                    # Optimized: use dict for faster lookups if possible?
                    # Actually, bulk_update_mappings is better but we still need the ID.
                    pass
                
                # RE-THINK: It's better to fetch all signal IDs for this symbol from DB first
                signals_query = db.query(TechnicalSignal.id, TechnicalSignal.date).filter(
                    TechnicalSignal.symbol == symbol,
                    TechnicalSignal.timeframe == 'D'
                ).all()
                
                date_to_id = {s.date.date() if hasattr(s.date, 'date') else s.date: s.id for s in signals_query}
                
                updates = []
                for timestamp, row in valid_df.iterrows():
                    d = timestamp.date()
                    if d in date_to_id:
                        updates.append({
                            "id": date_to_id[d],
                            "pct_from_resistance": float(row['pct_res'])
                        })
                
                if updates:
                    # Split into chunks of 1000 for safety
                    for i in range(0, len(updates), 1000):
                        chunk = updates[i:i+1000]
                        db.bulk_update_mappings(TechnicalSignal, chunk)
                    db.commit()
                    logger.info(f"  -> Updated {len(updates)} records.")
                
            except Exception as e:
                db.rollback()
                logger.error(f"  -> Error processing {symbol}: {e}")

    finally:
        db.close()
        logger.info("Resistance backfill complete.")

if __name__ == "__main__":
    backfill_resistance()
