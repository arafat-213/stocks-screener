# Pipeline Resiliency and Bulk Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix Yahoo Finance 429 rate limiting by implementing a "Bulk-First" pipeline and resolve API unresponsiveness by isolating network sessions and offloading blocking calls.

**Architecture:** 
1. **Bulk Pipeline:** Segmented `yf.download` batches (500 symbols) -> Technical Filter -> `fast_info` check -> Surgical Deep Fundamentals.
2. **Resiliency:** Separate `yf_session` (API) and `pipeline_session` (Pipeline) with `respect_retry_after_header=False` and async offloading for the market-live endpoint.

**Tech Stack:** Python, FastAPI, yfinance, requests-cache, SQLAlchemy, pandas.

---

### Task 1: Fetcher Resiliency & Session Isolation

**Files:**
- Modify: `backend/app/pipeline/fetcher.py`

- [x] **Step 1: Isolate Sessions and Update Retry Logic**
Modify `backend/app/pipeline/fetcher.py` to create separate session objects and set `respect_retry_after_header=False`.

```python
# backend/app/pipeline/fetcher.py

# ... existing imports ...
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# ... cache setup ...

retry_strategy = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"],
    respect_retry_after_header=False  # Crucial: Don't block thread for arbitrary duration
)
adapter = HTTPAdapter(max_retries=retry_strategy)

# Dashboard Session
yf_session = requests_cache.CachedSession(
    cache_file,
    urls_expire_after=urls_expire_after,
    backend='sqlite'
)
yf_session.mount("https://", adapter)
yf_session.mount("http://", adapter)
yf_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
})

# Pipeline Session
pipeline_session = requests_cache.CachedSession(
    os.path.join(cache_dir, 'pipeline_cache'), # Separate cache file
    urls_expire_after={'*': 3600}, # 1 hour expiry for pipeline runs
    backend='sqlite'
)
pipeline_session.mount("https://", adapter)
pipeline_session.mount("http://", adapter)
pipeline_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
})

# Update existing functions to use yf_session by default, 
# but orchestrator will use pipeline_session for bulk.
# (Update fetch_stock_data and fetch_market_snapshots to use yf_session)
```

- [x] **Step 2: Add `slice_bulk_df` Helper**
Add the helper to `backend/app/pipeline/fetcher.py` to handle MultiIndex slicing and single-symbol fallback.

```python
def slice_bulk_df(bulk_df: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    """Extracts OHLCV for a symbol from a MultiIndex or flat DataFrame."""
    try:
        suffix_symbol = f"{symbol}.NS"
        if isinstance(bulk_df.columns, pd.MultiIndex):
            df = bulk_df.xs(suffix_symbol, axis=1, level=1).copy()
        else:
            # Fallback for single-symbol batches where yfinance returns flat columns
            df = bulk_df.copy()
            
        df = df.dropna(how='all')
        if df.empty:
            return None
        return df
    except (KeyError, AttributeError):
        return None
```

- [x] **Step 3: Commit**
```bash
git add backend/app/pipeline/fetcher.py
git commit -m "feat: isolate pipeline session and add bulk slicing helper"
```

---

### Task 2: Unit Testing for Bulk Refactor

**Files:**
- Create: `backend/tests/unit/test_bulk_refactor.py`

- [x] **Step 1: Write test for `slice_bulk_df`**
Test both MultiIndex and single-symbol scenarios.

```python
import pandas as pd
import pytest
from app.pipeline.fetcher import slice_bulk_df

def test_slice_bulk_df_multiindex():
    cols = pd.MultiIndex.from_tuples([('Close', 'RELIANCE.NS'), ('Open', 'RELIANCE.NS')])
    df = pd.DataFrame([[100, 90], [110, 100]], columns=cols)
    sliced = slice_bulk_df(df, 'RELIANCE')
    assert sliced is not None
    assert 'Close' in sliced.columns
    assert sliced.iloc[0]['Close'] == 100

def test_slice_bulk_df_single():
    df = pd.DataFrame([[100, 90]], columns=['Close', 'Open'])
    sliced = slice_bulk_df(df, 'RELIANCE')
    assert sliced is not None
    assert sliced.iloc[0]['Close'] == 100
```

- [x] **Step 2: Run tests**
Run: `pytest backend/tests/unit/test_bulk_refactor.py`
Expected: PASS

- [x] **Step 3: Commit**
```bash
git add backend/tests/unit/test_bulk_refactor.py
git commit -m "test: add unit tests for bulk slicing"
```

---

### Task 3: Tier 1 & 1.1 Orchestration (Bulk Download + Technical Filter)

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [x] **Step 1: Implement Segmented Bulk Download**
Modify `run_pipeline` in `backend/app/pipeline/orchestrator.py` to fetch symbols in batches of 500 using `yf.download`.

