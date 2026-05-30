# Technical Specification: Persistent OHLCV Cache

## Problem Statement

The pipeline and backtest engine independently fetch 3 years of OHLCV history for every symbol on every run via `yfinance`. There is no reuse between runs or between the pipeline and backtest engine.

- **Pipeline run**: ~1.5 hours, dominated by bulk `yf.download` + per-symbol `fetch_stock_data` calls
- **Backtest run**: 45–60 minutes, dominated by per-symbol `fetch_stock_data("3y")` calls for every symbol it processes

Both systems fetch the same data independently, and the existing `requests_cache` (SQLite, HTTP-level) does not fully solve this because its TTL is 86,400 seconds (1 day) for most routes — meaning data fetched at 4 PM is stale by the next morning's backtest.

---

## Goals

1. Eliminate redundant full 3-year fetches on every run.
2. Allow the pipeline and backtest engine to share a single source of OHLCV truth.
3. Reduce pipeline wall-clock time from ~1.5 hours to under 20 minutes after the first cold run.
4. Reduce backtest wall-clock time from ~45 minutes to under 5 minutes when data is fresh.
5. Remain correct: stale data must never be silently served; there must be a clear freshness contract.

---

## Non-Goals

- Real-time (intraday) data is out of scope.
- Replacing the existing `requests_cache` HTTP layer.
- Caching fundamental / info data (covered by `FundamentalCache`).

---

## Proposed Solution: Filesystem Parquet Cache

Store each symbol's OHLCV DataFrame as a Parquet file. On each fetch request, load the existing file, identify the missing date range, fetch only the incremental tail from yfinance, append it, and persist the updated file.

### Why Parquet

| Property | Parquet | SQLite table | CSV |
|---|---|---|---|
| Read speed (3y, ~750 rows) | < 5 ms | ~20–40 ms | ~15 ms |
| Write speed (append) | Low (full rewrite of small file) | Low | Low |
| Preserves dtypes / index | Yes | Needs casting | No |
| Dependency | `pyarrow` (already transitive) | Already present | None |
| Human inspectable | No | Partial | Yes |

A single symbol's 3-year daily file is approximately 50–80 KB. The full NSE universe (~1,800 symbols) is approximately 90–140 MB on disk — well within acceptable bounds.

---

## Data Contract

### Freshness Rules

| Condition | Action |
|---|---|
| File does not exist | Full fetch (3y), write file |
| File exists, last date is today's trading date | Serve from cache, no network call |
| File exists, last date < today's trading date | Incremental fetch from `(last_date + 1 day)` to today, append, write |
| File exists but is corrupt / unreadable | Delete and full fetch |
| Caller passes `force_refresh=True` | Full fetch regardless of file state |

"Today's trading date" is defined as the most recent weekday on or before the current date, adjusted for known NSE holidays if a holiday calendar is available; otherwise the last available row in the file is the authoritative latest date.

### Canonical Date Range

All cached data covers a rolling window of **3 years** from the current date. On full fetches, data older than 3 years is not retained. On incremental fetches, no trimming of old data is required (files grow by at most ~252 rows per year).

---

## Cache Location and Naming

```
<CACHE_DIR>/ohlcv/
    RELIANCE.parquet
    TCS.parquet
    ^NSEI.parquet          # Benchmark symbols use ^ prefix as-is
    ...
```

`CACHE_DIR` is resolved from the `CACHE_DIR` environment variable, falling back to `backend/data/`. This is consistent with the existing `pipeline_cache_file` path.

