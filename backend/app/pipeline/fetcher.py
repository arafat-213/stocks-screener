import os
import yfinance as yf
from nsepython import nse_eq_symbols
import pandas as pd
import logging
import requests_cache
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

urls_expire_after = {
    '*/v8/finance/chart/^NSEI*': 60,
    '*/v8/finance/chart/^BSESN*': 60,
    '*': 86400,
}

cache_dir = os.environ.get("CACHE_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data"))
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
cache_file = os.path.join(cache_dir, 'yfinance_cache')

session = requests_cache.CachedSession(
    cache_file,
    urls_expire_after=urls_expire_after,
    backend='sqlite'
)

retry_strategy = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"],
    respect_retry_after_header=True
)
# ⚠️ Note: respect_retry_after_header=True means a Yahoo Finance
# Retry-After header can block this thread for an arbitrary duration.
# If pipeline hangs are observed, set this to False and rely solely
# on backoff_factor for wait timing.
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

# Keep the original get_nse_symbols unchanged
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

def fetch_stock_data(symbol: str, append_ns: bool = True, period: str = "1y", fetch_info: bool = True):
    try:
        ticker_symbol = f"{symbol}.NS" if append_ns else symbol
        # Inject our custom session
        ticker = yf.Ticker(ticker_symbol, session=session)
        hist = ticker.history(period=period)
        
        info = None
        if fetch_info:
            info = ticker.info
        
        if hist.empty:
            return None, None
            
        return hist, info
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None, None

def fetch_market_snapshots(symbols: list[str] = ["^NSEI", "^BSESN"], period: str = "5d") -> list[dict]:
    """
    Dedicated function to fetch market snapshots efficiently using yf.download.
    """
    try:
        # yf.download is much faster and less prone to rate limits for pure price data
        # Inject our custom session here as well
        data = yf.download(symbols, period=period, progress=False, session=session)
        
        if data.empty:
            return []
            
        snapshots = []
        for symbol in symbols:
            try:
                # When downloading multiple tickers, yf returns a MultiIndex column DataFrame
                # If only one ticker is requested, it's a single index DataFrame
                if len(symbols) > 1:
                    close_series = data['Close'][symbol].dropna()
                else:
                    close_series = data['Close'].dropna()
                    
                if len(close_series) >= 2:
                    current_close = float(close_series.iloc[-1])
                    prev_close = float(close_series.iloc[-2])
                    change_pct = ((current_close - prev_close) / prev_close) * 100
                    
                    snapshots.append({
                        "symbol": symbol,
                        "close": current_close,
                        "change_pct": change_pct
                    })
            except KeyError:
                logger.warning(f"Could not extract data for {symbol} from bulk download.")
                continue
                
        return snapshots
    except Exception as e:
        logger.error(f"Error bulk fetching market snapshots: {e}")
        return []