- [x] **Step 2: Implement Technical Filter (Tier 1.1)**
Run `calculate_combined_score` (technical only) on the bulk data to identify survivors (~500-800).

```python
# Inside run_pipeline (replacing existing Tier 1 loop)
batch_size = 500
technical_survivors = []
for i in range(0, len(symbols), batch_size):
    batch = symbols[i:i+batch_size]
    suffix_batch = [s + ".NS" for s in batch]
    
    logger.info(f"Bulk downloading Tier 1 data for batch {i//batch_size + 1}")
    bulk_data = yf.download(suffix_batch, period="2y", progress=False, session=pipeline_session)
    
    for symbol in batch:
        hist = slice_bulk_df(bulk_data, symbol)
        if hist is None: continue
        
        # Technical Score Only
        scores = calculate_combined_score(hist, {})  # Pass empty dict, not None
        if scores['is_bullish'] or scores['score'] > 40:  # 'score', not 'combined_score'
            technical_survivors.append((symbol, hist))
```

- [x] **Step 3: Commit**
```bash
git add backend/app/pipeline/orchestrator.py
git commit -m "feat: implement segmented bulk download and technical filtering"
```

---

### Task 4: Tier 1.5 & 2 Orchestration (Liquidity Check + Deep Fundamentals)

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`
- Modify: `backend/app/pipeline/screener.py`

- [x] **Step 0 (addition): Update screener.py import**
In `backend/app/pipeline/screener.py`, update the import:
`from app.pipeline.fetcher import session as yf_session`  →  `from app.pipeline.fetcher import pipeline_session as yf_session`

- [x] **Step 1: Implement Surgical Liquidity Check (Tier 1.5)**
For the `technical_survivors`, call `ticker.fast_info` to filter by `market_cap` and `averageVolume`.

- [x] **Step 2: Deep Fundamentals (Tier 2)**
Proceed with surgical `.info` and `.financials` for the final ~300 survivors.

```python
# In orchestrator.py
final_survivors = []
for symbol, hist in technical_survivors:
    ticker = yf.Ticker(symbol + ".NS", session=pipeline_session)
    fi = ticker.fast_info
    mcap = getattr(fi, 'market_cap', None) or 0
    last_price = getattr(fi, 'last_price', None) or 0
    avg_vol = getattr(fi, 'three_month_average_volume', None) or 0

    if mcap > 2_000_000_000 and (avg_vol * last_price > 20_000_000):
        final_survivors.append(symbol)

# Proceed to Tier 2 with final_survivors...
```

- [x] **Step 3: Commit**
```bash
git add backend/app/pipeline/orchestrator.py backend/app/pipeline/screener.py
git commit -m "feat: implement tier 1.5 liquidity check and surgical fundamentals"
```

---

### Task 5: API Resiliency (Async Market Live)

**Files:**
- Modify: `backend/app/routers/dashboard.py`

- [x] **Step 1: Convert `/market/live` to Async**
Use `asyncio.to_thread` to offload the yfinance market snapshot call.

```python
# backend/app/routers/dashboard.py
import asyncio

@router.get("/market/live")
async def get_live_market(response: Response):
    cache_key = "dashboard:market_live"
    cached, hit = response_cache.get(cache_key)
    if hit:
        response.headers["X-Cache"] = "HIT"
        return cached
    
    response.headers["X-Cache"] = "MISS"
    # Offload sync yfinance call to thread
    market_context = await asyncio.to_thread(get_live_market_data)
    data = {"market_context": market_context}
    response_cache.set(cache_key, data, 60)
    return data
```

- [x] **Step 2: Commit**
```bash
git add backend/app/routers/dashboard.py
git commit -m "fix: make market-live endpoint async-safe"
```

---

### Task 6: Verification

- [x] **Step 1: Run Pipeline with small limit**
Run: `python3 -c "from app.db.session import SessionLocal; from app.pipeline.orchestrator import run_pipeline; db=SessionLocal(); run_pipeline(db, limit=50)"`
Check `logs/pipeline.log` for bulk download messages.

- [x] **Step 2: Verify Dashboard responsiveness**
Start server: `uvicorn app.main:app`
Trigger pipeline: `curl -X POST http://localhost:8000/api/screener/run -d '{"limit": 100}'`
Simultaneously call health/live: `curl http://localhost:8000/api/health` and `curl http://localhost:8000/api/market/live`
Expected: Both return promptly while pipeline is running.

- [x] **Step 3: Commit all remaining**
```bash
git add .
git commit -m "chore: final verification and cleanup"
```
