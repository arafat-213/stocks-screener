# Resilient Market Data Fetcher Architecture

## Overview
To bypass Yahoo Finance's aggressive rate-limiting (`429 Too Many Requests`) without requiring paid broker API subscriptions, we are implementing a multi-layered resilient fetching strategy for the backend data pipeline. This strategy prioritizes reliability and eventual consistency over raw speed, allowing both heavy pipeline scans and lightweight live endpoint queries to succeed.

## Architecture & Layers

### 1. Persistent Local Caching (`requests-cache`)
*   **Mechanism:** All HTTP requests made to `yfinance` endpoints are routed through a `requests_cache.CachedSession` backed by an SQLite database.
*   **Storage Location:** The cache file location is primarily governed by the `CACHE_DIR` environment variable, which should map to a persistent volume in cloud deployments. As a fallback, it defaults to a `data/` directory relative to the backend project root. Relying on ephemeral directories (like `/tmp`) breaks resumability across container restarts.
*   **Per-URL Expiration (TTL):**
    *   **Live Market Snapshots (`^NSEI`, `^BSESN`):** 60 seconds. This ensures the `/api/market/live` endpoint returns genuinely fresh data while still buffering rapid successive calls.
    *   **Historical & Fundamental Data:** 24 hours (86400 seconds). Ensures the daily pipeline does not redundantly re-fetch data it already pulled earlier in the day.
*   **Known Limitation (Live Endpoint Concurrent Cache Misses):** With a 60-second TTL on the live endpoint, multiple concurrent requests (e.g. from multiple users opening the dashboard at exactly the 60-second mark) may trigger parallel cache misses, causing concurrent `yfinance` fetches before the first fetch populates the cache. We accept this small risk given the low anticipated concurrency of this internal dashboard.
*   **Cache Invalidation Note:** Cache hits depend on deterministic URLs. The `period` parameter in `fetch_stock_data` is hardcoded (e.g., `"3y"`) to ensure stable cache keys.
*   **Thread Safety Note:** `requests-cache` using SQLite in WAL mode handles concurrent reads well, but concurrent writes from multiple parallel pipeline instances could cause locking issues. We rely on the pipeline's singleton execution model (guarded by the orchestrator) to prevent write conflicts.

### 2. Automatic Retries with Exponential Backoff
*   **Mechanism:** The cached session is mounted with a custom HTTP adapter utilizing `urllib3.util.retry.Retry`.
*   **Configuration:**
    *   **Max Retries:** 5 attempts.
    *   **Backoff Factor:** 2. Given `urllib3`'s math (`{backoff_factor} * (2 ** (retry_number - 1))`), this yields actual wait times of 0s, 2s, 4s, 8s, and 16s before final failure.
    *   **Triggers:** HTTP status codes `[429, 500, 502, 503, 504]`.
    *   **Header Adherence:** `respect_retry_after_header=True` is enabled so the adapter honors the `Retry-After` header sent by Yahoo Finance if present.
*   **Fallback Behavior:** If all 5 retries are exhausted, the wrapper catches the exception, logs it, and returns `None`. The calling orchestrator logic gracefully skips the stock and continues with the pipeline.

### 3. Dedicated Market Snapshot Method
*   **Mechanism:** A new `fetch_market_snapshots` method is introduced, strictly utilizing `yf.download` for bulk price history.
*   **Benefit:** Avoids the instantiation of `yf.Ticker` objects for simple index quotes, which internally trigger requests to heavily rate-limited fundamental data endpoints (`quoteSummary`).
*   **Version Dependency:** Passing the `session` parameter to `yf.download` requires `yfinance >= 0.2.18`. Our `requirements.txt` correctly pins `yfinance==0.2.31`, ensuring this feature works as intended and the session logic isn't silently bypassed.

### 4. User-Agent Modification
*   **Mechanism:** The session headers are updated to mimic a standard desktop browser.
*   **Caveat:** Modern WAFs look at TLS handshakes and request cadence, not just User-Agents. This is a marginal defense (security through obscurity) and is not relied upon as the primary anti-blocking mechanism.

## Usage & Integration

The custom `session` object is injected globally into all `yfinance` interactions:
1.  **`app.pipeline.fetcher.fetch_stock_data`:** Injected into `yf.Ticker(symbol, session=session)`.
2.  **`app.pipeline.fetcher.fetch_market_snapshots`:** Injected into `yf.download(..., session=session)`.
3.  **`app.pipeline.screener.fetch_and_cache_deep_fundamentals`:** Injected into `yf.Ticker(symbol, session=session)`. This is the most heavily rate-limited section of the codebase (Tier 2 fundamentals) and requires the retry/cache logic to succeed reliably.