Filenames are derived by replacing characters invalid on common filesystems (`/`, `\`, `:`) with `_`.

---

## Interface

### `OHLCVCache` — New Module: `app/pipeline/ohlcv_cache.py`

#### `get(symbol, append_ns, period, force_refresh) → pd.DataFrame | None`

- Primary entry point. Encapsulates the freshness logic described above.
- `append_ns` controls whether `.NS` is appended when calling yfinance (mirrors the existing `fetch_stock_data` parameter).
- Returns a DataFrame with the same schema as `fetch_stock_data` currently returns, so callsites require no schema changes.
- Returns `None` if the fetch fails and no cached file exists.

#### `invalidate(symbol) → None`

- Deletes the Parquet file for a single symbol.

#### `invalidate_all() → None`

- Deletes all files in the `ohlcv/` cache directory.

#### `stats() → dict`

- Returns `{ "total_files": int, "total_size_mb": float, "oldest_file_date": str }` for observability.

---

## Integration Points

### Pipeline (`app/pipeline/orchestrator.py`)

- The Tier 1 bulk `yf.download` path remains unchanged — it is already batch-optimised and its result is short-lived within a single run.
- The per-symbol `fetch_stock_data` call in the **Scoring phase** (currently fetching 3y on every symbol) is replaced with `OHLCVCache.get(symbol, period="3y")`.
- The `hist_cache` dict (in-memory, run-scoped) is removed; its role is superseded by `OHLCVCache`.

### Backtest Engine (`app/backtest/engine.py`)

- `fetch_stock_data(symbol, period='3y')` inside `run_backtest` is replaced with `OHLCVCache.get(symbol, period="3y")`.
- The benchmark fetch (`^NSEI`) is also routed through `OHLCVCache` with `append_ns=False`.

### Fetcher (`app/pipeline/fetcher.py`)

- `fetch_stock_data` is retained as the underlying network call used by `OHLCVCache`. No public API changes.

---

## Concurrency and Safety

- The pipeline and backtest engine run in separate threads (FastAPI `BackgroundTasks`).
- File writes use **write-to-temp-then-rename** (atomic on POSIX). This prevents a concurrent reader from observing a partially written file.
- No inter-process locking is required because the rename operation is atomic and the worst outcome of a race is a redundant network fetch (the later writer wins, which is safe).
- The `OHLCVCache` module is stateless; no shared mutable state exists at the module level.

---

## Observability

- A log line at `INFO` level is emitted on every cache hit, miss, and incremental fetch, including the symbol, last cached date, and fetch latency.
- `GET /api/health` response is extended with an `ohlcv_cache` key populated by `OHLCVCache.stats()`.

---

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `CACHE_DIR` | `backend/data/` | Root directory for all file caches (existing variable) |
| `OHLCV_CACHE_MAX_AGE_HOURS` | `24` | If last row is older than this, force incremental fetch |

`OHLCV_CACHE_MAX_AGE_HOURS` defaults to 24 so that a pipeline run in the evening produces a warm cache that the next morning's backtest can use without any network calls.

---

## Expected Performance Impact

| Scenario | Before | After (warm cache) |
|---|---|---|
| Pipeline scoring phase (1,800 symbols) | ~60–70 min (full 3y fetch × 1,800) | ~2–4 min (Parquet read × 1,800 + incremental tail fetch) |
| Backtest run (all symbols, 3y) | ~45–60 min | ~3–5 min |
| First cold run (no cache files) | ~1.5 hours | ~1.5 hours (same, populates cache) |
| Benchmark fetch (`^NSEI`) | 1 full fetch per run | 1 read + 0–1 incremental fetch per day |

---

## Migration and Rollout

1. The cache directory is created automatically on first use if it does not exist.
2. The first pipeline run after deployment performs a full cold fetch for every symbol and populates the cache; subsequent runs benefit immediately.
3. No database schema changes are required.
4. The existing HTTP-level `requests_cache` (SQLite) remains in place and continues to deduplicate network calls within a single incremental fetch window.

---

## Out of Scope / Future Considerations

- Weekly / monthly OHLCV resampling could also be cached, but the current `resample_ohlcv` utility is fast enough (in-memory pandas) that it is not a bottleneck.
- A cache-warming background job (e.g. run at 6 AM before market open) could pre-populate incremental updates before the pipeline fires at 4 PM.
- Monitoring stale files (e.g. symbols delisted or suspended) can be addressed by adding a `last_successful_fetch` metadata sidecar file in a future iteration.
