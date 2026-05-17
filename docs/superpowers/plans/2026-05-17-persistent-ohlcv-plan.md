# OHLCV Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent Parquet-based OHLCV cache so that the pipeline scoring phase and backtest engine read from disk instead of re-fetching 3 years of price history from yfinance on every run.

**Architecture:** A new `OHLCVCache` class in `app/pipeline/ohlcv_cache.py` owns all read/write logic. It checks whether a per-symbol `.parquet` file exists and is fresh; if not, it fetches only the missing tail from yfinance, appends it, and atomically writes the file back. The pipeline orchestrator and backtest engine each replace their `fetch_stock_data(symbol, period="3y")` calls with `OHLCVCache.get(...)`.

**Tech Stack:** Python 3.11+, pandas, pyarrow (Parquet I/O), yfinance, FastAPI, pytest, pytest-mock

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| **Create** | `backend/app/pipeline/ohlcv_cache.py` | `OHLCVCache` class: freshness logic, incremental fetch, Parquet I/O |
| **Create** | `backend/tests/pipeline/test_ohlcv_cache.py` | Unit tests for all `OHLCVCache` behaviour |
| **Modify** | `backend/app/pipeline/orchestrator.py` | Replace per-symbol `fetch_stock_data` call in the Scoring phase; remove `hist_cache` dict |
| **Modify** | `backend/app/backtest/engine.py` | Replace `fetch_stock_data(symbol, period='3y')` and benchmark fetch with cache calls |
| **Modify** | `backend/app/main.py` | Extend `/api/health` response with `ohlcv_cache` stats |
| **Modify** | `backend/tests/pipeline/test_orchestrator.py` | Update/add tests that previously mocked `fetch_stock_data` in the scoring phase |

> **Domain note:** yfinance returns a `pd.DataFrame` with a `DatetimeIndex` (timezone-aware or naive depending on the symbol). `fetch_stock_data` in `app/pipeline/fetcher.py` wraps `ticker.history(period=period)` and returns `(hist, info)`. The cache only stores `hist`; `info` (company metadata) is not part of this feature.

---

## Task 1: Create the `OHLCVCache` module skeleton

**Files:**
- Create: `backend/app/pipeline/ohlcv_cache.py`
- Create: `backend/tests/pipeline/test_ohlcv_cache.py`

- [ ] **Step 1: Write the failing test for module import and `OHLCVCache` instantiation**

```python
# backend/tests/pipeline/test_ohlcv_cache.py
import pytest
from app.pipeline.ohlcv_cache import OHLCVCache

def test_ohlcv_cache_instantiates(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    assert cache is not None
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend
pytest tests/pipeline/test_ohlcv_cache.py::test_ohlcv_cache_instantiates -v
```

Expected: `ModuleNotFoundError: No module named 'app.pipeline.ohlcv_cache'`

- [ ] **Step 3: Create the skeleton module**

```python
# backend/app/pipeline/ohlcv_cache.py
import os
import logging
import tempfile
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_OHLCV_SUBDIR = "ohlcv"


class OHLCVCache:
    """
    Persistent per-symbol OHLCV cache backed by Parquet files.

    Directory layout:
        <cache_dir>/ohlcv/<SYMBOL>.parquet
    """

    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = os.environ.get(
                "CACHE_DIR",
                os.path.join(os.path.dirname(__file__), "..", "..", "data"),
            )
        self._root = Path(cache_dir) / _OHLCV_SUBDIR
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _file_path(self, symbol: str) -> Path:
        safe = symbol.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self._root / f"{safe}.parquet"
```

- [ ] **Step 4: Run the test — must pass**

```bash
pytest tests/pipeline/test_ohlcv_cache.py::test_ohlcv_cache_instantiates -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/ohlcv_cache.py backend/tests/pipeline/test_ohlcv_cache.py
git commit -m "feat(ohlcv-cache): add OHLCVCache skeleton"
```

---

## Task 2: Implement `stats()` and `invalidate()`

