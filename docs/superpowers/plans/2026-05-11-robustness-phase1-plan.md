# Robustness Improvements Phase 1: API Performance & Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement in-process TTL caching for all high-traffic API endpoints and surface data freshness to the frontend.

**Architecture:** A generic thread-safe `ResponseCache` dictionary will wrap router endpoints, supplemented by a specific `ScreenCache` for materialized screens. The frontend will display a StaleBanner when data exceeds 26 hours of age based on pipeline completion timestamps.

**Tech Stack:** Python, FastAPI, React.

---

### Task 1: Core Response Cache

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/cache.py`
- Create: `backend/tests/unit/test_core_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_core_cache.py
import time
from app.core.cache import ResponseCache

def test_response_cache_basic_operations():
    cache = ResponseCache()
    # Initial get
    val, hit = cache.get("test_key")
    assert hit is False
    assert val is None
    
    # Set and get
    cache.set("test_key", {"data": 123}, 1) # 1 second TTL
    val, hit = cache.get("test_key")
    assert hit is True
    assert val == {"data": 123}
    
    # Expiration
    time.sleep(1.1)
    val, hit = cache.get("test_key")
    assert hit is False
    
    # Invalidation
    cache.set("key2", 456, 10)
    cache.invalidate("key2")
    _, hit = cache.get("key2")
    assert hit is False
    
    # Stats
    cache.set("key3", 789, 10)
    stats = cache.stats()
    assert stats["keys"] == 1
    assert stats["hits"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_core_cache.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.core.cache'"

- [ ] **Step 3: Create `__init__.py`**

Run: `touch backend/app/core/__init__.py`

- [ ] **Step 4: Write minimal implementation**

```python
# backend/app/core/cache.py
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
        if key not in self._store:
            self._misses += 1
            return None, False
            
        value, expires_at = self._store[key]
        if time.time() > expires_at:
            del self._store[key]
            self._misses += 1
            return None, False
            
        self._hits += 1
        return value, True
    
    def set(self, key: str, value: Any, ttl: int) -> None:
        self._store[key] = (value, time.time() + ttl)
    
    def invalidate(self, key: str | None = None) -> None:
        """key=None clears everything."""
        if key is None:
            self._store.clear()
        elif key in self._store:
            del self._store[key]
    
    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses, "keys": len(self._store)}

response_cache = ResponseCache()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_core_cache.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core backend/tests/unit/test_core_cache.py
git commit -m "feat: implement in-process ResponseCache"
```

---

### Task 2: Screen Cache implementation

**Files:**
- Create: `backend/app/screens/cache.py`
- Modify: `backend/app/screens/materializer.py`
- Test: `backend/tests/unit/test_screen_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_screen_cache.py
from app.screens.cache import ScreenCache

def test_screen_cache():
    cache = ScreenCache()
    cache.invalidate() # clean start
    
    val = cache.get("screen:momentum:False")
    assert val is None
    
    cache.set("screen:momentum:False", [{"symbol": "RELIANCE"}], 300)
    val = cache.get("screen:momentum:False")
    assert val == [{"symbol": "RELIANCE"}]
    
    cache.invalidate()
    assert cache.get("screen:momentum:False") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_screen_cache.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/screens/cache.py
from app.core.cache import ResponseCache

# We use a dedicated ResponseCache instance for screens
_screen_cache_store = ResponseCache()

class ScreenCache:
    def get(self, key: str) -> list[dict] | None:
        val, hit = _screen_cache_store.get(key)
        return val if hit else None

    def set(self, key: str, value: list[dict], ttl_seconds: int) -> None:
        _screen_cache_store.set(key, value, ttl_seconds)

    def invalidate(self, slug: str | None = None) -> None:
        if slug is None:
            _screen_cache_store.invalidate()
        else:
            _screen_cache_store.invalidate(f"screen:{slug}:False")
            _screen_cache_store.invalidate(f"screen:{slug}:True")

    def stats(self) -> dict:
        return _screen_cache_store.stats()

screen_cache = ScreenCache()
```

- [ ] **Step 4: Update Materializer**

```python
# In backend/app/screens/materializer.py, add the import at top:
from app.screens.cache import screen_cache

# At the end of `materialize_all_screens(db: Session)` function, add:
    screen_cache.invalidate()
```

- [ ] **Step 5: Run tests**

Run: `pytest backend/tests/unit/test_screen_cache.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/screens/cache.py backend/tests/unit/test_screen_cache.py backend/app/screens/materializer.py
git commit -m "feat: implement ScreenCache and invalidate on materialization"
```

---

### Task 3: API Endpoints Caching

**Files:**
- Modify: `backend/app/routers/screens.py`
- Modify: `backend/app/routers/dashboard.py`

- [ ] **Step 1: Implement caching in screens router**

Modify `backend/app/routers/screens.py`:
```python
# Add imports
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from app.screens.cache import screen_cache

# Add cache clear endpoint before get_screen_results
@router.post("/cache/clear")
def clear_screen_cache():
    screen_cache.invalidate()
    return {"status": "cleared"}

# Modify get_screen_results
@router.get("/{slug}")
def get_screen_results(
    slug: str, 
    response: Response,
    live: bool = Query(False),
    db: Session = Depends(get_db)
):
    if slug not in SCREEN_REGISTRY:
        raise HTTPException(status_code=404, detail="Screen not found")
        
    cache_key = f"screen:{slug}:{live}"
    cached_val = screen_cache.get(cache_key)
    if cached_val is not None:
        response.headers["X-Cache"] = "HIT"
        # X-Cache-Age omitted for simplicity in basic implementation
        return cached_val
        
    response.headers["X-Cache"] = "MISS"
    
    # ... KEEP ALL EXISTING DB AND LIVE EXECUTION LOGIC HERE ...
    # Assume results variable contains the final list
    # ...
    
    ttl = 60 if live else 900
    screen_cache.set(cache_key, results, ttl)
    return results 
```
IMPORTANT: The `results` list must be populated via the existing logic before the cache
write. Place `screen_cache.set(cache_key, results, ttl)` as the LAST statement before
`return results`, after BOTH the DB-lookup path and the live-execution fallback path have
had a chance to populate `results`. The cache read (early return) must be placed BEFORE
the `if not live:` branch so it short-circuits both paths.

The correct structure is:
```python
@router.get("/{slug}")
def get_screen_results(slug, response, live, db):
    # 1. Cache check — must come first
    cached_val = screen_cache.get(cache_key)
    if cached_val is not None:
        response.headers["X-Cache"] = "HIT"
        return cached_val
    response.headers["X-Cache"] = "MISS"
    results = []

    # 2. DB lookup path (existing code, populates results)
    if not live:
        ...

    # 3. Live fallback path (existing code, populates results)
    # (runs only if DB returned nothing OR live=True)
    if live or not results:
        ...

    # 4. Cache write — after both paths
    screen_cache.set(cache_key, results, 60 if live else 900)
    return results
```

- [ ] **Step 2: Add inline caching to dashboard router endpoints**

Do NOT implement the `cached` decorator. FastAPI's dependency injection is incompatible
with generic async wrappers. Instead, apply the cache inline in each function body.

Modify `backend/app/routers/dashboard.py`:

1. Add import at top:
```python
   from app.core.cache import response_cache
```

2. Modify `get_live_market` (no Depends, safe to wrap simply):
```python
   @router.get("/market/live")
   def get_live_market():
       val, hit = response_cache.get("market_live")
       if hit:
           return {"market_context": val}
       data = get_live_market_data()
       response_cache.set("market_live", data, 60)
       return {"market_context": data}
```

3. Modify `get_dashboard_results` — cache the final sorted list, NOT intermediate
   query results (caching SQLAlchemy ORM objects will fail on serialization):
```python
   @router.get("/screener/results")
   def get_dashboard_results(db: Session = Depends(get_db)):
       val, hit = response_cache.get("screener_results")
       if hit:
           return val
       # ... ALL EXISTING QUERY AND GROUPING LOGIC UNCHANGED ...
       final_results.sort(...)
       response_cache.set("screener_results", final_results, 600)
       return final_results
```

4. Modify `get_pipeline_status` with inline cache (TTL 30s):
```python
   @router.get("/pipeline/latest")
   def get_pipeline_status(db: Session = Depends(get_db)):
       val, hit = response_cache.get("pipeline_latest")
       if hit:
           return val
       # ... EXISTING LOGIC ...
       response_cache.set("pipeline_latest", result, 30)
       return result
```

IMPORTANT: Remove the `cached` decorator definition entirely. It should not exist in the file.

- [ ] **Step 3: Invalidate response cache on pipeline completion**

Modify `backend/app/pipeline/orchestrator.py`:

1. Add import at top:
```python
   from app.core.cache import response_cache
```

2. At the point where `run.status = "complete"` is set (near the bottom of `run_pipeline`),
   add the invalidation call immediately before the final `db.commit()`:
```python
   run.status = "complete"
   run.stocks_fetched = fetched_count
   run.stocks_scored = scored_count
   response_cache.invalidate()   # clear all cached API responses
   db.commit()
```

This ensures the next `GET /screener/results` or `GET /pipeline/latest` call hits the DB
and reflects the fresh pipeline output.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/screens.py backend/app/routers/dashboard.py
git commit -m "feat: apply response caching to dashboard and screens endpoints"
```

---

### Task 4: Frontend Data Freshness API & UI

**Files:**
- Modify: `backend/app/routers/dashboard.py`
- Modify: `frontend/src/hooks/usePipeline.js` (assuming it exists, otherwise adapt)
- Create: `frontend/src/components/StaleBanner.jsx`
- Create: `frontend/src/components/StaleBanner.css`

- [ ] **Step 1: Update API Response**

Modify `get_pipeline_status` in `backend/app/routers/dashboard.py`:
```python
import datetime

@router.get("/pipeline/latest")
def get_pipeline_status(db: Session = Depends(get_db)):
    val, hit = response_cache.get("pipeline_latest")
    if hit: return val

    run = db.query(PipelineRun).order_by(PipelineRun.timestamp.desc()).first()
    if not run:
        return {"status": "never_run", "market_context": []}
        
    market = db.query(MarketSnapshot).filter(MarketSnapshot.date == run.timestamp.date()).all()
    
    # Calculate age
    age_delta = datetime.datetime.utcnow() - run.timestamp
    data_age_hours = age_delta.total_seconds() / 3600.0
    is_stale = data_age_hours > 26
    
    result = {
        "status": run.status,
        "scored_at": run.timestamp,
        "data_age_hours": round(data_age_hours, 1),
        "is_stale": is_stale,
        "stocks_fetched": run.stocks_fetched,
        "tier1_count": run.tier1_count,
        "tier2_count": run.tier2_count,
        "stocks_scored": run.stocks_scored,
        "market_context": [
            {"symbol": m.symbol, "close": m.close, "change_pct": m.change_pct} 
            for m in market
        ]
    }
    response_cache.set("pipeline_latest", result, 30)
    return result
```

- [ ] **Step 2: Create StaleBanner Component**

```jsx
// frontend/src/components/StaleBanner.jsx
import React from 'react';
import './StaleBanner.css';

export default function StaleBanner({ lastUpdated, dataAgeHours, onRunPipeline }) {
    if (!lastUpdated) return null;
    
    const dateStr = new Date(lastUpdated).toLocaleString();
    
    return (
        <div className="stale-banner">
            <span className="stale-icon">⚠️</span>
            <div className="stale-content">
                <strong>Data is {dataAgeHours} hours old.</strong> Last pipeline run: {dateStr}. 
            </div>
            {onRunPipeline && (
                <button className="stale-run-btn" onClick={onRunPipeline}>
                    Run Pipeline
                </button>
            )}
        </div>
    );
}
```

```css
/* frontend/src/components/StaleBanner.css */
/* frontend/src/components/StaleBanner.css */
.stale-banner {
    display: flex;
    align-items: center;
    gap: 12px;
    background-color: color-mix(in srgb, var(--color-warning, #f59e0b) 12%, var(--color-bg-secondary));
    color: var(--color-text);
    border: 1px solid color-mix(in srgb, var(--color-warning, #f59e0b) 40%, transparent);
    padding: 12px 16px;
    border-radius: var(--radius-md, 8px);
    margin-bottom: 16px;
}
.stale-icon { flex-shrink: 0; }
.stale-content { flex: 1; font-size: 0.875rem; }
.stale-run-btn {
    flex-shrink: 0;
    background-color: var(--color-warning, #f59e0b);
    color: #000;
    border: none;
    padding: 6px 14px;
    border-radius: var(--radius-sm, 4px);
    cursor: pointer;
    font-weight: 600;
    font-size: 0.8rem;
}
.stale-run-btn:hover {
    opacity: 0.85;
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/dashboard.py frontend/src/components/StaleBanner.*
git commit -m "feat: add data freshness tracking and frontend banner"
```
