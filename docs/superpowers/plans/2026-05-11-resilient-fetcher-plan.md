# Resilient Market Data Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a resilient, multi-layered fetching strategy for `yfinance` to handle aggressive rate-limiting using local caching and exponential backoff.

**Architecture:** We will configure a custom `requests_cache.CachedSession` with an SQLite backend and `urllib3.util.retry.Retry` adapter. This session will be injected into all `yfinance` calls. A new dedicated `fetch_market_snapshots` method using `yf.download` will be created for the live endpoint to bypass rate-heavy metadata endpoints. We will rely solely on `requests-cache` for TTL management to prevent duplicate/conflicting caches.

**Tech Stack:** Python, yfinance, requests-cache, urllib3, pytest, unittest.mock

---

### Task 1: Setup Unstoppable Session Configuration & Dependencies

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `.gitignore`
- Modify: `backend/app/pipeline/fetcher.py`
- Create: `backend/tests/unit/test_fetcher_session.py`

- [ ] **Step 1: Update dependencies and gitignore**

Modify `backend/requirements.txt` to pin required versions (yfinance >= 0.2.18 is needed for session injection in yf.download):
```text
# Add or update these lines
requests-cache>=1.3.2
yfinance>=0.2.31
urllib3>=2.0.0
```

Modify `.gitignore` (in the project root) to prevent committing the cache directory:
```text
# Add this line
backend/data/
```

- [ ] **Step 2: Write the failing test for session config**

```python
# backend/tests/unit/test_fetcher_session.py
import os
import pytest
from unittest.mock import patch
from app.pipeline.fetcher import session

def test_session_configuration():
    assert session.__class__.__name__ == 'CachedSession'
    assert session.cache.backend.__class__.__name__ == 'SQLiteCache'

    # Check TTLs (Testing the underlying dict pattern)
    urls_expire_dict = dict(session.settings.urls_expire_after)
    assert '*/v8/finance/chart/^NSEI*' in urls_expire_dict
    assert urls_expire_dict['*/v8/finance/chart/^NSEI*'] == 60
    assert urls_expire_dict['*'] == 86400

    # Check Retries
    adapter = session.get_adapter("https://")
    retry = adapter.max_retries
    assert retry.total == 5
    assert retry.backoff_factor == 2
    assert 429 in retry.status_forcelist
    assert retry.respect_retry_after_header is True

    # Check allowed methods (urllib3 v2+ uses allowed_methods)
    assert 'GET' in retry.allowed_methods
```

- [ ] **Step 3: Run test to verify it fails (or passes if already implemented)**
Run: `pytest backend/tests/unit/test_fetcher_session.py -v`

- [ ] **Step 4: Write minimal implementation in fetcher.py**
*(Note: Code is already partially implemented in `backend/app/pipeline/fetcher.py` during debugging, ensure it matches this exactly. Also note: `urls_expire_after` patterns assume yfinance uses `/v8/finance/chart/`. Consider enabling `requests_cache` debug logging on first run to verify cache hits).*
```python
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
```

- [ ] **Step 5: Run test to verify it passes**
Run: `pytest backend/tests/unit/test_fetcher_session.py -v`

- [ ] **Step 6: Commit**
```bash
git add backend/tests/unit/test_fetcher_session.py backend/app/pipeline/fetcher.py backend/requirements.txt .gitignore
git commit -m "feat: configure resilient requests-cache session with exponential backoff and dependencies"
```

---

### Task 2: Inject Session into Pipeline Fetcher Functions & Router

**Files:**
- Modify: `backend/app/pipeline/fetcher.py`
- Modify: `backend/app/routers/dashboard.py`
- Create: `backend/tests/unit/test_fetcher_functions.py`

- [ ] **Step 1: Write failing test for session injection**
```python
# backend/tests/unit/test_fetcher_functions.py
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from app.pipeline.fetcher import fetch_stock_data, fetch_market_snapshots, session

@patch('yfinance.Ticker')
def test_fetch_stock_data_uses_session(mock_ticker):
    mock_instance = MagicMock()
    mock_ticker.return_value = mock_instance
    # Ensure hist has an index so hist.empty works correctly
    mock_instance.history.return_value = pd.DataFrame({'Close': [100, 101]}, index=pd.date_range('2023-01-01', periods=2))

    # We pass fetch_info=False to test the new signature
    fetch_stock_data("RELIANCE", fetch_info=False)

    mock_ticker.assert_called_once_with("RELIANCE.NS", session=session)

@patch('yfinance.download')
def test_fetch_market_snapshots_uses_session(mock_download):
    mock_download.return_value = pd.DataFrame()
    fetch_market_snapshots(["^NSEI"])

    mock_download.assert_called_once_with(["^NSEI"], period="5d", progress=False, session=session)
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest backend/tests/unit/test_fetcher_functions.py -v`
Expected: Fail, because `fetch_stock_data` doesn't have the `fetch_info` parameter yet and doesn't inject the session.

