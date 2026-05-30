# Watchlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a lightweight Watchlist to track stock signals with live "Compute on Read" tracking for trading days elapsed and entry zone status.

**Architecture:** A new `Watchlist` table stores signal snapshots. The `GET /watchlist` endpoint fetches live OHLCV data to compute current status and session counts on the fly.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pandas (EMA), yfinance (via OHLCVCache).

---

### Task 1: Database Model & Migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: Alembic migration in `backend/migrations/versions/`

- [ ] **Step 1: Add Watchlist model to models.py**

```python
class Watchlist(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, ForeignKey('stocks.symbol'), nullable=False)
    added_date = Column(Date, nullable=False, default=datetime.date.today)
    signal_date = Column(Date, nullable=False)

    alert_type = Column(String, nullable=True)
    quality_tier = Column(String(1), nullable=True)
    signal_score = Column(Float, nullable=True)
    planned_entry_low = Column(Float, nullable=True)
    planned_entry_high = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default='watching') # 'watching', 'entered', 'skipped', 'expired'

    __table_args__ = (
        UniqueConstraint('symbol', 'signal_date'),
        Index('ix_watchlist_status', 'status'),
    )
```

- [ ] **Step 2: Generate and run migration**

Run: `cd backend && alembic revision --autogenerate -m "add watchlist table" && alembic upgrade head`
Expected: Migration file created and database updated.

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/models.py backend/migrations/versions/
git commit -m "db: add watchlist table and migration"
```

---

### Task 2: API POST Endpoint (Add to Watchlist)

**Files:**
- Create: `backend/app/routers/watchlist.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/api/test_watchlist.py`

- [ ] **Step 1: Write failing test for POST**

```python
def test_add_to_watchlist_success(client, db_session):
    # Setup: Create a technical signal to pull data from
    # ... mock signal code ...
    response = client.post("/api/watchlist/", json={"symbol": "RELIANCE.NS", "signal_date": "2026-05-20"})
    assert response.status_code == 200
```

- [ ] **Step 2: Create router and POST endpoint**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Watchlist, TechnicalSignal
from pydantic import BaseModel
import datetime

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

class WatchlistAdd(BaseModel):
    symbol: str
    signal_date: datetime.date

@router.post("/")
def add_to_watchlist(data: WatchlistAdd, db: Session = Depends(get_db)):
    # 1. Check if already exists
    existing = db.query(Watchlist).filter(
        Watchlist.symbol == data.symbol,
        Watchlist.signal_date == data.signal_date
    ).first()
    if existing:
        return existing

    # 2. Fetch signal metadata
    sig = db.query(TechnicalSignal).filter(
        TechnicalSignal.symbol == data.symbol,
        func.date(TechnicalSignal.date) == data.signal_date,
        TechnicalSignal.timeframe == 'D'
    ).first()

    # 3. Create entry
    entry = Watchlist(
        symbol=data.symbol,
        signal_date=data.signal_date,
        quality_tier=sig.quality_tier if sig else None,
        # ... map other fields from sig ...
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
```

- [ ] **Step 3: Register router in main.py**

```python
from app.routers import stocks, dashboard, reports, screens, backtest, paper_trading, watchlist
# ...
app.include_router(watchlist.router, prefix="/api")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/api/test_watchlist.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/watchlist.py backend/app/main.py backend/tests/api/test_watchlist.py
git commit -m "api: implement POST /watchlist"
```

---

### Task 3: GET /api/watchlist with Live Logic

**Files:**
- Modify: `backend/app/routers/watchlist.py`
- Modify: `backend/tests/api/test_watchlist.py`

- [ ] **Step 1: Implement live calculation helper**

In `watchlist.py`:
```python
def compute_watchlist_live_data(entry: Watchlist, ohlcv_cache):
    df = ohlcv_cache.get(entry.symbol)
    if df is None or df.empty:
        return {"current_price": None, "days_elapsed": 0, "in_zone": False}

    # Count sessions since signal_date
    recent = df[df.index.date > entry.signal_date]
    days_elapsed = len(recent)

    # Live status
    current_price = df['Close'].iloc[-1]
    # ... compute EMA20 ...
    return {
        "current_price": current_price,
        "days_elapsed": days_elapsed,
        "in_zone": entry.planned_entry_low <= current_price <= entry.planned_entry_high,
        # ... vs_ema20 ...
    }
```

- [ ] **Step 2: Add GET endpoint**

```python
@router.get("/")
def get_watchlist(db: Session = Depends(get_db)):
    entries = db.query(Watchlist).filter(Watchlist.status == 'watching').all()
    results = []
    for e in entries:
        live = compute_watchlist_live_data(e, _ohlcv_cache)
        # Auto-expire if needed
        if live['days_elapsed'] > 8:
            e.status = 'expired'
            db.commit()
            continue
        results.append({**e.__dict__, "live": live})
    return results
```

- [ ] **Step 3: Test and Commit**

---

### Task 4: PATCH Status and GET Expired

**Files:**
- Modify: `backend/app/routers/watchlist.py`

- [ ] **Step 1: Add PATCH endpoint for status updates**
- [ ] **Step 2: Add GET /expired endpoint for history**
- [ ] **Step 3: Test and Commit**

---

### Task 5: Frontend Integration

**Files:**
- Create: `frontend/src/pages/Watchlist.jsx`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Create Watchlist UI page with shadcn/table**
- [ ] **Step 2: Add "Add to Watchlist" button to Screener/Dashboard rows**
- [ ] **Step 3: Verify functionality and Commit**
