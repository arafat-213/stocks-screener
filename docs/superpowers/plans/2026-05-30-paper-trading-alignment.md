# Paper Trading Alignment & Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure Paper Trading triggers match Email Alerts and are visible in the Portfolio UI as "Pending" trades.

**Architecture:**
1. Centralize Market Regime check using scored `^NSEI` data.
2. Extend `TradeJournal` sync to include `pending` status for transparency.
3. Update Frontend to render "Pending Pullback" status with entry targets.

**Tech Stack:** Python (FastAPI/SQLAlchemy), React (Vite)

---

### Task 1: Pipeline & Regime Alignment

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`
- Create: `backend/app/pipeline/utils.py` (if not exists, otherwise modify)
- Modify: `backend/app/alerts/engine.py`
- Modify: `backend/app/paper_trading/engine.py`

- [ ] **Step 1: Force score Nifty 50 in Orchestrator**
Modify `backend/app/pipeline/orchestrator.py` at the end of Tier 2/Scoring to always process `^NSEI`.

```python
# After the scoring loop in run_pipeline
indices = ["^NSEI", "^BSESN"]
for idx in indices:
    hist = _ohlcv_cache.get(idx, append_ns=False, period="3y")
    if hist is not None:
        process_symbol(idx, db, hist=hist, info=None, cache=None, scored_at=scored_at)
```

- [ ] **Step 2: Create shared `get_market_regime` helper**
In `backend/app/pipeline/utils.py` (or a new shared file):

```python
from app.db.models import TechnicalSignal
from sqlalchemy import func

def get_market_regime(db: Session, date: datetime.date) -> bool:
    sig = db.query(TechnicalSignal).filter(
        TechnicalSignal.symbol == "^NSEI",
        TechnicalSignal.timeframe == "D",
        func.date(TechnicalSignal.date) <= date
    ).order_by(TechnicalSignal.date.desc()).first()
    return bool(sig.is_bullish) if sig else True # Fallback to Bullish to avoid missing signals
```

- [ ] **Step 3: Update Alert Engine to use shared helper**
Modify `backend/app/alerts/engine.py` to use `get_market_regime`.

- [ ] **Step 4: Update Paper Trading Engine to use shared helper**
Modify `backend/app/paper_trading/engine.py` to remove `_get_regime` and use `get_market_regime`.

---

### Task 2: Sync Pending States to Journal

**Files:**
- Modify: `backend/app/backtest/sync_service.py`
- Modify: `backend/app/paper_trading/engine.py`
- Modify: `backend/app/routers/journal.py`

- [ ] **Step 1: Update `sync_paper_to_journal` in `backend/app/backtest/sync_service.py`**

```python
def sync_paper_to_journal(db: Session, paper_pos: models.PaperPosition):
    journal = (
        db.query(models.TradeJournal)
        .filter_by(source="paper", external_id=paper_pos.id)
        .first()
    )

    if not journal:
        journal = models.TradeJournal(
            source="paper",
            external_id=paper_pos.id,
            symbol=paper_pos.symbol,
            status="pending" if paper_pos.status == "pending" else "open",
        )
        db.add(journal)

    # Entry mappings
    journal.signal_date = paper_pos.signal_date
    journal.signal_score = paper_pos.signal_score

    if paper_pos.status == "pending":
        journal.status = "pending"
        journal.entry_price = paper_pos.ema20_at_signal # Target entry
        journal.shares = 0
        journal.position_value = 0
    elif paper_pos.status == "open":
        journal.status = "open"
        journal.entry_date = paper_pos.entry_date
        journal.entry_price = paper_pos.entry_price
        journal.shares = int(paper_pos.shares or 0)
        journal.position_value = (paper_pos.entry_price or 0) * (paper_pos.shares or 0)
        journal.stop_loss = paper_pos.stop_loss_price
        journal.target = paper_pos.target_price
    elif paper_pos.status in ["closed", "expired"]:
        journal.status = "closed"
        journal.exit_date = paper_pos.closed_at.date() if paper_pos.closed_at else None
        journal.exit_price = paper_pos.exit_price
        journal.exit_reason = paper_pos.exit_reason

    db.commit()
```

- [ ] **Step 2: Trigger Sync on Discovery and Invalidation**
In `backend/app/paper_trading/engine.py`:
- In `scan_for_new_signals`, call `sync_paper_to_journal(db, pending)` after adding it to the session.
- In `process_pending_orders`, call `sync_paper_to_journal(db, pos)` when `pos.status` changes to "expired".

- [ ] **Step 3: Update Journal Router `backend/app/routers/journal.py`**
Modify `get_open_trades` to allow "pending":

```python
@router.get("/open")
def get_open_trades(source: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.TradeJournal).filter(models.TradeJournal.status.in_(["open", "pending"]))
    # ...
```
And handle `live_return_pct` and `unrealized_pnl` for pending (set to 0).

---

### Task 3: Portfolio UI Enhancements

**Files:**
- Modify: `frontend/src/pages/Portfolio.jsx`

- [ ] **Step 1: Handle "pending" status in `OpenPositionsTable`**
Render "PENDING" badge and disable "CLOSE TRADE" button.

```jsx
const isPending = get('status')(pos) === 'pending';
// ...
<td className='p-4 text-right'>
  <button
    onClick={() => !isPending && onCloseTrade(pos)}
    disabled={isPending}
    className={`px-4 py-1.5 border border-border rounded-lg text-xs font-black transition-all shadow-sm ${
      isPending
        ? 'opacity-50 cursor-not-allowed bg-bg-secondary'
        : 'bg-bg-elevated hover:bg-primary hover:text-white'
    }`}
  >
    {isPending ? 'WATCHING' : 'CLOSE TRADE'}
  </button>
</td>
```

- [ ] **Step 2: Label Target Price for Pending**
In the price/PNL columns, show "TARGET" label if pending.

---

### Task 4: Verification

- [ ] **Step 1: Run Pipeline Simulation**
Manually trigger the pipeline and check logs/DB for `^NSEI` signal creation.
- [ ] **Step 2: Verify UI**
Open Portfolio page and ensure any pending paper signals are visible.
- [ ] **Step 3: Unit Test Sync Service**
Ensure manual entries still sync/work without `external_id` errors.
