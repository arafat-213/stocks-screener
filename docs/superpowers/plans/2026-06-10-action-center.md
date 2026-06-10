# Action Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a hyper-focused "Action Center" on the dashboard that highlights stocks ready for entry or nearing stop-loss/target prices.

**Architecture:** Add a dedicated backend endpoint to categorize stocks from the Watchlist and Trade Journal based on live price proximity. Create a responsive React component to display these "Action Cards" with quick-access buttons.

**Tech Stack:** FastAPI, SQLAlchemy, React, Tailwind CSS, Lucide icons.

---

### Task 1: Backend API Endpoint

**Files:**
- Create: `backend/tests/api/test_action_center.py`
- Modify: `backend/app/routers/dashboard.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_action_center.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import models

def test_get_action_center_empty(db_session):
    client = TestClient(app)
    response = client.get("/dashboard/action-center")
    assert response.status_code == 200
    data = response.json()
    assert "entry_candidates" in data
    assert "sl_risk" in data
    assert "target_near" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/api/test_action_center.py`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Implement the endpoint in dashboard.py**

```python
# backend/app/routers/dashboard.py

@router.get("/action-center")
def get_action_center(db: Session = Depends(get_db)):
    # 1. Fetch data
    watchlist = db.query(models.Watchlist).filter(models.Watchlist.status == "watching").all()
    open_trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == "open").all()

    symbols = list(set([w.symbol for w in watchlist] + [t.symbol for t in open_trades]))
    if not symbols:
        return {"entry_candidates": [], "sl_risk": [], "target_near": []}

    # 2. Fetch live prices
    snapshots = fetch_market_snapshots(symbols)
    price_map = {s["symbol"]: s["close"] for s in snapshots}

    entry_candidates = []
    sl_risk = []
    target_near = []

    # 3. Categorize Watchlist
    for w in watchlist:
        price = price_map.get(w.symbol)
        if price and w.planned_entry_low and w.planned_entry_high:
            if w.planned_entry_low <= price <= w.planned_entry_high:
                entry_candidates.append({
                    "symbol": w.symbol,
                    "current_price": price,
                    "entry_low": w.planned_entry_low,
                    "entry_high": w.planned_entry_high,
                    "watchlist_id": w.id
                })

    # 4. Categorize Open Trades
    for t in open_trades:
        price = price_map.get(t.symbol)
        if not price: continue

        if t.stop_loss:
            dist_pct = (price - t.stop_loss) / t.stop_loss * 100
            if dist_pct <= 1.5: # Within 1.5% of SL
                sl_risk.append({
                    "id": t.id,
                    "symbol": t.symbol,
                    "current_price": price,
                    "stop_loss": t.stop_loss,
                    "dist_pct": round(dist_pct, 2)
                })

        if t.target:
            dist_pct = (t.target - price) / price * 100
            if dist_pct <= 1.5: # Within 1.5% of Target
                target_near.append({
                    "id": t.id,
                    "symbol": t.symbol,
                    "current_price": price,
                    "target": t.target,
                    "dist_pct": round(dist_pct, 2)
                })

    return sanitize_for_json({
        "entry_candidates": entry_candidates,
        "sl_risk": sl_risk,
        "target_near": target_near
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/api/test_action_center.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/api/test_action_center.py backend/app/routers/dashboard.py
git commit -m "feat(backend): add /dashboard/action-center endpoint"
```

---

### Task 2: Frontend API and Hook

**Files:**
- Modify: `frontend/src/api/client.js`
- Create: `frontend/src/hooks/useActionCenter.js`

- [ ] **Step 1: Update API client**

```javascript
// frontend/src/api/client.js

export const getActionCenter = () => api.get('/dashboard/action-center').then(r => r.data);
```

- [ ] **Step 2: Create useActionCenter hook**

```javascript
// frontend/src/hooks/useActionCenter.js
import { useState, useEffect } from 'react';
import { getActionCenter } from '../api/client';

export const useActionCenter = (interval = 30000) => {
  const [data, setData] = useState({ entry_candidates: [], sl_risk: [], target_near: [] });
  const [loading, setLoading] = useState(true);

  const fetch = async () => {
    try {
      const res = await getActionCenter();
      setData(res);
    } catch (err) {
      console.error('Failed to fetch action center', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetch();
    const t = setInterval(fetch, interval);
    return () => clearInterval(t);
  }, [interval]);

  return { ...data, loading, refetch: fetch };
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.js frontend/src/hooks/useActionCenter.js
git commit -m "feat(frontend): add useActionCenter hook and api client method"
```

---

### Task 3: ActionCenter Component

**Files:**
- Create: `frontend/src/components/ActionCenter.jsx`

- [ ] **Step 1: Implement ActionCenter component**

