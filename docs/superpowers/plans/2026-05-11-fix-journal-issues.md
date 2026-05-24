# Fix Journal P&L Logic and Test Mocking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix unmocked network calls in tests, improve P&L robustness, and add missing distance-to-limit fields in the Journal API.

**Architecture:** 
- Update the `GET /journal/open` endpoint to include calculated distance fields and robust price fallbacks.
- Use `unittest.mock.patch` in tests to intercept external yfinance calls.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pytest, unittest.mock

---

### Task 1: Update Journal Router Logic

**Files:**
- Modify: `backend/app/routers/journal.py`

- [ ] **Step 1: Refactor `get_open_trades` for robustness and new fields**

```python
@router.get("/open")
def get_open_trades(db: Session = Depends(get_db)):
    trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'open').all()
    if not trades:
        return []
    
    symbols = list(set([t.symbol for t in trades]))
    snapshots = fetch_market_snapshots(symbols)
    price_map = {s['symbol']: s['close'] for s in snapshots}
    
    results = []
    for t in trades:
        # Robust fallback: use entry_price if current_price is None or missing
        current_price = price_map.get(t.symbol) or t.entry_price
        
        unrealized_pnl = (current_price - t.entry_price) * t.shares
        live_return_pct = ((current_price - t.entry_price) / t.entry_price) * 100
        
        # Distance calculations
        # dist_to_stop: % from current_price down to stop_loss
        dist_to_stop = 0.0
        if current_price > 0:
            dist_to_stop = ((current_price - t.stop_loss) / current_price) * 100
            
        # dist_to_target: % from current_price up to target
        dist_to_target = 0.0
        if current_price > 0:
            dist_to_target = ((t.target - current_price) / current_price) * 100
        
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
            "dist_to_stop": dist_to_stop,
            "dist_to_target": dist_to_target,
            "notes": t.notes
        }
        results.append(trade_data)
        
    return results
```

- [ ] **Step 2: Verify the file content after editing**

### Task 2: Fix Journal API Tests

**Files:**
- Modify: `backend/tests/api/test_journal_api.py`

- [ ] **Step 1: Mock `fetch_market_snapshots` in `test_get_open_trades_with_live_pnl`**

```python
from unittest.mock import patch

def test_get_open_trades_with_live_pnl(client, db):
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
    db.add(trade)
    db.commit()

    with patch("app.routers.journal.fetch_market_snapshots") as mock_fetch:
        mock_fetch.return_value = [{"symbol": "RELIANCE.NS", "close": 2600.0, "change_pct": 1.0}]
        
        response = client.get("/api/journal/open")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        
        trade_data = data[0]
        assert trade_data["current_price"] == 2600.0
        assert trade_data["unrealized_pnl"] == 1000.0 # (2600-2500)*10
        assert trade_data["live_return_pct"] == 4.0 # (2600-2500)/2500 * 100
        
        # Verify new fields
        # dist_to_stop = (2600 - 2400) / 2600 * 100 = 200 / 2600 * 100 = 7.6923...
        assert "dist_to_stop" in trade_data
        assert abs(trade_data["dist_to_stop"] - 7.69) < 0.01
        
        # dist_to_target = (2700 - 2600) / 2600 * 100 = 100 / 2600 * 100 = 3.846...
        assert "dist_to_target" in trade_data
        assert abs(trade_data["dist_to_target"] - 3.84) < 0.01
```

- [ ] **Step 2: Run all journal tests to verify**

Run: `pytest backend/tests/api/test_journal_api.py -v`

### Task 3: Final Verification and Commit

- [ ] **Step 1: Run all backend tests to ensure no regressions**

Run: `pytest backend/tests/ -v`

- [ ] **Step 2: Commit changes**

```bash
git add backend/app/routers/journal.py backend/tests/api/test_journal_api.py
git commit -m "fix(journal): add dist to stop/target, robust price fallback, and mock tests"
```
