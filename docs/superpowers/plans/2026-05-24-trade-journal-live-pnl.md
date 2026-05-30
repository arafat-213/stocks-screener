# Trade Journal Live P&L and Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Live P&L for open trades, historical trade retrieval, and trade statistics for the Trade Journal.

**Architecture:**
- Use `fetch_market_snapshots` from `app.pipeline.fetcher` to get real-time price data for open positions.
- Add `GET /open`, `GET /closed`, `GET /stats`, and `PATCH /{id}/close` endpoints to `backend/app/routers/journal.py`.
- Calculate unrealized P&L and return % dynamically for open trades.

**Tech Stack:** FastAPI, SQLAlchemy, yfinance (via fetcher).

---

### Task 1: Setup Tests and Implement `GET /journal/open` with Live P&L

**Files:**
- Modify: `backend/app/routers/journal.py`
- Create: `backend/tests/api/test_journal_api.py`

- [ ] **Step 1: Create the test file `backend/tests/api/test_journal_api.py`**

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db
from app.db import models
import datetime

client = TestClient(app)

def test_get_open_trades_with_live_pnl(db_session):
    # Add a dummy open trade
    trade = models.TradeJournal(
        symbol="RELIANCE.NS",
        entry_price=2500.0,
        shares=10,
        position_value=25000.0,
        stop_loss=2400.0,
        target=2700.0,
        status='open',
        entry_date=datetime.date.today()
    )
    db_session.add(trade)
    db_session.commit()

    response = client.get("/api/journal/open")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    # Current price might vary as it's fetched live, but keys should exist
    assert "unrealized_pnl" in data[0]
    assert "live_return_pct" in data[0]
    assert "current_price" in data[0]
```

- [ ] **Step 2: Implement `GET /journal/open` in `backend/app/routers/journal.py`**

```python
from app.pipeline.fetcher import fetch_market_snapshots

@router.get("/open")
def get_open_trades(db: Session = Depends(get_db)):
    trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'open').all()
    if not trades:
        return []

    symbols = list(set([t.symbol for t in trades]))
    # yfinance requires .NS for NSE stocks, TradeJournal should already have them
    snapshots = fetch_market_snapshots(symbols)
    price_map = {s['symbol']: s['close'] for s in snapshots}

    results = []
    for t in trades:
        current_price = price_map.get(t.symbol, t.entry_price)
        unrealized_pnl = (current_price - t.entry_price) * t.shares
        live_return_pct = ((current_price - t.entry_price) / t.entry_price) * 100

        trade_data = {
            "id": t.id,
            "symbol": t.symbol,
            "entry_date": t.entry_date,
            "entry_price": t.entry_price,
            "shares": t.shares,
            "position_value": t.position_value,
            "stop_loss": t.stop_loss,
            "target": t.target,
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "live_return_pct": live_return_pct,
            "notes": t.notes
        }
        results.append(trade_data)

    return results
```

- [ ] **Step 3: Run tests to verify `GET /open`**

Run: `pytest backend/tests/api/test_journal_api.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/journal.py backend/tests/api/test_journal_api.py
git commit -m "feat(journal): implement GET /open with live P&L"
```

---

### Task 2: Implement `GET /journal/closed`

**Files:**
- Modify: `backend/app/routers/journal.py`
- Modify: `backend/tests/api/test_journal_api.py`

- [ ] **Step 1: Add test for closed trades in `backend/tests/api/test_journal_api.py`**

```python
def test_get_closed_trades(db_session):
    # Add a dummy closed trade
    trade = models.TradeJournal(
        symbol="TCS.NS",
        entry_price=3000.0,
        shares=5,
        position_value=15000.0,
        stop_loss=2800.0,
        target=3500.0,
        exit_price=3200.0,
        exit_date=datetime.date.today(),
        pnl=1000.0,
        return_pct=6.67,
        status='closed'
    )
    db_session.add(trade)
    db_session.commit()

    response = client.get("/api/journal/closed")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["status"] == "closed"
    assert data[0]["pnl"] == 1000.0
```

- [ ] **Step 2: Implement `GET /journal/closed` in `backend/app/routers/journal.py`**

```python
@router.get("/closed")
def get_closed_trades(db: Session = Depends(get_db)):
    trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'closed').order_by(models.TradeJournal.exit_date.desc()).all()
    return trades