- [ ] **Step 3: Update fetcher.py and dashboard.py**

In `backend/app/pipeline/fetcher.py`, update the signatures and inject the session.
*Note: `fetch_info=True` is the default to preserve existing behavior for orchestrator callers.*
```python
# Add these functions to backend/app/pipeline/fetcher.py
def fetch_stock_data(symbol: str, append_ns: bool = True, period: str = "1y", fetch_info: bool = True):
    try:
        ticker_symbol = f"{symbol}.NS" if append_ns else symbol
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
    try:
        data = yf.download(symbols, period=period, progress=False, session=session)

        if data.empty:
            return []

        snapshots = []
        for symbol in symbols:
            try:
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
```

In `backend/app/routers/dashboard.py`, wire the live endpoint to use `fetch_market_snapshots` and remove the redundant `cachetools` dependency since `requests-cache` handles TTL natively:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.db.models import Stock, TechnicalSignal, FundamentalData, PipelineRun, MarketSnapshot, FundamentalCache
from app.pipeline.fetcher import fetch_stock_data, fetch_market_snapshots

router = APIRouter()

def get_live_market_data():
    # Relies entirely on requests-cache for the 60s TTL
    return fetch_market_snapshots(["^NSEI", "^BSESN"])

@router.get("/market/live")
def get_live_market():
    return {"market_context": get_live_market_data()}

# ... keep existing get_dashboard_results below
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest backend/tests/unit/test_fetcher_functions.py -v`

- [ ] **Step 5: Commit**
```bash
git add backend/tests/unit/test_fetcher_functions.py backend/app/pipeline/fetcher.py backend/app/routers/dashboard.py
git commit -m "feat: inject custom session into fetchers and simplify router caching"
```

---

### Task 3: Inject Session into Tier 2 Screener

**Files:**
- Modify: `backend/app/pipeline/screener.py`
- Create: `backend/tests/unit/test_screener_session.py`

- [ ] **Step 1: Write test for screener session injection**
```python
# backend/tests/unit/test_screener_session.py
import pytest
import datetime
from unittest.mock import patch, MagicMock
from app.pipeline.screener import fetch_and_cache_deep_fundamentals, CURRENT_SCREENER_VERSION
from app.pipeline.fetcher import session as yf_session

@patch('app.pipeline.screener.yf.Ticker')
def test_screener_uses_resilient_session(mock_ticker):
    # Setup mock to not crash on DB operations
    mock_instance = MagicMock()
    mock_ticker.return_value = mock_instance
    mock_instance.info = {'marketCap': 1e10}
    mock_instance.financials = MagicMock(empty=True)
    mock_instance.balance_sheet = MagicMock(empty=True)
    mock_instance.cashflow = MagicMock(empty=True)

    mock_db_session = MagicMock()
    mock_cache = MagicMock()
    # Mocking properties to prevent TypeError during comparisons
    mock_cache.last_updated = datetime.datetime.utcnow()
    mock_cache.cache_version = CURRENT_SCREENER_VERSION
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_cache

    fetch_and_cache_deep_fundamentals(["TEST"], mock_db_session)

    mock_ticker.assert_called_with("TEST.NS", session=yf_session)
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest backend/tests/unit/test_screener_session.py -v`

- [ ] **Step 3: Update screener.py**
```python
# backend/app/pipeline/screener.py
# Add the import at the top (after other imports)
from app.pipeline.fetcher import session as yf_session

# ... inside fetch_and_cache_deep_fundamentals loop around line 43:
            for attempt in range(max_retries):
                try:
                    ticker = yf.Ticker(f"{symbol}.NS", session=yf_session)
                    info = ticker.info

# ⚠️ Implementation Note: The injected session already handles retries via
# urllib3 Retry (5 attempts, exponential backoff). The screener's own
# manual retry loop (max_retries=3) should be REDUCED to max_retries=1
# (effectively disabling it) to prevent double-retrying and pipeline slowdowns.
# The session-level retry is the authoritative mechanism.
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest backend/tests/unit/test_screener_session.py -v`

- [ ] **Step 5: Commit**
```bash
git add backend/tests/unit/test_screener_session.py backend/app/pipeline/screener.py
git commit -m "fix: inject resilient session into tier 2 deep fundamental fetching"
```
