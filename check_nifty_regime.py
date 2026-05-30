
import datetime
import logging
import sys
import os

# Add the backend directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.db.session import SessionLocal
from app.paper_trading.engine import _get_regime
from app.screens.base import get_latest_signal_date
from app.pipeline.ohlcv_cache import OHLCVCache

logging.basicConfig(level=logging.INFO)

def check_regime():
    db = SessionLocal()
    try:
        today = get_latest_signal_date(db)
        print(f"Latest Signal Date: {today}")

        regime = _get_regime(db, today)
        print(f"Regime Bullish: {regime}")

        # Check Nifty data
        cache = OHLCVCache()
        df = cache.get("^NSEI", append_ns=False)
        if df is not None and not df.empty:
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            import pandas_ta_classic
            df.ta.ema(length=50, append=True)
            df.ta.ema(length=200, append=True)
            last = df.iloc[-1]
            print(f"Nifty Close: {last['Close']}")
            print(f"EMA 50: {last.get('EMA_50')}")
            print(f"EMA 200: {last.get('EMA_200')}")

    finally:
        db.close()

if __name__ == "__main__":
    check_regime()
