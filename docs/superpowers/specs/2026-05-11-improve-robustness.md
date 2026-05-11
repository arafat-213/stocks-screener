# Screener AI — Robustness Improvements Spec

**Version:** 1.0  
**Scope:** Backend pipeline reliability, screen result caching, API performance, and frontend resilience  
**Purpose:** Provide a complete, implementation-ready specification for an AI coding agent to produce a detailed implementation plan

---

## 1. Context & Problem Statement

The current system has several reliability and performance gaps:

1. **Named screens hit the database (and sometimes re-run live Python logic) on every API request.** The `GET /screens/{slug}` endpoint tries a DB lookup first, but the `ScreenResult` table is only populated after a full pipeline run. If no materialized results exist for today, it falls through to live execution — which can be slow and fragile.

2. **No in-process or HTTP-layer caching.** Every frontend poll re-runs the same SQLAlchemy queries. The live market endpoint (`/market/live`) relies entirely on `requests-cache` with a 60-second TTL, but there is no equivalent protection on any other endpoint.

3. **yfinance rate-limiting is handled at the fetcher level but not surfaced cleanly.** When the pipeline hits rate limits mid-run, the error is logged but the affected symbol is silently skipped. There is no dead-letter queue, retry budget tracking, or per-run error summary exposed through the API.

4. **The pipeline has no incremental mode.** If a run crashes halfway through, the next full run re-fetches every symbol from scratch, including those already written to `TechnicalSignal`. This wastes quota and time.

5. **`FundamentalCache` stale-data check is simplistic.** The 7-day TTL is hardcoded, and there is no mechanism to force-refresh a single symbol or to detect that yfinance returned a stale or truncated response.

6. **RS rank computation is single-threaded and blocking.** `_compute_rs_ranks` fetches the benchmark, then does an in-process sort and bulk update. For 1000+ signals this is fine, but it runs synchronously inside the pipeline and cannot be isolated or tested independently.

7. **Frontend has no stale-data indicator.** If the pipeline last ran 3 days ago, the dashboard shows old scores with no visual warning. Users have no way to know data freshness without visiting the System page.

8. **No structured error taxonomy.** `PipelineRun.errors` is a free-text `Text` column. Parsing it for monitoring or alerting is impossible.

---

## 2. Goals & Non-Goals

### Goals

- Eliminate redundant database queries on every screen endpoint call through a proper caching layer
- Make the pipeline restartable/resumable after a partial failure
- Surface data freshness to both the API and the frontend
- Add structured error tracking to pipeline runs
- Protect all high-traffic API endpoints from repeated heavy queries
- Make `FundamentalCache` refresh smarter (per-symbol, forced-refresh capable)
- Decouple RS rank computation so it can run independently

### Non-Goals

- Switching from PostgreSQL to any other database
- Replacing yfinance with a paid data provider
- Adding authentication/authorization
- Horizontal scaling / multi-worker deployment (out of scope for personal tool)

---

## 3. Improvement Areas & Detailed Specifications

---

### 3.1 Screen Result Caching (Highest Priority)

#### 3.1.1 Problem

`GET /screens/{slug}` currently:

1. Queries `ScreenResult` joined with `Stock`, `FundamentalCache`, and `TechnicalSignal` (4-table join)
2. Falls back to live Python execution if no rows found for today
3. Live execution calls the screen function, which runs another multi-table query, then a second enrichment query for the symbols returned

