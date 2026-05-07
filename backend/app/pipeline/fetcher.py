import yfinance as yf
from nsepython import nse_eq_symbols
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def get_nse_symbols() -> list[str]:
    try:
        symbols = nse_eq_symbols()
        if not symbols:
            raise ValueError("Empty list returned from nsepython")
        logger.info(f"Successfully fetched {len(symbols)} symbols from NSE")
        return symbols
    except Exception as e:
        logger.error(f"Failed to fetch NSE universe: {e}")
        return ["RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR"]

def fetch_stock_data(symbol: str, period: str = "1y"):
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period=period)
        info = ticker.info
        
        if hist.empty:
            return None, None
            
        return hist, info
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None, None
