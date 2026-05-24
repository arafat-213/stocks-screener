# Trade Journal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a manual trade journal to track actual execution, live P&L, and performance metrics, bridging the gap between system signals and user execution.

**Architecture:** Standalone module with a bridge from the Watchlist. Backend uses FastAPI and SQLAlchemy with on-demand yfinance fetching for live P&L. Frontend uses React.

**Tech Stack:** Python (FastAPI, SQLAlchemy, yfinance), React (Vite, TailwindCSS).

---

### Task 1: Database Model & Migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: Alembic migration (auto-generated)

- [ ] **Step 1: Add TradeJournal model to models.py**

```python
# backend/app/db/models.py
class TradeJournal(Base):
    __tablename__ = "trade_journal"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    watchlist_id = Column(Integer, ForeignKey('watchlist.id'), nullable=True)
    
    # Entry
    signal_date = Column(Date, nullable=True)
    entry_date = Column(Date, nullable=False, default=datetime.date.today)
    entry_price = Column(Float, nullable=False)
    shares = Column(Integer, nullable=False)
    position_value = Column(Float, nullable=False)
    
    # Risk Management
    stop_loss = Column(Float, nullable=False)
    target = Column(Float, nullable=False)
    quality_tier = Column(String(1), nullable=True)
    signal_score = Column(Float, nullable=True)
    
    # Exit
    exit_date = Column(Date, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True) # 'stop', 'target', 'manual', 'trail'
    pnl = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)
    
    status = Column(String, nullable=False, default='open') # 'open' | 'closed'
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        Index('ix_tj_status', 'status'),
        Index('ix_tj_symbol', 'symbol'),
    )
```

- [ ] **Step 2: Generate and run Alembic migration**

Run: `cd backend && alembic revision --autogenerate -m "add_trade_journal_table" && alembic upgrade head`

- [ ] **Step 3: Verify table exists**