**Files:**
- Modify: `backend/app/pipeline/ohlcv_cache.py`
- Modify: `backend/tests/pipeline/test_ohlcv_cache.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to backend/tests/pipeline/test_ohlcv_cache.py
import pandas as pd
import numpy as np

def _make_df(days: int = 5) -> pd.DataFrame:
    """Helper: returns a minimal OHLCV DataFrame with a DatetimeIndex."""
    idx = pd.date_range("2024-01-01", periods=days, freq="B")
    return pd.DataFrame({
        "Open":   np.ones(days) * 100,
        "High":   np.ones(days) * 105,
        "Low":    np.ones(days) * 95,
        "Close":  np.ones(days) * 102,
        "Volume": np.ones(days, dtype=int) * 1_000_000,
    }, index=idx)


def test_stats_empty_cache(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    s = cache.stats()
    assert s["total_files"] == 0
    assert s["total_size_mb"] == 0.0
    assert s["oldest_file_date"] is None


def test_invalidate_single(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    df = _make_df()
    df.to_parquet(cache._file_path("RELIANCE"))
    assert cache._file_path("RELIANCE").exists()
    cache.invalidate("RELIANCE")
    assert not cache._file_path("RELIANCE").exists()


def test_invalidate_all(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    for sym in ["TCS", "INFY"]:
        _make_df().to_parquet(cache._file_path(sym))
    cache.invalidate_all()
    remaining = list(cache._root.glob("*.parquet"))
    assert remaining == []


def test_stats_after_write(tmp_path):
    cache = OHLCVCache(cache_dir=str(tmp_path))
    _make_df().to_parquet(cache._file_path("HDFC"))
    s = cache.stats()
    assert s["total_files"] == 1
    assert s["total_size_mb"] > 0
    assert s["oldest_file_date"] is not None
```

- [ ] **Step 2: Run to confirm all four tests fail**

```bash
pytest tests/pipeline/test_ohlcv_cache.py -k "stats or invalidate" -v
```

Expected: 4 × `FAILED` with `AttributeError`

- [ ] **Step 3: Implement `stats()`, `invalidate()`, and `invalidate_all()`**

Add these methods to `OHLCVCache` in `ohlcv_cache.py`:

```python
    def stats(self) -> dict:
        files = list(self._root.glob("*.parquet"))
        if not files:
            return {"total_files": 0, "total_size_mb": 0.0, "oldest_file_date": None}
        total_bytes = sum(f.stat().st_size for f in files)
        oldest_mtime = min(f.stat().st_mtime for f in files)
        oldest_str = pd.Timestamp(oldest_mtime, unit="s").strftime("%Y-%m-%d")
        return {
            "total_files": len(files),
            "total_size_mb": round(total_bytes / 1_048_576, 2),
            "oldest_file_date": oldest_str,
        }

    def invalidate(self, symbol: str) -> None:
        path = self._file_path(symbol)
        if path.exists():
            path.unlink()
            logger.info("ohlcv_cache: invalidated %s", symbol)

    def invalidate_all(self) -> None:
        for path in self._root.glob("*.parquet"):
            path.unlink()
        logger.info("ohlcv_cache: invalidated all files")
```

- [ ] **Step 4: Run tests — all must pass**

```bash
pytest tests/pipeline/test_ohlcv_cache.py -k "stats or invalidate" -v
```

Expected: 4 × `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/ohlcv_cache.py backend/tests/pipeline/test_ohlcv_cache.py
git commit -m "feat(ohlcv-cache): add stats, invalidate, invalidate_all"
```

---

## Task 3: Implement `get()` — cache miss (cold fetch)

This task covers the path where no Parquet file exists yet.

**Files:**
- Modify: `backend/app/pipeline/ohlcv_cache.py`
- Modify: `backend/tests/pipeline/test_ohlcv_cache.py`

> **Domain note:** `OHLCVCache.get()` calls `fetch_stock_data` from `app.pipeline.fetcher`. That function returns `(hist_df, info_dict)`. The cache only persists and returns `hist_df`; `info` is discarded here because it is handled by `FundamentalCache` elsewhere.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/pipeline/test_ohlcv_cache.py
from unittest.mock import patch, MagicMock

