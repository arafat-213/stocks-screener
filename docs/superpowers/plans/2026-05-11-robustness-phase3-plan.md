# Robustness Improvements Phase 3: RS Rank Isolation & Health Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple RS rank computation so it can be run and tested independently, and improve the `/api/health` endpoint to reflect database and cache status.

**Architecture:** The RS rank computation logic will be moved from `orchestrator.py` to `rs_ranks.py` with its own API endpoint. The health endpoint will be updated to check DB connectivity and cache stats.

**Tech Stack:** Python, FastAPI.

---

### Task 1: Isolate RS Rank Computation

**Files:**
- Create: `backend/app/pipeline/rs_ranks.py`
- Modify: `backend/app/pipeline/orchestrator.py`
- Modify: `backend/app/routers/stocks.py`
- Test: `backend/tests/unit/test_rs_ranks.py`

- [ ] **Step 1: Write test for isolated RS rank**

```python
# backend/tests/unit/test_rs_ranks.py
from app.pipeline.rs_ranks import compute_rs_ranks
import datetime

def test_compute_rs_ranks(mock_db_session):
    # This requires a mock session setup, skipped actual implementation for brevity
    # The agent should mock the query and bulk_update_mappings
    pass
```

- [ ] **Step 2: Create implementation**

```python
# backend/app/pipeline/rs_ranks.py
import datetime
import logging
from sqlalchemy.orm import Session
from app.db.models import TechnicalSignal
from app.pipeline.fetcher import fetch_stock_data

logger = logging.getLogger(__name__)

def compute_rs_ranks(db: Session, signal_date: datetime.date, benchmark_symbol: str | None = None) -> dict:
    RS_BENCHMARK_CANDIDATES = ["^CRSLDX", "^NSEI"]
    benchmark_return = 0.0

    if not benchmark_symbol:
        for candidate in RS_BENCHMARK_CANDIDATES:
            hist, _ = fetch_stock_data(candidate, append_ns=False, period="2y")
            if hist is not None and len(hist) >= 252:
                benchmark_symbol = candidate
                benchmark_return = (hist['Close'].iloc[-1] / hist['Close'].iloc[-252] - 1) * 100
                break

    if not benchmark_symbol:
        return {"error": "No suitable RS benchmark found"}

    signals = db.query(TechnicalSignal).filter(
        TechnicalSignal.date == signal_date,
        TechnicalSignal.timeframe == 'D'
    ).all()

    valid_signals = [s for s in signals if s.momentum_12m is not None]
    if not valid_signals:
        return {"error": "No signals with 12m momentum found"}

    valid_signals.sort(key=lambda x: (x.momentum_12m - benchmark_return))
    count = len(valid_signals)

    updates = []
    for i, s in enumerate(valid_signals):
        rank = ((i + 1) / count) * 100
        updates.append({"id": s.id, "rs_score": rank})

    if updates:
        db.bulk_update_mappings(TechnicalSignal, updates)
        db.commit()

    return {
        "benchmark_used": benchmark_symbol,
        "benchmark_return": benchmark_return,
        "signals_updated": len(updates),
        "skipped_no_momentum": len(signals) - len(valid_signals)
    }
```

- [ ] **Step 3: Update Orchestrator and add API endpoint**

Modify `backend/app/pipeline/orchestrator.py`:
- Remove `_compute_rs_ranks`
- Import and use `compute_rs_ranks` from `app.pipeline.rs_ranks`.

Modify `backend/app/routers/stocks.py`:
```python
from app.pipeline.rs_ranks import compute_rs_ranks
from app.screens.base import get_latest_signal_date
import datetime

@router.post("/pipeline/recompute-rs")
def recompute_rs(
    date: str | None = None,   # accept as string, parse manually
    db: Session = Depends(get_db)
):
    if date:
        try:
            target_date = datetime.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        # Default to the latest date we have signals for
        latest = get_latest_signal_date(db, timeframe='D')
        target_date = latest.date() if hasattr(latest, 'date') else latest

    summary = compute_rs_ranks(db, target_date)
    return summary
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/pipeline/rs_ranks.py backend/app/pipeline/orchestrator.py backend/app/routers/stocks.py
git commit -m "refactor: isolate RS rank computation and add API endpoint"
```

---

### Task 2: Enhanced Health Check

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/test_health.py`

- [ ] **Step 1: Write test for enhanced health**

```python
# Modify backend/tests/unit/test_health.py
from fastapi.testclient import TestClient
# ... import app ...

def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "db" in data
    assert "cache" in data
```

- [ ] **Step 2: Update implementation**

Modify `backend/app/main.py` health check logic:

```python
from sqlalchemy import text
from app.core.cache import response_cache

@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    # We omit pipeline stale check for brevity here, but agent should implement it
    # based on the spec
    status = "error" if db_status == "error" else "ok"

    return {
        "status": status,
        "db": db_status,
        "cache": response_cache.stats(),
        "version": "2.1.0"
    }
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py backend/tests/unit/test_health.py
git commit -m "feat: enhance /api/health endpoint"
```