```

- [ ] **Step 3: Run tests to verify `GET /closed`**

Run: `pytest backend/tests/api/test_journal_api.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/journal.py backend/tests/api/test_journal_api.py
git commit -m "feat(journal): implement GET /closed for historical trades"
```

---

### Task 3: Implement `PATCH /journal/{id}/close`

**Files:**
- Modify: `backend/app/routers/journal.py`
- Modify: `backend/tests/api/test_journal_api.py`

- [ ] **Step 1: Add test for closing a trade in `backend/tests/api/test_journal_api.py`**

```python
def test_close_trade(db_session):
    # Add an open trade
    trade = models.TradeJournal(
        symbol="INFY.NS",
        entry_price=1500.0,
        shares=10,
        position_value=15000.0,
        stop_loss=1400.0,
        target=1700.0,
        status='open',
        entry_date=datetime.date.today() - datetime.timedelta(days=5)
    )
    db_session.add(trade)
    db_session.commit()
    trade_id = trade.id

    close_data = {
        "exit_price": 1600.0,
        "exit_date": str(datetime.date.today()),
        "exit_reason": "target"
    }
    response = client.patch(f"/api/journal/{trade_id}/close", json=close_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "closed"
    assert data["pnl"] == 1000.0
    assert abs(data["return_pct"] - 6.666) < 0.01
    assert data["holding_days"] == 5
```

- [ ] **Step 2: Implement `PATCH /journal/{id}/close` in `backend/app/routers/journal.py`**

```python
class TradeCloseRequest(BaseModel):
    exit_price: float
    exit_date: datetime.date
    exit_reason: str

@router.patch("/{trade_id}/close")
def close_trade(trade_id: int, data: TradeCloseRequest, db: Session = Depends(get_db)):
    trade = db.query(models.TradeJournal).filter(models.TradeJournal.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    if trade.status == 'closed':
        raise HTTPException(status_code=400, detail="Trade already closed")

    trade.exit_price = data.exit_price
    trade.exit_date = data.exit_date
    trade.exit_reason = data.exit_reason
    trade.status = 'closed'

    # Calculations
    trade.pnl = (data.exit_price - trade.entry_price) * trade.shares
    trade.return_pct = ((data.exit_price - trade.entry_price) / trade.entry_price) * 100

    if trade.entry_date:
        delta = data.exit_date - trade.entry_date
        trade.holding_days = delta.days

    db.commit()
    db.refresh(trade)
    return trade
```

- [ ] **Step 3: Run tests to verify `PATCH /close`**

Run: `pytest backend/tests/api/test_journal_api.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/journal.py backend/tests/api/test_journal_api.py
git commit -m "feat(journal): implement PATCH /close endpoint"
```

---

### Task 4: Implement `GET /journal/stats`

**Files:**
- Modify: `backend/app/routers/journal.py`
- Modify: `backend/tests/api/test_journal_api.py`

- [ ] **Step 1: Add test for stats in `backend/tests/api/test_journal_api.py`**

```python
def test_get_journal_stats(db_session):
    # Add one winner and one loser
    trade1 = models.TradeJournal(
        symbol="W1.NS", entry_price=100, shares=10, exit_price=110,
        status='closed', pnl=100, return_pct=10, exit_date=datetime.date.today()
    )
    trade2 = models.TradeJournal(
        symbol="L1.NS", entry_price=100, shares=10, exit_price=90,
        status='closed', pnl=-100, return_pct=-10, exit_date=datetime.date.today()
    )
    db_session.add_all([trade1, trade2])
    db_session.commit()

    response = client.get("/api/journal/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_trades"] == 2
    assert data["win_rate"] == 50.0
    assert data["total_pnl"] == 0.0
```

- [ ] **Step 2: Implement `GET /journal/stats` in `backend/app/routers/journal.py`**

```python
@router.get("/stats")
def get_journal_stats(db: Session = Depends(get_db)):
    closed_trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'closed').all()

    if not closed_trades:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "avg_return": 0
        }

    total_trades = len(closed_trades)
    winning_trades = len([t for t in closed_trades if (t.pnl or 0) > 0])
    total_pnl = sum([t.pnl or 0 for t in closed_trades])
    avg_return = sum([t.return_pct or 0 for t in closed_trades]) / total_trades

    return {
        "total_trades": total_trades,
        "win_rate": (winning_trades / total_trades) * 100,
        "total_pnl": total_pnl,
        "avg_return": avg_return
    }
```

- [ ] **Step 3: Run tests to verify `GET /stats`**

Run: `pytest backend/tests/api/test_journal_api.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/journal.py backend/tests/api/test_journal_api.py
git commit -m "feat(journal): implement GET /stats endpoint"
```