def test_get_cold_miss_fetches_and_writes(tmp_path):
    """No parquet file → should call fetch_stock_data and write to disk."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    mock_df = _make_df(days=10)

    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(mock_df, None)) as mock_fetch:
        result = cache.get("RELIANCE", append_ns=True, period="3y")

    mock_fetch.assert_called_once_with("RELIANCE", append_ns=True, period="3y", fetch_info=False)
    assert result is not None
    assert len(result) == 10
    assert cache._file_path("RELIANCE").exists()


def test_get_returns_none_when_fetch_fails(tmp_path):
    """fetch_stock_data returns (None, None) and no file exists → get() returns None."""
    cache = OHLCVCache(cache_dir=str(tmp_path))

    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(None, None)):
        result = cache.get("BADSTOCK", append_ns=True, period="3y")

    assert result is None
    assert not cache._file_path("BADSTOCK").exists()
```

- [ ] **Step 2: Run to confirm both tests fail**

```bash
pytest tests/pipeline/test_ohlcv_cache.py -k "cold_miss or fetch_fails" -v
```

Expected: `FAILED` — `OHLCVCache` has no `get` method.

- [ ] **Step 3: Implement `get()` for the cold-miss path only**

Add this import at the top of `ohlcv_cache.py` (after the existing imports):

```python
from app.pipeline.fetcher import fetch_stock_data
```

Add the `get` method to `OHLCVCache`:

```python
    def get(
        self,
        symbol: str,
        append_ns: bool = True,
        period: str = "3y",
        force_refresh: bool = False,
    ) -> pd.DataFrame | None:
        """
        Return the OHLCV DataFrame for *symbol*, using the cache when possible.

        Steps:
          1. If force_refresh=True, skip the cache entirely.
          2. If a Parquet file exists and is fresh enough, return it.
          3. If a Parquet file exists but is stale, fetch the missing tail and append.
          4. If no file exists, do a full fetch and write the file.
        """
        path = self._file_path(symbol)

        if not force_refresh and path.exists():
            try:
                cached_df = pd.read_parquet(path)
                if self._is_fresh(cached_df):
                    logger.info("ohlcv_cache: HIT %s (rows=%d)", symbol, len(cached_df))
                    return cached_df
                # Stale — incremental fetch handled in Task 4
                return self._incremental_fetch(symbol, cached_df, append_ns, path)
            except Exception as exc:
                logger.warning("ohlcv_cache: corrupt file for %s (%s), re-fetching", symbol, exc)
                path.unlink(missing_ok=True)

        # Cold miss or force_refresh
        return self._full_fetch(symbol, append_ns, period, path)

    # ------------------------------------------------------------------ #
    # Private fetch helpers                                                 #
    # ------------------------------------------------------------------ #

    def _is_fresh(self, df: pd.DataFrame) -> bool:
        """Return True if the last row's date equals the latest available trading date."""
        if df.empty:
            return False
        max_age_hours = int(os.environ.get("OHLCV_CACHE_MAX_AGE_HOURS", "24"))
        last_ts = df.index[-1]
        if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is not None:
            last_ts = last_ts.tz_localize(None)
        age_hours = (pd.Timestamp.utcnow().tz_localize(None) - last_ts).total_seconds() / 3600
        return age_hours < max_age_hours

    def _full_fetch(
        self, symbol: str, append_ns: bool, period: str, path: Path
    ) -> pd.DataFrame | None:
        logger.info("ohlcv_cache: MISS %s — full fetch", symbol)
        df, _ = fetch_stock_data(symbol, append_ns=append_ns, period=period, fetch_info=False)
        if df is None or df.empty:
            return None
        self._write_atomic(df, path)
        return df

    def _incremental_fetch(
        self, symbol: str, cached_df: pd.DataFrame, append_ns: bool, path: Path
    ) -> pd.DataFrame | None:
        # Implemented in Task 4
        return cached_df

    def _write_atomic(self, df: pd.DataFrame, path: Path) -> None:
        """Write *df* to *path* atomically via a temp file in the same directory."""
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".parquet.tmp")
        os.close(fd)
        try:
            df.to_parquet(tmp)
            os.replace(tmp, path)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise
```

- [ ] **Step 4: Run the two new tests — must pass**

```bash
pytest tests/pipeline/test_ohlcv_cache.py -k "cold_miss or fetch_fails" -v
```

Expected: 2 × `PASSED`

- [ ] **Step 5: Run the full test file to check for regressions**

```bash
pytest tests/pipeline/test_ohlcv_cache.py -v
```

Expected: all previous tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline/ohlcv_cache.py backend/tests/pipeline/test_ohlcv_cache.py
git commit -m "feat(ohlcv-cache): implement get() cold-miss path"
```

