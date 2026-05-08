import yfinance as yf
from nsepython import nse_eq_symbols
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def get_nse_symbols(limit: int = None) -> list[str]:
    try:
        symbols = nse_eq_symbols()
        if not symbols:
            raise ValueError("Empty list returned from nsepython")
        
        if limit:
            symbols = symbols[:limit]
            
        logger.info(f"Successfully fetched {len(symbols)} symbols from NSE")
        return symbols
    except Exception as e:
        logger.error(f"Failed to fetch NSE universe: {e}")
        return ["RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR"]

def fetch_stock_data(symbol: str, append_ns: bool = True, period: str = "1y"):
    try:
        ticker_symbol = f"{symbol}.NS" if append_ns else symbol
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period=period)
        info = ticker.info
        
        if hist.empty:
            return None, None
            
        return hist, info
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None, None
