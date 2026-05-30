# Fix Journal Page Mismatches and Add Manual Entry

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align backend and frontend for the Trade Journal page, fixing field mismatches and adding manual entry support.

**Architecture:** Update FastAPI backend to provide accurate stats, and React frontend to use correct fields and support new interactions.

**Tech Stack:** Python (FastAPI, SQLAlchemy), React (Vite).

---

### Task 1: Update Backend Stats Endpoint

**Files:**
- Modify: `backend/app/routers/journal.py`

- [ ] **Step 1: Update `get_journal_stats` to include `total_unrealized_pnl`**

Update the function to fetch open trades, get current prices via `fetch_market_snapshots`, and sum up unrealized PnL.

```python
@router.get("/stats")
def get_journal_stats(db: Session = Depends(get_db)):
    closed_trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'closed').all()
    open_trades = db.query(models.TradeJournal).filter(models.TradeJournal.status == 'open').all()

    total_trades = len(closed_trades)
    winning_trades = len([t for t in closed_trades if (t.pnl or 0) > 0])
    total_pnl = sum([t.pnl or 0 for t in closed_trades])
    avg_return = round(sum([t.return_pct or 0 for t in closed_trades]) / total_trades, 2) if total_trades > 0 else 0

    # Calculate Unrealized PnL
    total_unrealized_pnl = 0.0
    if open_trades:
        symbols = list(set([t.symbol for t in open_trades]))
        snapshots = fetch_market_snapshots(symbols)
        price_map = {s['symbol']: s['close'] for s in snapshots}

        for t in open_trades:
            current_price = price_map.get(t.symbol) or t.entry_price
            total_unrealized_pnl += (current_price - t.entry_price) * t.shares

    return {
        "total_trades": total_trades,
        "win_rate": round((winning_trades / total_trades) * 100, 2) if total_trades > 0 else 0,
        "total_pnl": total_pnl,
        "avg_return": avg_return,
        "total_unrealized_pnl": total_unrealized_pnl,
        "open_positions": len(open_trades)
    }
```

- [ ] **Step 2: Verify backend response**

Run: `pytest backend/tests/test_journal_stats.py` (Need to create this test if it doesn't exist)

### Task 2: Fix Frontend Field Mismatches

**Files:**
- Modify: `frontend/src/pages/Journal.jsx`

- [ ] **Step 1: Correct Stats Bar field names**

Update `label="Total Realized P&L"` to use `stats?.total_pnl` and `stats?.avg_return`.
Update `label="Open Unrealized P&L"` to use `stats?.total_unrealized_pnl` and `stats?.open_positions`.

- [ ] **Step 2: Correct Open Positions Table field names**

Update `pos.unrealised_pct` to `pos.live_return_pct`.

- [ ] **Step 3: Update Close Trade Request to include `exit_date`**

Ensure `handleCloseSubmit` sends `exit_date: new Date().toISOString().split('T')[0]`.

### Task 3: Add Manual Entry Button and Modal

**Files:**
- Modify: `frontend/src/pages/Journal.jsx`

- [ ] **Step 1: Add "Manual Entry" button to header**

Add a button next to the "Last Updated" card.

- [ ] **Step 2: Create Manual Entry Modal and form state**

Add state for `manualModalOpen` and form fields for `symbol`, `entry_price`, `shares`, `stop_loss`, `target`, `entry_date`, `notes`.

- [ ] **Step 3: Implement `handleManualSubmit`**

Call `createJournalEntry(formData)` and refresh data.

---