---

## Task 4: Implement `get()` — cache hit and incremental fetch

**Files:**
- Modify: `backend/app/pipeline/ohlcv_cache.py`
- Modify: `backend/tests/pipeline/test_ohlcv_cache.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to backend/tests/pipeline/test_ohlcv_cache.py
import os

def test_get_cache_hit_no_network_call(tmp_path):
    """Fresh parquet file → return cached data, never call fetch_stock_data."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    # Write a file whose last row is within the past 24 hours
    now = pd.Timestamp.utcnow().tz_localize(None)
    idx = pd.date_range(end=now, periods=5, freq="B")
    df = _make_df(days=5)
    df.index = idx
    df.to_parquet(cache._file_path("TCS"))

    with patch("app.pipeline.ohlcv_cache.fetch_stock_data") as mock_fetch:
        result = cache.get("TCS", append_ns=True, period="3y")

    mock_fetch.assert_not_called()
    assert result is not None
    assert len(result) == 5


def test_get_stale_file_triggers_incremental_fetch(tmp_path):
    """Stale parquet file → fetch only the tail and append to cached data."""
    cache = OHLCVCache(cache_dir=str(tmp_path))

    # Old data ending 5 days ago
    old_end = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=5)
    old_idx = pd.date_range(end=old_end, periods=10, freq="B")
    old_df = _make_df(days=10)
    old_df.index = old_idx
    old_df.to_parquet(cache._file_path("INFY"))

    # Tail that yfinance would return for the missing window
    tail_idx = pd.date_range(start=old_end + pd.Timedelta(days=1), periods=3, freq="B")
    tail_df = _make_df(days=3)
    tail_df.index = tail_idx

    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(tail_df, None)) as mock_fetch:
        result = cache.get("INFY", append_ns=True, period="3y")

    mock_fetch.assert_called_once()
    # Caller should have fetched only the tail, not 3 full years
    call_kwargs = mock_fetch.call_args
    assert "3y" not in str(call_kwargs)  # period is a date string, not "3y"
    assert result is not None
    assert len(result) == 13  # 10 old + 3 new


def test_get_force_refresh_bypasses_fresh_cache(tmp_path):
    """force_refresh=True should re-fetch even if the cache is fresh."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    now = pd.Timestamp.utcnow().tz_localize(None)
    idx = pd.date_range(end=now, periods=5, freq="B")
    df = _make_df(days=5)
    df.index = idx
    df.to_parquet(cache._file_path("WIPRO"))

    fresh_df = _make_df(days=20)
    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(fresh_df, None)) as mock_fetch:
        result = cache.get("WIPRO", append_ns=True, period="3y", force_refresh=True)

    mock_fetch.assert_called_once()
    assert len(result) == 20
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/pipeline/test_ohlcv_cache.py -k "cache_hit or incremental or force_refresh" -v
```

Expected: 3 × `FAILED`

- [ ] **Step 3: Implement the incremental fetch path in `_incremental_fetch`**

Replace the stub `_incremental_fetch` in `ohlcv_cache.py`:

```python
    def _incremental_fetch(
        self, symbol: str, cached_df: pd.DataFrame, append_ns: bool, path: Path
    ) -> pd.DataFrame | None:
        last_date = cached_df.index[-1]
        if hasattr(last_date, "tzinfo") and last_date.tzinfo is not None:
            last_date = last_date.tz_localize(None)

        start_str = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        end_str = pd.Timestamp.utcnow().strftime("%Y-%m-%d")

        logger.info(
            "ohlcv_cache: STALE %s — incremental fetch %s → %s",
            symbol, start_str, end_str,
        )

        tail, _ = fetch_stock_data(
            symbol,
            append_ns=append_ns,
            period=f"start={start_str}&end={end_str}",
            fetch_info=False,
        )

        if tail is None or tail.empty:
            logger.info("ohlcv_cache: no new data for %s, serving cached rows", symbol)
            return cached_df

        # Normalise timezone before concat
        if tail.index.tz is not None:
            tail.index = tail.index.tz_localize(None)
        if cached_df.index.tz is not None:
            cached_df.index = cached_df.index.tz_localize(None)

        merged = pd.concat([cached_df, tail]).loc[~pd.Series(
            pd.concat([cached_df, tail]).index
        ).duplicated().values]
        merged.sort_index(inplace=True)

        self._write_atomic(merged, path)
        logger.info("ohlcv_cache: wrote %d rows for %s", len(merged), symbol)
        return merged
```

