# Robustness Improvements Phase 2: Pipeline Resumability & Error Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the pipeline restartable after partial failure, track errors structurally, and implement smart backoff for failing fundamental fetches.

**Architecture:** Introduction of `PipelineCheckpoint` and `PipelineError` models. The orchestrator will check for a `resume_run_id` and skip completed symbols. Failing fetches will increment an attempt counter and set a `retry_after` timestamp.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic.

---

### Task 1: DB Models and Alembic Migrations

**Files:**
- Modify: `backend/app/db/models.py`
- Modify: `alembic/versions/...` (create new migrations)

- [ ] **Step 1: Add new models and fields to `models.py`**

```python
# In backend/app/db/models.py
from sqlalchemy import Column, String, Float, DateTime, PrimaryKeyConstraint, Text, Integer, Boolean, UniqueConstraint, Date, ForeignKey, func

# ... existing imports ...

class PipelineCheckpoint(Base):
    __tablename__ = "pipeline_checkpoints"
    run_id = Column(String, ForeignKey('pipeline_runs.run_id'), primary_key=True)
    phase = Column(String, primary_key=True)  
    completed_symbols = Column(Text)  # JSON array of symbols
    started_at = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)

class PipelineError(Base):
    __tablename__ = "pipeline_errors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey('pipeline_runs.run_id'), nullable=False)
    symbol = Column(String, nullable=True)
    phase = Column(String, nullable=False)  
    error_type = Column(String, nullable=False)  
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    occurred_at = Column(DateTime, default=datetime.datetime.utcnow)

# In FundamentalCache, add new fields:
class FundamentalCache(Base):
    # ... existing fields ...
    retry_after = Column(DateTime, nullable=True)
    fetch_attempts = Column(Integer, default=0)
    last_error = Column(String, nullable=True)
    force_refresh = Column(Boolean, default=False)
```

- [ ] **Step 2: Generate and verify Alembic migrations**

Run in order (upgrade between each to keep state clean):

```bash
# Migration 1: new tables
alembic revision --autogenerate -m "add_pipeline_checkpoints_and_errors"
# Inspect the generated file — verify it contains CreateTable for
# pipeline_checkpoints and pipeline_errors. If it's empty, the models
# are not imported in env.py. Fix: add the new models to the import in
# alembic/env.py (e.g. from app.db.models import Base).
alembic upgrade head

# Migration 2: new columns on existing table
alembic revision --autogenerate -m "add_fundamental_cache_backoff_fields"
# Inspect — verify it contains add_column for retry_after, fetch_attempts,
# last_error, force_refresh on fundamental_cache.
alembic upgrade head
```

Each generated migration MUST have a working `downgrade()`. Verify the downgrade
drops the tables/columns it added. Do not leave `pass` in downgrade functions.

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/models.py backend/migrations/versions/
git commit -m "feat: add pipeline checkpoints, errors, and cache backoff models"
```

---

### Task 2: Error Classification

**Files:**
- Create: `backend/app/pipeline/errors.py`
- Test: `backend/tests/unit/test_pipeline_errors.py`

- [ ] **Step 1: Write test for error classification**

```python
# backend/tests/unit/test_pipeline_errors.py
from app.pipeline.errors import classify_error
import sqlalchemy.exc

def test_classify_error():
    assert classify_error(Exception("429 Too Many Requests")) == "rate_limit"
    assert classify_error(Exception("Read timed out.")) == "timeout"
    assert classify_error(sqlalchemy.exc.OperationalError("statement", {}, None)) == "db_write"
    assert classify_error(ValueError("Some unknown error")) == "unknown"
```

- [ ] **Step 2: Create implementation**

```python
# backend/app/pipeline/errors.py
import sqlalchemy.exc

def classify_error(exc: Exception) -> str:
    """Returns one of: 'rate_limit', 'empty_data', 'db_write', 'timeout', 'unknown'"""
    msg = str(exc).lower()
    if "429" in msg or "too many requests" in msg or "rate limit" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if isinstance(exc, sqlalchemy.exc.SQLAlchemyError):
        return "db_write"
    if "empty data" in msg or "no data found" in msg:
        return "empty_data"
    return "unknown"
```

- [ ] **Step 3: Run test & Commit**

```bash
pytest backend/tests/unit/test_pipeline_errors.py -v
git add backend/app/pipeline/errors.py backend/tests/unit/test_pipeline_errors.py
git commit -m "feat: add pipeline error classification helper"
```

---

### Task 3: Pipeline Checkpoint Logic

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`
- Modify: `backend/app/routers/screener.py`

- [ ] **Step 1: Implement checkpointing in orchestrator**

Modify `backend/app/pipeline/orchestrator.py` to use `resume_run_id` and save completed symbols:

```python
# In orchestrator.py, update run_pipeline signature:
def run_pipeline(db: Session, limit: int = None, resume_run_id: str | None = None):
    # Add logic to load completed_symbols from PipelineCheckpoint if resume_run_id is provided
    import json
    from app.db.models import PipelineCheckpoint, PipelineError
    from app.pipeline.errors import classify_error

    completed_symbols_tier1 = set()
    completed_symbols_scoring = set()

    if resume_run_id:
        checkpoints = db.query(PipelineCheckpoint).filter(PipelineCheckpoint.run_id == resume_run_id).all()
        for cp in checkpoints:
            if cp.completed_symbols:
                syms = set(json.loads(cp.completed_symbols))
                if cp.phase == 'tier1':
                    completed_symbols_tier1 = syms
                elif cp.phase == 'scoring':
                    completed_symbols_scoring = syms
        
        # We reuse the run
        run = db.query(PipelineRun).filter(PipelineRun.run_id == resume_run_id).first()
        run.status = "running"
    else:
        run = PipelineRun(status="running", stocks_fetched=0, stocks_scored=0)
        db.add(run)
    db.commit()

    # In the Tier 1 loop:
    # if symbol in completed_symbols_tier1: continue

    # In the Scoring loop:
    # if symbol in completed_symbols_scoring: continue

    # Add try/except block inside the loop to catch and log to PipelineError instead of stopping
    # ... (Implementation detail for agent to fill based on above pattern)
```

- [ ] **Step 2: Update router to accept `resume_run_id`**

Modify `backend/app/routers/screener.py`:
```python
from pydantic import BaseModel
class RunPipelineRequest(BaseModel):
    limit: int | None = None
    resume_run_id: str | None = None

@router.post("/run")
def start_pipeline(req: RunPipelineRequest, db: Session = Depends(get_db)):
    # Assuming background tasks are used
    # background_tasks.add_task(run_pipeline, db, limit=req.limit, resume_run_id=req.resume_run_id)
    pass # Adjust according to existing file structure
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/pipeline/orchestrator.py backend/app/routers/screener.py
git commit -m "feat: implement pipeline resumability via checkpoints"
```

---

### Task 4: FundamentalCache Backoff

**Files:**
- Modify: `backend/app/pipeline/screener.py`
- Modify: `backend/app/routers/stocks.py`

- [ ] **Step 1: Implement backoff logic**

Modify `backend/app/pipeline/screener.py` inside `fetch_and_cache_deep_fundamentals`:

```python
# When fetch fails:
# error_type = classify_error(e)
# cache.fetch_attempts += 1
# cache.last_error = str(e)[:255]
# if error_type == 'rate_limit':
#     cache.retry_after = datetime.datetime.utcnow() + datetime.timedelta(hours=6)
# elif error_type == 'empty_data' and cache.fetch_attempts >= 3:
#     cache.retry_after = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
# else:
#     cache.retry_after = datetime.datetime.utcnow() + datetime.timedelta(hours=2)

# Also update the `_needs_refresh` check to respect `retry_after` and `force_refresh`.
```
Also modify `backend/app/pipeline/orchestrator.py` to replace the existing stale check
in the Tier 2 refresh loop:

REMOVE:
```python
if not cache or cache.last_updated < seven_days_ago or cache.cache_version < CURRENT_SCREENER_VERSION:
    to_refresh.append(symbol)
```

REPLACE WITH a call to a helper defined in `screener.py`:
```python
# In screener.py, add this function:
def needs_cache_refresh(cache, seven_days_ago) -> bool:
    if cache is None:
        return True
    if getattr(cache, 'force_refresh', False):
        return True
    retry_after = getattr(cache, 'retry_after', None)
    if retry_after and datetime.datetime.utcnow() < retry_after:
        return False   # still in backoff window — skip
    if cache.last_updated < seven_days_ago:
        return True
    if cache.cache_version < CURRENT_SCREENER_VERSION:
        return True
    return False

# In orchestrator.py, import and use it:
from app.pipeline.screener import needs_cache_refresh
...
if needs_cache_refresh(cache, seven_days_ago):
    to_refresh.append(symbol)
```

The `getattr` guards are important: they prevent AttributeError during the period
before the Alembic migration has been run in a dev environment.

- [ ] **Step 2: Add force refresh endpoints**

Modify `backend/app/routers/stocks.py`:
```python
@router.post("/{symbol}/refresh-cache")
def refresh_cache(symbol: str, db: Session = Depends(get_db)):
    cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).first()
    if cache:
        cache.force_refresh = True
        cache.retry_after = None
        cache.fetch_attempts = 0
        db.commit()
    return {"queued": True}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/pipeline/screener.py backend/app/routers/stocks.py
git commit -m "feat: implement fundamental cache backoff and force refresh"
```
