# Unified Portfolio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate manual journaling and automated paper trading into a single 'Portfolio' view with bi-directional syncing.

**Architecture:** Extend the `TradeJournal` model to track source, implement a sync service to link paper trades to the journal, and refactor the frontend into a unified dashboard.

**Tech Stack:** Python (FastAPI, SQLAlchemy, Alembic), React (Vite).

---

### Task 1: Database Migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/migrations/versions/<timestamp>_add_source_to_journal.py` (via Alembic)

- [ ] **Step 1: Update TradeJournal model**

```python
# backend/app/db/models.py (around line 409)
class TradeJournal(Base):
    __tablename__ = "trade_journal"
    # ... existing fields ...
    source = Column(String, nullable=False, default="manual")  # 'manual' | 'paper'
    external_id = Column(Integer, nullable=True)  # Links to PaperPosition.id
```

- [ ] **Step 2: Generate and run Alembic migration**

Run: `cd backend && alembic revision --autogenerate -m "add_source_and_external_id_to_journal"`
Run: `alembic upgrade head`

- [ ] **Step 3: Verify migration**

Run: `export PGPASSWORD=postgres && psql -h localhost -U postgres -d stock_ai -c "\d trade_journal"`
Expected: Columns `source` and `external_id` exist.

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/models.py backend/migrations/versions/
git commit -m "db: add source and external_id to trade_journal"
```

---

### Task 2: Journal Sync Service

**Files:**
- Create: `backend/app/backtest/sync_service.py`
- Test: `backend/tests/unit/test_sync_service.py`

- [ ] **Step 1: Write failing test for sync logic**

```python
# backend/tests/unit/test_sync_service.py
from app.backtest.sync_service import sync_paper_to_journal
from app.db import models

def test_sync_new_position(db_session):
    paper_pos = models.PaperPosition(
        id=999,
        symbol="RELIANCE.NS",
        status="open",
        entry_price=2500.0,
        shares=10,
        entry_date="2024-01-01"
    )
    sync_paper_to_journal(db_session, paper_pos)
    journal_entry = db_session.query(models.TradeJournal).filter_by(external_id=999).first()
    assert journal_entry is not None
    assert journal_entry.source == "paper"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_sync_service.py`

- [ ] **Step 3: Implement sync service**

```python
# backend/app/backtest/sync_service.py
from app.db import models
from sqlalchemy.orm import Session

def sync_paper_to_journal(db: Session, paper_pos: models.PaperPosition):
    journal = db.query(models.TradeJournal).filter_by(
        source="paper", external_id=paper_pos.id
    ).first()

    if not journal:
        journal = models.TradeJournal(
            source="paper",
            external_id=paper_pos.id,
            symbol=paper_pos.symbol,
            entry_date=paper_pos.entry_date,
            entry_price=paper_pos.entry_price,
            shares=int(paper_pos.shares or 0),
            position_value=(paper_pos.entry_price or 0) * (paper_pos.shares or 0),
            status="open"
        )
        db.add(journal)

    # Sync updates/exits
    if paper_pos.status == "closed":
        journal.status = "closed"
        journal.exit_date = paper_pos.closed_at.date() if paper_pos.closed_at else None
        journal.exit_price = paper_pos.exit_price
        journal.exit_reason = paper_pos.exit_reason

    db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_sync_service.py`

- [ ] **Step 5: Commit**

```bash
git add backend/app/backtest/sync_service.py backend/tests/unit/test_sync_service.py
git commit -m "feat: add paper trading to journal sync service"
```

---

### Task 3: Integrate Sync into PaperTradingEngine

**Files:**
- Modify: `backend/app/paper_trading/engine.py`

- [ ] **Step 1: Identify entry/exit points in engine**

Open `backend/app/paper_trading/engine.py` and find where positions are opened and closed.

- [ ] **Step 2: Add sync calls**

```python
from app.backtest.sync_service import sync_paper_to_journal

# After opening a position:
sync_paper_to_journal(db, new_pos)

# After closing a position:
sync_paper_to_journal(db, closed_pos)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/paper_trading/engine.py
git commit -m "feat: integrate journal sync into paper trading engine"
```

---

### Task 4: API Refinement (Source Filtering)

**Files:**
- Modify: `backend/app/routers/journal.py`

- [ ] **Step 1: Update GET endpoints to support source filter**

```python
# backend/app/routers/journal.py
@router.get("/open")
def get_open_trades(source: str = None, db: Session = Depends(get_db)):
    query = db.query(models.TradeJournal).filter(models.TradeJournal.status == "open")
    if source:
        query = query.filter(models.TradeJournal.source == source)
    return query.all()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/journal.py
git commit -m "feat: support source filtering in journal API"
```

---

### Task 5: Frontend Portfolio Transformation

**Files:**
- Create: `frontend/src/pages/Portfolio.jsx`
- Modify: `frontend/src/App.jsx`
- Delete: `frontend/src/pages/Journal.jsx` (or rename)
- Delete: `frontend/src/pages/PaperTrading.jsx`

- [ ] **Step 1: Create Portfolio page with Source badges**

Build a unified view that fetches `/api/journal/open` and `/api/journal/closed` and displays them with a "System" vs "Manual" badge.

- [ ] **Step 2: Update Routes in App.jsx**

```javascript
// frontend/src/App.jsx
import Portfolio from './pages/Portfolio';
// ... remove Journal/PaperTrading imports ...

<Route path="/portfolio" element={<Portfolio />} />
<Route path="/journal" element={<Navigate to="/portfolio" replace />} />
<Route path="/paper" element={<Navigate to="/portfolio" replace />} />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Portfolio.jsx frontend/src/App.jsx
git commit -m "feat: unified portfolio frontend"
```