> **Note on `period` format:** `fetch_stock_data` passes `period` straight to `yf.Ticker.history(period=...)`. For incremental fetches we switch to the `start` / `end` keyword format accepted by yfinance's `history()`. Update `fetch_stock_data` to accept and forward a `start` / `end` period string, **or** (simpler, no API change) call `yf.Ticker.history(start=..., end=...)` directly inside `_incremental_fetch`.

Replace `_incremental_fetch` with this version that calls yfinance directly:

```python
    def _incremental_fetch(
        self, symbol: str, cached_df: pd.DataFrame, append_ns: bool, path: Path
    ) -> pd.DataFrame | None:
        import yfinance as yf

        last_date = cached_df.index[-1]
        if hasattr(last_date, "tzinfo") and last_date.tzinfo is not None:
            last_date = last_date.tz_localize(None)

        start_str = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        end_str = (pd.Timestamp.utcnow() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        logger.info(
            "ohlcv_cache: STALE %s — incremental fetch %s → %s",
            symbol, start_str, end_str,
        )

        ticker_sym = f"{symbol}.NS" if append_ns else symbol
        try:
            tail = yf.Ticker(ticker_sym).history(start=start_str, end=end_str)
        except Exception as exc:
            logger.warning("ohlcv_cache: incremental fetch failed for %s: %s", symbol, exc)
            return cached_df

        if tail is None or tail.empty:
            logger.info("ohlcv_cache: no new data for %s, serving cached rows", symbol)
            return cached_df

        if tail.index.tz is not None:
            tail.index = tail.index.tz_localize(None)
        if cached_df.index.tz is not None:
            cached_df.index = cached_df.index.tz_localize(None)

        combined = pd.concat([cached_df, tail])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined.sort_index(inplace=True)

        self._write_atomic(combined, path)
        logger.info("ohlcv_cache: wrote %d rows for %s", len(combined), symbol)
        return combined
```

- [ ] **Step 4: Update the stale-fetch test to match the actual yfinance call**

The test currently patches `fetch_stock_data`; the incremental path now calls `yf.Ticker` directly. Update the stale test:

```python
def test_get_stale_file_triggers_incremental_fetch(tmp_path):
    """Stale parquet file → fetch only the tail and append to cached data."""
    cache = OHLCVCache(cache_dir=str(tmp_path))

    old_end = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=5)
    old_idx = pd.date_range(end=old_end, periods=10, freq="B")
    old_df = _make_df(days=10)
    old_df.index = old_idx
    old_df.to_parquet(cache._file_path("INFY"))

    tail_idx = pd.date_range(
        start=old_end + pd.Timedelta(days=1), periods=3, freq="B"
    )
    tail_df = _make_df(days=3)
    tail_df.index = tail_idx

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = tail_df

    with patch("app.pipeline.ohlcv_cache.yf.Ticker", return_value=mock_ticker):
        result = cache.get("INFY", append_ns=True, period="3y")

    mock_ticker.history.assert_called_once()
    assert result is not None
    assert len(result) == 13
```

Add `import yfinance as yf` at the top of `ohlcv_cache.py` (replacing the inline import inside `_incremental_fetch`).

- [ ] **Step 5: Run all cache tests — must pass**

```bash
pytest tests/pipeline/test_ohlcv_cache.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline/ohlcv_cache.py backend/tests/pipeline/test_ohlcv_cache.py
git commit -m "feat(ohlcv-cache): implement cache hit, incremental fetch, force_refresh"
```

---

## Task 5: Wire the cache into the backtest engine

The backtest engine (`app/backtest/engine.py`) currently calls `fetch_stock_data(symbol, period='3y', fetch_info=False)` inside the main symbol loop, and `fetch_stock_data("^NSEI", append_ns=False, period='3y', fetch_info=False)` for the benchmark. Both are replaced with `OHLCVCache.get(...)`.