Run: `psql -d stock_ai -c "\dt trade_journal"`

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/models.py backend/migrations/versions/*.py
git commit -m "db: add trade_journal table"
```

---

### Task 2: Backend Router & Basic CRUD

**Files:**
- Create: `backend/app/routers/journal.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create journal router with Pydantic schemas**

```python
# backend/app/routers/journal.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db import models
from pydantic import BaseModel
from typing import List, Optional
import datetime

router = APIRouter(prefix="/journal", tags=["journal"])

class TradeEntryCreate(BaseModel):
    symbol: str
    entry_price: float
    shares: int
    stop_loss: float
    target: float
    signal_date: Optional[datetime.date] = None
    entry_date: Optional[datetime.date] = datetime.date.today()
    watchlist_id: Optional[int] = None
    notes: Optional[str] = None

@router.post("/")
def create_entry(data: TradeEntryCreate, db: Session = Depends(get_db)):
    db_entry = models.TradeJournal(
        **data.model_dump(),
        position_value=data.entry_price * data.shares,
        status='open'
    )
    db.add(db_entry)
    
    # Bridge: Update watchlist status if linked
    if data.watchlist_id:
        wl = db.query(models.Watchlist).filter(models.Watchlist.id == data.watchlist_id).first()
        if wl:
            wl.status = 'entered'
            
    db.commit()
    db.refresh(db_entry)
    return db_entry
```

- [ ] **Step 2: Register router in main.py**

```python
# backend/app/main.py
from app.routers import stocks, dashboard, reports, screens, backtest, paper_trading, watchlist, journal
# ...
app.include_router(journal.router, prefix="/api")
```

- [ ] **Step 3: Test API endpoint with curl**

Run: `curl -X POST http://localhost:8000/api/journal/ -H "Content-Type: application/json" -d '{"symbol":"RELIANCE.NS", "entry_price":2500, "shares":10, "stop_loss":2300, "target":2800}'`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/journal.py backend/app/main.py
git commit -m "feat: add trade journal router and create endpoint"
```

---

### Task 3: Live P&L and Stats Logic

**Files:**
- Modify: `backend/app/routers/journal.py`

- [ ] **Step 1: Implement GET /open with Live P&L**

```python
# backend/app/routers/journal.py
from app.pipeline.fetcher import fetch_market_snapshots

@router.get("/open")
def get_open_positions(db: Session = Depends(get_db)):
    positions = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'open').all()
    if not positions:
        return []
    
    symbols = [p.symbol for p in positions]
    # Fetch live quotes
    snapshots = fetch_market_snapshots(symbols)
    prices = {s['symbol']: s['close'] for s in snapshots}
    
    results = []
    for p in positions:
        curr_price = prices.get(p.symbol) or prices.get(f"{p.symbol}.NS") or p.entry_price
        unrealized_pnl = (curr_price - p.entry_price) * p.shares
        return_pct = ((curr_price - p.entry_price) / p.entry_price) * 100
        
        results.append({
            "id": p.id,
            "symbol": p.symbol,
            "entry_price": p.entry_price,
            "curr_price": curr_price,
            "shares": p.shares,
            "unrealized_pnl": unrealized_pnl,
            "return_pct": return_pct,
            "stop_loss": p.stop_loss,
            "target": p.target,
            "dist_to_stop": ((p.stop_loss - curr_price) / curr_price) * 100,
            "dist_to_target": ((p.target - curr_price) / curr_price) * 100
        })
    return results
```

- [ ] **Step 2: Implement PATCH /{id}/close and GET /stats**

```python
# backend/app/routers/journal.py
class TradeExit(BaseModel):
    exit_price: float
    exit_date: datetime.date = datetime.date.today()
    exit_reason: str

@router.patch("/{id}/close")
def close_trade(id: int, data: TradeExit, db: Session = Depends(get_db)):
    trade = db.query(models.TradeJournal).filter(models.TradeJournal.id == id).first()
    if not trade:
        raise HTTPException(status_code=404)
        
    trade.exit_price = data.exit_price
    trade.exit_date = data.exit_date
    trade.exit_reason = data.exit_reason
    trade.status = 'closed'
    trade.pnl = (data.exit_price - trade.entry_price) * trade.shares
    trade.return_pct = ((data.exit_price - trade.entry_price) / trade.entry_price) * 100
    trade.holding_days = (data.exit_date - trade.entry_date).days
    
    db.commit()
    return trade

@router.get("/stats")
def get_journal_stats(db: Session = Depends(get_db)):
    trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'closed').all()
    if not trades:
        return {"win_rate": 0, "total_pnl": 0, "count": 0}
        
    wins = [t for t in trades if t.pnl > 0]
    total_pnl = sum(t.pnl for t in trades)
    
    return {
        "count": len(trades),
        "win_rate": len(wins) / len(trades) * 100,
        "total_pnl": total_pnl,
        "avg_return": sum(t.return_pct for t in trades) / len(trades)
    }
```

- [ ] **Step 3: Verify stats with local test script or curl**

Run: `curl http://localhost:8000/api/journal/stats`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/journal.py
git commit -m "feat: live pnl and trade exit logic for journal"
```

---

### Task 4: Frontend API & Route Setup

**Files:**
- Create: `frontend/src/api/journal.js`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Create journal API service**

```javascript
// frontend/src/api/journal.js
import axios from 'axios';
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const journalApi = {
  getOpen: () => axios.get(`${API_BASE}/journal/open`),
  getClosed: () => axios.get(`${API_BASE}/journal/closed`),
  getStats: () => axios.get(`${API_BASE}/journal/stats`),
  create: (data) => axios.post(`${API_BASE}/journal/`, data),
  close: (id, data) => axios.patch(`${API_BASE}/journal/${id}/close`, data),
};
```

- [ ] **Step 2: Add Route to App.jsx**

```javascript
// frontend/src/App.jsx
import Journal from './pages/Journal';
// ...
<Route path="/journal" element={<Journal />} />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/journal.js frontend/src/App.jsx
git commit -m "feat: frontend api and route for journal"
```

---

### Task 5: Frontend Journal Page

**Files:**
- Create: `frontend/src/pages/Journal.jsx`

- [ ] **Step 1: Implement Journal page with Tabs (Open/History)**

Use `Journal.jsx` template with basic table rendering for open positions and a summary bar.

- [ ] **Step 2: Add "Close Trade" Modal**

Implement a simple dialog to collect `exit_price` and `exit_reason`.

- [ ] **Step 3: Verify frontend renders and fetches data**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Journal.jsx
git commit -m "feat: journal page with open positions and history"
```

---

### Task 6: Frontend Watchlist Bridge

**Files:**
- Modify: `frontend/src/pages/Watchlist.jsx`

- [ ] **Step 1: Add "Log Trade" button to Watchlist rows**

```javascript
// frontend/src/pages/Watchlist.jsx
// In the table row actions:
<button 
  onClick={() => navigate(`/journal?action=new&symbol=${item.symbol}&price=${item.signal_price}&sl=${item.stop_loss}&target=${item.target}&wl_id=${item.id}`)}
  className="btn-primary"
>
  Log Trade
</button>
```

- [ ] **Step 2: Handle pre-fill in Journal.jsx**

```javascript
// frontend/src/pages/Journal.jsx
useEffect(() => {
  const params = new URLSearchParams(location.search);
  if (params.get('action') === 'new') {
    setNewTradeData({
      symbol: params.get('symbol'),
      entry_price: params.get('price'),
      // ...
    });
    setShowNewModal(true);
  }
}, [location]);
```

- [ ] **Step 3: Final verification of the end-to-end flow**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Watchlist.jsx frontend/src/pages/Journal.jsx
git commit -m "feat: bridge watchlist to journal with pre-fill"
```