This means on a cold start (or any day the pipeline hasn't run yet), every screen request runs two heavyweight queries.

#### 3.1.2 Solution: Two-Layer Caching

**Layer 1 — In-process TTL cache on screen results (FastAPI startup)**

Use a simple in-process dictionary with a timestamp to cache the fully-serialized response for each `(slug, live_mode)` pair. This is the cheapest possible cache — no Redis dependency, no configuration.

```
Cache key:   f"screen:{slug}:{live}"
Cache value: (list[dict], datetime)   # serialized response + stored_at
TTL:         15 minutes for live=False, 60 seconds for live=True
Invalidation: explicit invalidation called at end of materialize_all_screens()
```

**Implementation location:** `backend/app/screens/cache.py` (new file)

```python
# Proposed API surface — implementation detail left to agent
class ScreenCache:
    def get(self, key: str) -> list[dict] | None: ...
    def set(self, key: str, value: list[dict], ttl_seconds: int) -> None: ...
    def invalidate(self, slug: str | None = None) -> None: ...
        # slug=None invalidates all entries
    def stats(self) -> dict: ...  # hit/miss counts for /api/health
```

**Layer 2 — DB query result cache on TechnicalSignal subqueries**

The `latest_signal_sub` subquery in `get_screen_results` is computed fresh every request. Wrap it in a module-level cached function with a 5-minute TTL keyed on `(timeframe, date)`.

This is purely an in-process optimization — no new infrastructure needed.

#### 3.1.3 Cache Invalidation

Call `ScreenCache.invalidate()` at the very end of `materialize_all_screens()`, after all slugs have been written to `ScreenResult`. This ensures the next API request after a pipeline run always sees fresh data.

Also add a `POST /api/screens/cache/clear` endpoint (admin use) that calls `ScreenCache.invalidate()`.

#### 3.1.4 API Changes

Add a response header `X-Cache: HIT | MISS` and `X-Cache-Age: <seconds>` to every `/screens/{slug}` response so the frontend and developers can observe cache behavior without logging.

---

### 3.2 Pipeline Resumability

#### 3.2.1 Problem

If the pipeline crashes at symbol #800 of 2000, the next run starts from scratch. All 800 already-written `TechnicalSignal` rows are valid and fresh, but they are recomputed anyway.

#### 3.2.2 Solution: Checkpoint Table + Skip Logic

**New model: `PipelineCheckpoint`**

```python
class PipelineCheckpoint(Base):
    __tablename__ = "pipeline_checkpoints"
    run_id      = Column(String, ForeignKey('pipeline_runs.run_id'), primary_key=True)
    phase       = Column(String, primary_key=True)  
                 # 'tier1', 'tier2_refresh', 'scoring', 'rs_ranks', 'snapshots', 'report', 'screens'
    completed_symbols = Column(Text)  # JSON array of symbols that finished this phase
    started_at  = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)
```

**Resume logic in `run_pipeline()`**

Add a `resume_run_id: str | None = None` parameter. When provided:

1. Load `PipelineCheckpoint` rows for that `run_id`
2. For each phase, skip symbols already in `completed_symbols`
3. Log how many symbols were skipped due to checkpoint

**`POST /screener/run` request body change**

```json
{
  "limit": null,
  "resume_run_id": null   // new optional field
}
```

**Checkpoint write cadence**

Write checkpoint after every successful symbol in the scoring phase (batched: flush every 25 symbols to avoid per-symbol commits). Write phase-level checkpoints at phase transitions (tier1 complete, tier2 complete, etc.).

**Cleanup**

Delete `PipelineCheckpoint` rows for a `run_id` when that run reaches `status = "complete"`. Keep checkpoints for `failed` and `stopped` runs for 7 days, then purge via a startup cleanup task.

---

### 3.3 Structured Error Tracking

#### 3.3.1 Problem

`PipelineRun.errors` is a single `Text` column that concatenates error strings. It cannot be queried, filtered, or counted programmatically.

#### 3.3.2 Solution: `PipelineError` Table

**New model:**

```python
class PipelineError(Base):
    __tablename__ = "pipeline_errors"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    run_id      = Column(String, ForeignKey('pipeline_runs.run_id'), nullable=False)
    symbol      = Column(String, nullable=True)   # null for pipeline-level errors
    phase       = Column(String, nullable=False)  
                 # 'fetch', 'tier1', 'tier2', 'scoring', 'rs_ranks', 'snapshot', 'report'
    error_type  = Column(String, nullable=False)  
                 # 'rate_limit', 'empty_data', 'db_write', 'timeout', 'unknown'
    message     = Column(Text, nullable=False)
    traceback   = Column(Text, nullable=True)
    occurred_at = Column(DateTime, default=datetime.datetime.utcnow)
```

**Error classification helper** in `backend/app/pipeline/errors.py` (new file):

```python
def classify_error(exc: Exception) -> str:
    """Returns one of: 'rate_limit', 'empty_data', 'db_write', 'timeout', 'unknown'"""
    msg = str(exc).lower()
    if "429" in msg or "too many requests" in msg or "rate limit" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if isinstance(exc, (sqlalchemy.exc.SQLAlchemyError,)):
        return "db_write"
    # ... etc
    return "unknown"
```

**API exposure:**

`GET /api/pipeline/errors?run_id=<id>&phase=<phase>&error_type=<type>` — returns paginated list of `PipelineError` rows. Add this to the System page's pipeline status panel.

**Keep `PipelineRun.errors`** as a short human-readable summary string (e.g. `"47 errors: 12 rate_limit, 30 empty_data, 5 unknown"`) rather than the full dump.

---

### 3.4 Smart FundamentalCache Refresh

#### 3.4.1 Problem

The current stale check is:
```python
cache.last_updated < seven_days_ago or cache.cache_version < CURRENT_SCREENER_VERSION
```

This has two issues:
- A symbol that returned corrupt/empty data from yfinance is retried every 7 days, wasting quota
- There is no way to force-refresh a single symbol without editing the DB directly

#### 3.4.2 Solution

**Add fields to `FundamentalCache`:**

```python
retry_after     = Column(DateTime, nullable=True)   
                  # set to utcnow() + 24h when yfinance returns empty/corrupt data
fetch_attempts  = Column(Integer, default=0)         
                  # incremented each attempt; reset to 0 on success
last_error      = Column(String, nullable=True)      
                  # short error string from last failed attempt
force_refresh   = Column(Boolean, default=False)     
                  # set to True via API; cleared after next successful fetch
```

**Updated stale check logic** in `orchestrator.py`:

```python
def _needs_refresh(cache, seven_days_ago) -> bool:
    if cache is None:
        return True
    if cache.force_refresh:
        return True
    if cache.retry_after and datetime.datetime.utcnow() < cache.retry_after:
        return False   # back off: don't retry yet
    if cache.last_updated < seven_days_ago:
        return True
    if cache.cache_version < CURRENT_SCREENER_VERSION:
        return True
    return False
```

**Backoff on failure** in `screener.py`:

When `fetch_and_cache_deep_fundamentals` fails all retries for a symbol:
- If `error_type == 'rate_limit'`: set `retry_after = utcnow() + 6 hours`
- If `error_type == 'empty_data'` and `fetch_attempts >= 3`: set `retry_after = utcnow() + 24 hours`
- Otherwise: set `retry_after = utcnow() + 2 hours`

**New API endpoints:**

```
POST /api/stocks/{symbol}/refresh-cache
    Body: {}
    Effect: sets FundamentalCache.force_refresh = True for that symbol
    Returns: { "queued": true }

GET /api/stocks/{symbol}/cache-status  
    Returns: {
        "symbol": "RELIANCE",
        "last_updated": "...",
        "cache_version": 1,
        "fetch_attempts": 2,
        "retry_after": "...",
        "force_refresh": false,
        "last_error": null
    }
```

---

### 3.5 In-Process HTTP Response Caching for Hot Endpoints

#### 3.5.1 Endpoints to Cache

| Endpoint | TTL | Cache Key |
|---|---|---|
| `GET /api/screener/results` | 10 minutes | static |
| `GET /api/market/live` | 60 seconds | static |
| `GET /api/pipeline/latest` | 30 seconds | static |
| `GET /api/screens/` (list) | 1 hour | static |
| `GET /api/screens/{slug}` | 15 minutes | slug |
| `GET /api/reports/latest` | 10 minutes | static |
| `GET /api/reports/{date}` | 1 hour | date |

#### 3.5.2 Implementation

Create `backend/app/core/cache.py` with a generic `ResponseCache` class:

```python
import time
from typing import Any

class ResponseCache:
    """Thread-safe in-process TTL cache. No external dependencies."""
    
    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> tuple[Any, bool]:
        """Returns (value, is_hit). is_hit=False means expired or absent."""
        ...
    
    def set(self, key: str, value: Any, ttl: int) -> None: ...
    
    def invalidate(self, key: str | None = None) -> None:
        """key=None clears everything."""
        ...
    
    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses, "keys": len(self._store)}

response_cache = ResponseCache()   # module-level singleton
```

Use a decorator pattern on router functions:

```python
from app.core.cache import response_cache

def cached(key: str, ttl: int):
    """FastAPI-compatible response caching decorator."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            val, hit = response_cache.get(key)
            if hit:
                return val
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            response_cache.set(key, result, ttl)
            return result
        return wrapper
    return decorator
```

For endpoints with dynamic keys (e.g. `/reports/{date}`, `/screens/{slug}`), compute the key from the path parameter inside the function body rather than using the decorator.

#### 3.5.3 Cache Invalidation Triggers

- Pipeline run `status → "complete"`: invalidate `screener/results`, `pipeline/latest`, all `screens/*`
- New report written: invalidate `reports/latest`, `reports/{today}`

Call `response_cache.invalidate(key)` at the appropriate points in `orchestrator.py` and `reporter.py`.

---

### 3.6 Data Freshness API & Frontend Indicator

#### 3.6.1 New Field on Pipeline Status Response

Add `data_age_hours: float` and `is_stale: bool` to `GET /api/pipeline/latest`:

```json
{
  "status": "complete",
  "scored_at": "2026-05-08T16:30:00",
  "data_age_hours": 47.5,
  "is_stale": true,
  "stocks_fetched": 1800,
  ...
}
```

`is_stale = data_age_hours > 26` (market runs Mon–Fri; anything older than ~1 trading day is stale).

#### 3.6.2 Frontend: Stale Data Banner

In `Dashboard.jsx`, after the market summary bar, add a `StaleBanner` component that renders when `pipeline.is_stale === true`:

```jsx
// Shown at top of dashboard content, below the error banner
<StaleBanner lastUpdated={pipeline.scored_at} />
```

Design: amber/yellow background, warning icon, text like:
> "⚠ Data is 47 hours old. Last pipeline run: Thu, May 8 at 4:30 PM. Run pipeline to refresh."

With a "Run Now" button that calls `handleRunPipeline()`.

Also add a small dot indicator on the System nav item when `is_stale` is true (badge on the nav icon).

#### 3.6.3 StockDetail Page Freshness

On `StockDetail`, show the signal age next to the score: "Signal from 2 days ago" in muted text below each timeframe score card.

---

### 3.7 RS Rank Computation Isolation

#### 3.7.1 Problem

`_compute_rs_ranks` is embedded inside `run_pipeline` with no way to run it standalone. It fetches the benchmark (a potentially slow network call) synchronously.

#### 3.7.2 Solution

**Move to `backend/app/pipeline/rs_ranks.py`** (new file):

```python
def compute_rs_ranks(db: Session, signal_date: datetime.date, benchmark_symbol: str | None = None) -> dict:
    """
    Standalone RS rank computation. Returns summary dict.
    Can be called independently via API or from orchestrator.
    
    Args:
        db: SQLAlchemy session
        signal_date: date to compute ranks for
        benchmark_symbol: override benchmark (default: auto-detect from RS_BENCHMARK_CANDIDATES)
    
    Returns:
        {
            "benchmark_used": "^CRSLDX",
            "benchmark_return": 12.4,
            "signals_updated": 847,
            "skipped_no_momentum": 23
        }
    """
```

**Add API endpoint:**

```
POST /api/pipeline/recompute-rs?date=YYYY-MM-DD
    Effect: runs compute_rs_ranks for the given date (defaults to latest signal date)
    Returns: the summary dict
    Background: runs synchronously (it's fast enough at < 2000 stocks)
```

**In `orchestrator.py`**, replace the inline `_compute_rs_ranks` call with:

```python
from app.pipeline.rs_ranks import compute_rs_ranks
rs_summary = compute_rs_ranks(db, final_signal_date)
logger.info(f"RS rank summary: {rs_summary}")
```

---

### 3.8 Health Endpoint Enhancement

#### 3.8.1 Current State

`GET /api/health` returns `{"status": "ok"}` unconditionally, even if the DB is unreachable.

#### 3.8.2 Enhanced Health Check

```json
GET /api/health

{
  "status": "ok" | "degraded" | "error",
  "db": "ok" | "error",
  "cache": {
    "hits": 1240,
    "misses": 87,
    "keys": 14
  },
  "pipeline": {
    "last_status": "complete",
    "data_age_hours": 22.1,
    "is_stale": false
  },
  "version": "2.1.0"
}
```

DB check: run `SELECT 1` with a 2-second timeout. If it fails, set `"db": "error"` and `"status": "degraded"`.

`"status": "error"` if DB is down. `"status": "degraded"` if DB is ok but data is stale. `"status": "ok"` otherwise.

---

## 4. Database Migration Plan

All schema changes require Alembic migrations. The agent should generate one migration per logical group:

| Migration | Changes |
|---|---|
| `001_pipeline_checkpoint` | Add `pipeline_checkpoints` table |
| `002_pipeline_errors` | Add `pipeline_errors` table; alter `pipeline_runs.errors` column comment |
| `003_fundamental_cache_backoff` | Add `retry_after`, `fetch_attempts`, `last_error`, `force_refresh` to `fundamental_cache` |
| `004_pipeline_run_data_age` | No schema change; computed field — no migration needed |

Each migration must be reversible (implement `downgrade()`).

---

## 5. File Changeset Summary

The following files must be **created**:

```
backend/app/core/__init__.py          (empty)
backend/app/core/cache.py             (ResponseCache class + module singleton)
backend/app/screens/cache.py          (ScreenCache wrapping ResponseCache)
backend/app/pipeline/rs_ranks.py      (extracted compute_rs_ranks function)
backend/app/pipeline/errors.py        (classify_error helper + PipelineError write helper)
alembic/versions/001_pipeline_checkpoint.py
alembic/versions/002_pipeline_errors.py
alembic/versions/003_fundamental_cache_backoff.py
frontend/src/components/StaleBanner.jsx
frontend/src/components/StaleBanner.css
```

The following files must be **modified**:

```
backend/app/db/models.py
    + PipelineCheckpoint model
    + PipelineError model
    + FundamentalCache: add retry_after, fetch_attempts, last_error, force_refresh fields

backend/app/pipeline/orchestrator.py
    + import compute_rs_ranks from rs_ranks.py (replace inline _compute_rs_ranks)
    + add resume_run_id param to run_pipeline()
    + checkpoint write logic throughout pipeline phases
    + call response_cache.invalidate() on pipeline completion
    + write PipelineError rows instead of appending to run.errors string
    - remove _compute_rs_ranks function (moved to rs_ranks.py)

backend/app/pipeline/screener.py
    + backoff/retry_after logic in fetch_and_cache_deep_fundamentals
    + use classify_error() from errors.py
    + increment fetch_attempts, set last_error on failure

backend/app/pipeline/reporter.py
    + call response_cache.invalidate() after writing report

backend/app/screens/materializer.py
    + call ScreenCache.invalidate() after materialize_all_screens() completes

backend/app/routers/dashboard.py
    + add data_age_hours and is_stale to /pipeline/latest response
    + wrap get_dashboard_results with response cache (10 min TTL)
    + wrap get_live_market with response cache (60s TTL)
    + wrap get_pipeline_status with response cache (30s TTL)

backend/app/routers/screens.py
    + use ScreenCache in get_screen_results
    + add POST /screens/cache/clear endpoint
    + add X-Cache and X-Cache-Age response headers

backend/app/routers/stocks.py
    + add POST /stocks/{symbol}/refresh-cache
    + add GET /stocks/{symbol}/cache-status
    + add POST /pipeline/recompute-rs
    + add GET /pipeline/errors

backend/app/routers/reports.py
    + wrap get_latest_report with response cache (10 min TTL)
    + wrap get_report_by_date with response cache (1 hr TTL)

backend/app/main.py
    + update /api/health to enhanced version

frontend/src/hooks/usePipeline.js
    + expose is_stale and data_age_hours from pipeline status response

frontend/src/pages/Dashboard.jsx
    + render <StaleBanner> when pipeline.is_stale
    + pass scored_at to StaleBanner

frontend/src/pages/StockDetail.jsx
    + show signal age below each timeframe score card

frontend/src/components/MainLayout.jsx
    + show amber dot badge on System nav item when is_stale
```

---

## 6. Implementation Order (for the coding agent)

The agent should implement in this order to avoid breaking changes:

1. **`backend/app/core/cache.py`** — pure Python, no dependencies, fully testable in isolation
2. **`backend/app/screens/cache.py`** — depends on core/cache.py
3. **`backend/app/pipeline/errors.py`** — pure helpers + new model
4. **`backend/app/pipeline/rs_ranks.py`** — extracted function, no new logic
5. **DB models + Alembic migrations** — add new tables/columns
6. **`orchestrator.py` changes** — checkpoint + error tracking + RS ranks refactor
7. **`screener.py` changes** — backoff logic
8. **Router changes** — caching decorators + new endpoints
9. **`reporter.py` + `materializer.py`** — cache invalidation hooks
10. **`main.py`** — enhanced health check
11. **Frontend changes** — StaleBanner + signal age display

---

## 7. Acceptance Criteria

The implementation is complete when:

- [ ] `GET /screens/{slug}` returns in < 50ms on cache HIT (vs current ~200–800ms)
- [ ] `X-Cache: HIT` header is present on second request to any screen endpoint
- [ ] A pipeline run interrupted at phase "scoring" can be resumed via `resume_run_id` without re-fetching Tier 1 symbols
- [ ] `GET /api/pipeline/errors?run_id=<id>` returns structured rows for all errors in that run
- [ ] A symbol with 3+ failed fetches has a non-null `retry_after` in `FundamentalCache` and is skipped in the next run
- [ ] `GET /api/health` returns `"status": "degraded"` when `is_stale = true`
- [ ] Dashboard shows the `StaleBanner` when data is > 26 hours old
- [ ] `compute_rs_ranks` can be invoked via `POST /api/pipeline/recompute-rs` without triggering a full pipeline run
- [ ] `POST /api/stocks/{symbol}/refresh-cache` causes that symbol's `FundamentalCache` to be refreshed in the next pipeline run
- [ ] All new Alembic migrations have working `downgrade()` implementations

---

## 8. Out-of-Scope Decisions (Do Not Implement)

- **Redis / Memcached**: All caching is in-process. The tool runs on a single server and adding Redis is unnecessary complexity.
- **Celery / task queue**: Pipeline is already background-task based via FastAPI's `BackgroundTasks`. No separate worker process needed.
- **WebSocket push**: The frontend poll interval (5s when running, 60s at rest) is sufficient. WebSocket adds complexity with no meaningful UX benefit for a personal tool.
- **Rate-limit proxy / rotating IPs**: yfinance TOS prohibits this. Backoff + retry is the correct approach.
- **Parallel symbol fetching**: yfinance bans IPs that parallelize requests aggressively. The current sequential approach with batch sleeps is intentional.