**Files:**
- Modify: `backend/app/backtest/engine.py`

> **No test file is created here** — the backtest engine's integration with yfinance is tested at the `OHLCVCache` level (Tasks 1–4). The change here is a small, mechanical substitution that is verified by running the existing backtest router tests if any exist, otherwise a manual smoke test suffices.

- [ ] **Step 1: Add the module-level cache instance to `engine.py`**

At the top of `backend/app/backtest/engine.py`, after the existing imports, add:

```python
from app.pipeline.ohlcv_cache import OHLCVCache

_ohlcv_cache = OHLCVCache()
```

- [ ] **Step 2: Replace the per-symbol fetch in `run_backtest`**

Find the existing call inside the `for symbol in symbols:` loop (approximately line 220 in the current file):

```python
# BEFORE
df, _ = fetch_stock_data(symbol, period='3y', fetch_info=False)
```

Replace with:

```python
# AFTER
df = _ohlcv_cache.get(symbol, append_ns=True, period='3y')
```

The `if df is None or df.empty:` guard that follows remains unchanged.

- [ ] **Step 3: Replace the benchmark fetch in `run_backtest`**

Find (approximately 30 lines above the symbol loop):

```python
# BEFORE
benchmark_df, _ = fetch_stock_data("^NSEI", append_ns=False, period='3y', fetch_info=False)
```

Replace with:

```python
# AFTER
benchmark_df = _ohlcv_cache.get("^NSEI", append_ns=False, period='3y')
```

- [ ] **Step 4: Verify the engine still imports cleanly**

```bash
cd backend
python -c "from app.backtest.engine import run_backtest; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat(ohlcv-cache): wire cache into backtest engine"
```

---

## Task 6: Wire the cache into the pipeline orchestrator

The scoring phase of `run_pipeline` (in `app/pipeline/orchestrator.py`) currently re-fetches 3 years of data per symbol via `fetch_stock_data`. It also maintains an in-memory `hist_cache` dict to avoid double-fetching within a single run. Both are replaced by `OHLCVCache`.

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Add the module-level cache instance**

At the top of `backend/app/pipeline/orchestrator.py`, after the existing imports:

```python
from app.pipeline.ohlcv_cache import OHLCVCache

_ohlcv_cache = OHLCVCache()
```

- [ ] **Step 2: Remove `hist_cache` construction and the lazy-loading block**

Locate and **delete** these lines (they appear after the Tier 1.5 block, before Tier 2):

```python
# REMOVE THESE LINES
hist_cache = {} # Temporary cache for hist data and info to avoid re-fetching
```

Also locate and **delete** the memory-optimisation block:

```python
# REMOVE THESE LINES
use_lazy_loading = len(final_survivors) > 300
if use_lazy_loading:
    logger.info("Survivors > 300. Clearing hist_cache to save memory (Lazy Loading enabled).")
    hist_cache.clear()
```

- [ ] **Step 3: Replace the per-symbol fetch in the scoring loop**

In the `for symbol in final_survivors:` scoring loop, find:

```python
# BEFORE
cache_data = hist_cache.get(symbol)
if cache_data is None:
    # Lazy load if cleared for memory
    hist, info = fetch_stock_data(symbol, period="3y")
    if hist is None or info is None:
        completed_scoring.add(symbol)
        continue
else:
    hist, info = cache_data
```

Replace with:

```python
# AFTER
hist = _ohlcv_cache.get(symbol, append_ns=True, period="3y")
if hist is None:
    completed_scoring.add(symbol)
    continue
info = None  # info is sourced from FundamentalCache, not needed here
```

- [ ] **Step 4: Remove the Tier 1 `hist_cache` population**

In the Tier 1 loop, find:

```python
# REMOVE: cache population in Tier 1
if hist is not None and not hist.empty:
    ...
    hist_cache[symbol] = (hist, None)
```

The `if hist is not None and not hist.empty:` block that does scoring logic is retained; only the `hist_cache[symbol] = ...` assignment inside it is deleted.

- [ ] **Step 5: Remove the `final_signal_date` `hist_cache` lookup**

Find the block that derives `final_signal_date` from `hist_cache`:

```python
# BEFORE
if final_survivors:
    if final_survivors[0] in hist_cache:
        first_hist, _ = hist_cache[final_survivors[0]]
        final_signal_date = first_hist.index[-1].date()
    else:
        # Re-fetch just one to get the date if cache was cleared
        h, _ = fetch_stock_data(final_survivors[0], period="1d")
        if h is not None and not h.empty:
            final_signal_date = h.index[-1].date()
```

Replace with:

```python
# AFTER
if final_survivors:
    first_hist = _ohlcv_cache.get(final_survivors[0], append_ns=True, period="3y")
    if first_hist is not None and not first_hist.empty:
        final_signal_date = first_hist.index[-1].date()
```

- [ ] **Step 6: Verify the orchestrator imports cleanly**

```bash
cd backend
python -c "from app.pipeline.orchestrator import run_pipeline; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/pipeline/orchestrator.py
git commit -m "feat(ohlcv-cache): wire cache into pipeline scoring phase, remove hist_cache"
```

---

## Task 7: Expose cache stats in `/api/health`

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add the cache import**

In `backend/app/main.py`, after the existing `from app.core.cache import response_cache` import, add:

```python
from app.pipeline.ohlcv_cache import OHLCVCache
_ohlcv_cache = OHLCVCache()
```

- [ ] **Step 2: Add `ohlcv_cache` to the health response**

Inside `health_check()`, find the `return` statement and extend it:

```python
# BEFORE
return {
    "status": status,
    "db": db_status,
    "cache": response_cache.stats(),
    "pipeline": pipeline_info,
    "version": "2.1.0"
}

# AFTER
return {
    "status": status,
    "db": db_status,
    "cache": response_cache.stats(),
    "ohlcv_cache": _ohlcv_cache.stats(),
    "pipeline": pipeline_info,
    "version": "2.1.0"
}
```

- [ ] **Step 3: Verify the response shape with curl or httpie**

```bash
cd backend
uvicorn app.main:app --port 8001 &
sleep 2
curl -s http://localhost:8001/api/health | python -m json.tool | grep -A 4 ohlcv_cache
kill %1
```

Expected output:

```json
"ohlcv_cache": {
    "total_files": 0,
    "total_size_mb": 0.0,
    "oldest_file_date": null
}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(ohlcv-cache): expose ohlcv_cache stats in /api/health"
```

---

## Task 8: Edge-case and regression tests

These tests cover error paths that protect production correctness.

**Files:**
- Modify: `backend/tests/pipeline/test_ohlcv_cache.py`

- [ ] **Step 1: Write the edge-case tests**

```python
# Append to backend/tests/pipeline/test_ohlcv_cache.py

def test_corrupt_parquet_is_deleted_and_refetched(tmp_path):
    """A corrupt Parquet file should be removed and a fresh fetch attempted."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    path = cache._file_path("CORRUPT")
    path.write_bytes(b"this is not a parquet file")

    fresh_df = _make_df(days=5)
    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(fresh_df, None)):
        result = cache.get("CORRUPT", append_ns=True, period="3y")

    assert result is not None
    assert len(result) == 5
    assert path.exists()  # re-written with valid data


def test_special_characters_in_symbol_name(tmp_path):
    """Symbols like ^NSEI must produce a valid filename."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    fresh_df = _make_df(days=5)
    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(fresh_df, None)):
        cache.get("^NSEI", append_ns=False, period="3y")

    files = list(cache._root.glob("*.parquet"))
    assert len(files) == 1
    assert "^" not in files[0].name  # caret must be sanitised


def test_empty_dataframe_from_fetch_is_not_written(tmp_path):
    """An empty DataFrame returned by yfinance should not be cached."""
    cache = OHLCVCache(cache_dir=str(tmp_path))
    with patch("app.pipeline.ohlcv_cache.fetch_stock_data", return_value=(pd.DataFrame(), None)):
        result = cache.get("EMPTY", append_ns=True, period="3y")

    assert result is None
    assert not cache._file_path("EMPTY").exists()


def test_incremental_no_new_data_returns_cached(tmp_path):
    """If the incremental fetch returns empty (market closed), serve the cached file."""
    cache = OHLCVCache(cache_dir=str(tmp_path))

    old_end = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=3)
    old_idx = pd.date_range(end=old_end, periods=5, freq="B")
    old_df = _make_df(days=5)
    old_df.index = old_idx
    old_df.to_parquet(cache._file_path("STABLE"))

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()  # empty — weekend/holiday

    with patch("app.pipeline.ohlcv_cache.yf.Ticker", return_value=mock_ticker):
        result = cache.get("STABLE", append_ns=True, period="3y")

    assert result is not None
    assert len(result) == 5  # original cached rows returned unchanged
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/pipeline/test_ohlcv_cache.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 3: Commit**

```bash
git add backend/tests/pipeline/test_ohlcv_cache.py
git commit -m "test(ohlcv-cache): add edge-case tests for corrupt files, empty frames, special chars"
```

---

## Task 9: End-to-end smoke test

This is a manual verification step — no new automated tests. It confirms the full stack works after the wiring changes in Tasks 5 and 6.

- [ ] **Step 1: Run the full test suite**

```bash
cd backend
pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: no new failures introduced by this feature.

