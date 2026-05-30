import logging
import os

import pandas as pd
import requests_cache
import yfinance as yf
from nsepython import nse_eq_symbols
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

urls_expire_after = {
    "*/v8/finance/chart/*NSEI*": 60,
    "*/v8/finance/chart/*BSESN*": 60,
    "*/v8/finance/chart/%5ENSEI*": 60,
    "*/v8/finance/chart/%5EBSESN*": 60,
    "*": 86400,
}

cache_dir = os.environ.get(
    "CACHE_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data")
)
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir, exist_ok=True)

# Session Isolation: Pipeline session remains for other requests if any
pipeline_cache_file = os.path.join(cache_dir, "pipeline_cache")

pipeline_session = requests_cache.CachedSession(
    pipeline_cache_file,
    urls_expire_after=urls_expire_after,
    backend="sqlite",
    allowable_codes=[200, 404],
)

retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"],
    respect_retry_after_header=True,
)

adapter = HTTPAdapter(max_retries=retry_strategy)
pipeline_session.mount("https://", adapter)
pipeline_session.mount("http://", adapter)

pipeline_session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
)

# Backward compatibility for any direct imports of 'session'
session = pipeline_session


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


def fetch_stock_data(
    symbol: str, append_ns: bool = True, period: str = "1y", fetch_info: bool = True
):
    try:
        ticker_symbol = symbol
        if append_ns and not symbol.endswith(".NS"):
            ticker_symbol = f"{symbol}.NS"

        # No session injection for yfinance 0.2.66+
        ticker = yf.Ticker(ticker_symbol)
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


def fetch_market_snapshots(
    symbols: list[str] = ["^NSEI", "^BSESN"], period: str = "5d"
) -> list[dict]:
    """
    Dedicated function to fetch market snapshots efficiently using yf.download.
    """
    try:
        # yf.download is much faster and less prone to rate limits for pure price data
        # No session injection for yfinance 0.2.66+
        data = yf.download(
            symbols, period=period, progress=False, threads=False, auto_adjust=False
        )

        if data.empty:
            return []
        snapshots = []
        for symbol in symbols:
            try:
                # When downloading multiple tickers, yf returns a MultiIndex column DataFrame
                # If only one ticker is requested, it's a single index DataFrame
                if len(symbols) > 1:
                    close_series = data["Close"][symbol].dropna()
                else:
                    close_series = data["Close"].dropna()

                if len(close_series) >= 2:
                    current_close = float(close_series.iloc[-1])
                    prev_close = float(close_series.iloc[-2])
                    change_pct = ((current_close - prev_close) / prev_close) * 100

                    snapshots.append(
                        {
                            "symbol": symbol,
                            "close": current_close,
                            "change_pct": change_pct,
                        }
                    )
            except KeyError:
                logger.warning(
                    f"Could not extract data for {symbol} from bulk download."
                )
                continue

        return snapshots
    except Exception as e:
        logger.error(f"Error bulk fetching market snapshots: {e}")
        return []


def slice_bulk_df(bulk_df: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    """Extracts OHLCV for a symbol from a MultiIndex or flat DataFrame."""
    try:
        suffix_symbol = f"{symbol}.NS"
        if isinstance(bulk_df.columns, pd.MultiIndex):
            df = bulk_df.xs(suffix_symbol, axis=1, level=1).copy()
        else:
            # Fallback for single-symbol batches where yfinance returns flat columns
            df = bulk_df.copy()

        df = df.dropna(how="all")
        if df.empty:
            return None
        return df
    except (KeyError, AttributeError):
        return None
