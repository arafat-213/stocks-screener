# Design Spec: Pipeline Resiliency and Bulk Refactor

**Date:** 2026-05-11
**Status:** Draft
**Topic:** Fixing Yahoo Finance 429 rate limiting and API unresponsiveness during pipeline execution.

## 1. Purpose
The current pipeline fetches detailed data for ~2,400 stocks sequentially, triggering Yahoo Finance rate limits (429 errors). Compounding this, the API becomes unresponsive during pipeline execution because shared network sessions and threadpools are exhausted by blocking retry logic and DB connection holds.

This design refactors the pipeline to a "Bulk-First" model and isolates the network sessions to ensure dashboard stability.

## 2. Architecture & Data Flow

### 2.1 Pipeline: Tiered Bulk Fetching
To reduce request volume from ~7,000+ to <1,000 per day:

1.  **Tier 1: Segmented Bulk OHLCV (2,400 symbols)**
    *   Divide the universe into batches of 500.
    *   Use `yf.download(batch, period="2y", session=pipeline_session)` for each batch.
    *   Extract per-symbol DataFrames using `bulk_data.xs(symbol, axis=1, level=1)`.
2.  **Tier 1.1: Technical Filtering (Pure Python)**
    *   Run EMA, RSI, and Volume scorers on the bulk OHLCV data.
    *   Filter down to ~500-800 technical survivors.
3.  **Tier 1.5: Surgical Liquidity Check (Survivors only)**
    *   Call `ticker.fast_info` on technical survivors to check `market_cap` and `averageVolume`.
    *   Filter down to final ~300 survivors for deep fundamental analysis.
4.  **Tier 2: Deep Fundamentals (Final ~300)**
    *   Call `.info` and `.financials` for survivors.
    *   Populate `FundamentalCache` and `FundamentalData`.
    *   Maintain existing 4s/50-batch sleep and checkpointing.

### 2.2 API Resiliency: Isolation & Concurrency
To prevent the dashboard from hanging during pipeline runs:

1.  **Session Isolation (`fetcher.py`)**
    *   Split into `yf_session` (for API/Dashboard) and `pipeline_session` (for Pipeline).
    *   Prevents pipeline-triggered 429s from blocking dashboard requests.
2.  **Bounded Backoff**
    *   Set `respect_retry_after_header=False` in both sessions.
    *   Ensures threads are only blocked for predictable backoff durations, not arbitrary 120s+ windows dictated by Yahoo.
3.  **Async Offloading (`dashboard.py`)**
    *   Convert `/api/dashboard/market/live` to `async def`.
    *   Use `asyncio.to_thread()` to run the synchronous `get_live_market_data` (yfinance call) in a separate thread.
    *   Keeps the FastAPI event loop responsive.

## 3. Data Structures & Interfaces

### 3.1 Network Sessions
*   `yf_session`: Module-level singleton for read-only dashboard/stock-detail requests.
*   `pipeline_session`: Module-level singleton for write-heavy pipeline operations.

### 3.2 Slicing Helper
```python
def slice_bulk_df(bulk_df, symbol):
    # Extracts [Open, High, Low, Close, Volume] for a symbol from a MultiIndex DF
    try:
        df = bulk_df.xs(symbol, axis=1, level=1).copy()
        return df.dropna()
    except KeyError:
        return None
```

## 4. Error Handling & Edge Cases
*   **Empty Bulk Batch:** If `yf.download` returns an empty DF for a batch, log a `PipelineError` for that batch and proceed to the next to ensure partial completion.
*   **Partial MultiIndex:** If some symbols are missing from the bulk response, they are treated as failed and skipped during slicing.
*   **Persistent 429s:** With `respect_retry_after_header=False`, the pipeline will fail faster on persistent throttling, which is preferred over hanging the entire system.

## 5. Implementation Plan (Summary)
1.  Refactor `fetcher.py`: Isolate sessions and update retry logic.
2.  Update `orchestrator.py`: Implement segmented `yf.download` and tiered filtering logic.
3.  Update `dashboard.py`: Convert market-live endpoint to async with `to_thread`.
4.  Verify: Run pipeline with a small limit (e.g., 50) then full run.