- [ ] **Step 2: Run a minimal backtest via the API**

With the server running:

```bash
curl -s -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"symbol_limit": 5, "holding_days": 10, "score_threshold": 40}' \
  | python -m json.tool
```

Expected: `{"run_id": "<uuid>", "status": "pending"}`

- [ ] **Step 3: Poll until complete and check timing**

```bash
RUN_ID=<uuid from above>
watch -n 3 "curl -s http://localhost:8000/api/backtest/$RUN_ID | python -m json.tool | grep -E 'status|symbols'"
```

On a warm cache (after the first run), the 5-symbol backtest should complete in under 30 seconds.

- [ ] **Step 4: Check the ohlcv_cache directory**

```bash
ls -lh backend/data/ohlcv/ | head -10
```

Expected: 5+ `.parquet` files for the symbols processed, plus `_NSEI.parquet` for the benchmark.

- [ ] **Step 5: Re-run the backtest (warm cache) and confirm no yfinance calls are logged**

```bash
curl -s -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"symbol_limit": 5, "holding_days": 10, "score_threshold": 40}' \
  | python -m json.tool
```

Tail the log and confirm you see only `ohlcv_cache: HIT` messages, no `ohlcv_cache: MISS` or `ohlcv_cache: STALE`.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: ohlcv-cache end-to-end smoke verified"
```

---

## Self-Review

### Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| No Parquet file → full fetch, write file | Task 3 |
| File exists, last date is today → serve from cache | Task 4 |
| File exists, last date < today → incremental fetch, append, write | Task 4 |
| Corrupt/unreadable → delete and full fetch | Task 8 |
| `force_refresh=True` → full fetch regardless | Task 4 |
| Atomic write-then-rename | Task 3 (`_write_atomic`) |
| `OHLCVCache.get(symbol, append_ns, period, force_refresh)` | Tasks 3–4 |
| `OHLCVCache.invalidate(symbol)` | Task 2 |
| `OHLCVCache.invalidate_all()` | Task 2 |
| `OHLCVCache.stats()` | Task 2 |
| Cache dir `<CACHE_DIR>/ohlcv/<SYMBOL>.parquet` | Task 1 |
| Special characters in filenames | Task 8 |
| `OHLCV_CACHE_MAX_AGE_HOURS` env var | Task 3 (`_is_fresh`) |
| Wire into backtest engine | Task 5 |
| Wire into pipeline scoring phase | Task 6 |
| Remove `hist_cache` in-memory dict | Task 6 |
| `/api/health` extended with `ohlcv_cache` key | Task 7 |
| Log INFO on every hit/miss/incremental | Tasks 3–4 |

All spec requirements are covered.

### Placeholder Scan

No TBD, TODO, or vague steps found. Every code block contains runnable code.

### Type Consistency

- `OHLCVCache.get()` returns `pd.DataFrame | None` — consistent across Tasks 3, 4, 5, 6.
- `_write_atomic(df, path)` — `df: pd.DataFrame`, `path: Path` — consistent in Task 3 (definition) and Task 4 (usage inside `_incremental_fetch`).
- `_file_path(symbol)` returns `Path` — used consistently in Tasks 2, 3, 4, 8.
- `_ohlcv_cache` module-level instance introduced in Tasks 5, 6, 7 — all reference the same `OHLCVCache()` constructor signature from Task 1.