```jsx
// frontend/src/components/ActionCenter.jsx
import React from 'react';
import { AlertTriangle, Target, Zap, ChevronRight } from 'lucide-react';

const ActionCard = ({ symbol, title, subtitle, colorClass, actionLabel, onAction }) => (
  <div className={`p-4 rounded-2xl border-2 border-border bg-bg-secondary flex justify-between items-center transition-all hover:border-${colorClass}-500 group shadow-sm`}>
    <div>
      <div className="flex items-center gap-2">
        <span className="text-lg font-black tracking-tight">{symbol.replace('.NS', '')}</span>
        <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded bg-${colorClass}-500/10 text-${colorClass}-500`}>
          {title}
        </span>
      </div>
      <p className="text-xs font-bold text-text-muted mt-1 uppercase tracking-tighter">{subtitle}</p>
    </div>
    <button
      onClick={onAction}
      className={`bg-${colorClass}-500 hover:bg-${colorClass}-600 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 shadow-lg shadow-${colorClass}-500/20 transition-all active:scale-95`}
    >
      {actionLabel}
      <ChevronRight size={14} />
    </button>
  </div>
);

const ActionCenter = ({ entry_candidates, sl_risk, target_near, onExecute, onExit }) => {
  const hasItems = entry_candidates.length > 0 || sl_risk.length > 0 || target_near.length > 0;
  if (!hasItems) return null;

  return (
    <div className="mb-8 animate-fade-in">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
        <h2 className="text-xl font-black uppercase tracking-tight">Action Center</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Entry candidates */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-blue-500 mb-1">
            <Zap size={18} />
            <span className="text-xs font-black uppercase tracking-widest">Entry Zone</span>
          </div>
          {entry_candidates.map(item => (
            <ActionCard
              key={item.symbol}
              symbol={item.symbol}
              title="Inside Zone"
              subtitle={`₹${item.current_price} (Range: ${item.entry_low}-${item.entry_high})`}
              colorClass="blue"
              actionLabel="EXECUTE"
              onAction={() => onExecute(item)}
            />
          ))}
          {entry_candidates.length === 0 && <p className="text-xs text-text-muted italic px-2">No entry zones hit...</p>}
        </div>

        {/* SL Risk */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-bearish mb-1">
            <AlertTriangle size={18} />
            <span className="text-xs font-black uppercase tracking-widest">Stop Loss Risk</span>
          </div>
          {sl_risk.map(item => (
            <ActionCard
              key={item.id}
              symbol={item.symbol}
              title={`${item.dist_pct}% from SL`}
              subtitle={`₹${item.current_price} vs SL ₹${item.stop_loss}`}
              colorClass="red"
              actionLabel="EXIT"
              onAction={() => onExit(item)}
            />
          ))}
          {sl_risk.length === 0 && <p className="text-xs text-text-muted italic px-2">Portfolio safe...</p>}
        </div>

        {/* Target Near */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-bullish mb-1">
            <Target size={18} />
            <span className="text-xs font-black uppercase tracking-widest">Targets Near</span>
          </div>
          {target_near.map(item => (
            <ActionCard
              key={item.id}
              symbol={item.symbol}
              title={`${item.dist_pct}% to Target`}
              subtitle={`₹${item.current_price} vs Tgt ₹${item.target}`}
              colorClass="green"
              actionLabel="EXIT"
              onAction={() => onExit(item)}
            />
          ))}
          {target_near.length === 0 && <p className="text-xs text-text-muted italic px-2">Scanning for targets...</p>}
        </div>
      </div>
    </div>
  );
};

export default ActionCenter;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ActionCenter.jsx
git commit -m "feat(frontend): create ActionCenter component"
```

---

### Task 4: Dashboard Integration

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Import hook and component**

```javascript
// frontend/src/pages/Dashboard.jsx
import ActionCenter from '../components/ActionCenter';
import { useActionCenter } from '../hooks/useActionCenter';
```

- [ ] **Step 2: Add state and handlers for modals**

Add this to the `Dashboard` component:

```javascript
const { entry_candidates, sl_risk, target_near, refetch: refetchActionCenter } = useActionCenter();
const navigate = useNavigate();

const handleExecute = (item) => {
  navigate(`/portfolio?action=new&symbol=${item.symbol}&price=${item.current_price}&wl_id=${item.watchlist_id}`);
};

// For exit, we might need a small refactor or just open the portfolio page with context
const handleExit = (item) => {
  navigate(`/portfolio?action=exit&trade_id=${item.id}`);
};
```

- [ ] **Step 3: Update Portfolio.jsx to handle 'exit' action**

```javascript
// frontend/src/pages/Portfolio.jsx
useEffect(() => {
  const params = new URLSearchParams(location.search);
  if (params.get('action') === 'exit') {
    const tradeId = params.get('trade_id');
    const trade = openPositions.find(p => p.id.toString() === tradeId);
    if (trade) {
      handleCloseClick(trade);
      navigate('/portfolio', { replace: true });
    }
  }
}, [location.search, openPositions, navigate]);
```

- [ ] **Step 4: Place ActionCenter in Dashboard.jsx**

Place `<ActionCenter ... />` between the market overview cards and `HighConvictionDigest`.

- [ ] **Step 5: Verify integration**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard.jsx frontend/src/pages/Portfolio.jsx
git commit -m "feat(frontend): integrate ActionCenter into Dashboard"
```
