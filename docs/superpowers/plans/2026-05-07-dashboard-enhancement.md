# Dashboard Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the stock dashboard with rich card data (confluence, price snapshots, fundamentals), sidebar funnel stats, and market context (Nifty 50).

**Architecture:** Update backend models to capture price/funnel data during pipeline runs, introduce a unified dashboard API endpoint with complex joins, and rebuild frontend components for higher data density.

**Tech Stack:** FastAPI, SQLAlchemy (PostgreSQL), Alembic, React (Vite), yfinance.

---

### Task 1: Database Schema Migration

**Files:**
- Create: `backend/migrations/versions/[timestamp]_dashboard_enhancement_fields.py` (via alembic)
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Update SQLAlchemy Models**

```python
# backend/app/db/models.py

# In TechnicalSignal class
close_price = Column(Float, nullable=True)
price_change_pct = Column(Float, nullable=True)

# In PipelineRun class
tier1_count = Column(Integer, default=0)
tier2_count = Column(Integer, default=0)

# New MarketSnapshot class
class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    date = Column(Date, primary_key=True)
    symbol = Column(String, primary_key=True)
    close = Column(Float)
    change_pct = Column(Float)
```

- [ ] **Step 2: Generate and apply migration**

Run: `cd backend && alembic revision --autogenerate -m "add dashboard enhancement fields and market_snapshots table" && alembic upgrade head`

- [ ] **Step 3: Verify migration**

Run: `psql $DATABASE_URL -c "\d technical_signals" && psql $DATABASE_URL -c "\d pipeline_runs" && psql $DATABASE_URL -c "\d market_snapshots"`
Expected: New columns and table exist.

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/models.py backend/migrations/versions/
git commit -m "db: add price, funnel, and market snapshot fields"
```

### Task 2: Pipeline Orchestrator Updates

**Files:**
- Modify: `backend/app/pipeline/fetcher.py`
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Update `fetch_stock_data` to support indices**

```python
# backend/app/pipeline/fetcher.py

def fetch_stock_data(symbol: str, append_ns: bool = True, period: str = "3y"):
    suffix = ".NS" if append_ns else ""
    ticker = yf.Ticker(f"{symbol}{suffix}")
    # ... rest of function unchanged
```

- [ ] **Step 2: Track funnel counts in orchestrator**

```python
# backend/app/pipeline/orchestrator.py

# After Tier 1 loop
run.tier1_count = len(tier1_survivors)
db.commit()

# Inside Tier 2 loop, track successes
tier2_survivors_count = 0
# ... inside loop where stock passes Tier 2 filters
tier2_survivors_count += 1
# After loop
run.tier2_count = tier2_survivors_count
db.commit()
```

- [ ] **Step 3: Capture price snapshots in scoring loop**

```python
# backend/app/pipeline/orchestrator.py

if tf == 'D' and len(working_df) >= 2:
    signal.close_price = float(working_df['Close'].iloc[-1])
    signal.price_change_pct = float(
        (working_df['Close'].iloc[-1] - working_df['Close'].iloc[-2]) 
        / working_df['Close'].iloc[-2] * 100
    )
```

- [ ] **Step 4: Implement Market Snapshot logic**

```python
# backend/app/pipeline/orchestrator.py (at end of run_pipeline)

from app.db.models import MarketSnapshot

# Derive signal_date from the same logic used in scoring loop
# If we have survivors, use the last candle date from the first one
if tier1_survivors and hist_cache:
    first_hist, _ = hist_cache[tier1_survivors[0]]
    signal_date = first_hist.index[-1].date()
else:
    signal_date = datetime.date.today()

indices = ["^NSEI"]
for idx in indices:
    hist, _ = fetch_stock_data(idx, append_ns=False, period="5d")
    if hist is not None and len(hist) >= 2:
        val = MarketSnapshot(
            date=signal_date,
            symbol=idx,
            close=float(hist['Close'].iloc[-1]),
            change_pct=float((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100)
        )
        db.merge(val) # Upsert
db.commit()
```

- [ ] **Step 5: Test pipeline run**

Run: `python backend/trigger_pipeline.py` (ensure it completes and populates new fields)

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline/
git commit -m "pipeline: populate funnel stats, price snapshots, and market context"
```

### Task 3: Unified Dashboard API Endpoints

**Files:**
- Create: `backend/app/routers/dashboard.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Implement `GET /api/screener/results`**

```python
# backend/app/routers/dashboard.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.db.models import Stock, TechnicalSignal, FundamentalData

router = APIRouter()

@router.get("/screener/results")
def get_dashboard_results(db: Session = Depends(get_db)):
    # 1. Get latest date from signals
    max_date = db.query(func.max(TechnicalSignal.date)).scalar()
    if not max_date:
        return []
        
    # 2. Latest Fundamental Subquery (Max date per symbol)
    latest_fund = db.query(
        FundamentalData.symbol,
        func.max(FundamentalData.date).label("max_date")
    ).group_by(FundamentalData.symbol).subquery()
    
    # 3. Join Query
    query_results = db.query(TechnicalSignal, Stock, FundamentalData).\
        join(Stock, TechnicalSignal.symbol == Stock.symbol).\
        outerjoin(latest_fund, Stock.symbol == latest_fund.c.symbol).\
        outerjoin(FundamentalData, (FundamentalData.symbol == latest_fund.c.symbol) & (FundamentalData.date == latest_fund.c.max_date)).\
        filter(TechnicalSignal.date == max_date).all()
        
    # 4. Python grouping
    stocks_map = {}
    for signal, stock, fund in query_results:
        if stock.symbol not in stocks_map:
            stocks_map[stock.symbol] = {
                "symbol": stock.symbol,
                "name": stock.name,
                "sector": stock.sector,
                "close_price": signal.close_price if signal.timeframe == 'D' else None,
                "price_change_pct": signal.price_change_pct if signal.timeframe == 'D' else None,
                "timeframes": {},
                "fundamentals": {
                    "pe": fund.pe if fund else None,
                    "pb": fund.pb if fund else None,
                    "roe": fund.roe if fund else None,
                    "market_cap": fund.market_cap if fund else stock.market_cap
                }
            }
        
        # Add timeframe signal
        stocks_map[stock.symbol]["timeframes"][signal.timeframe] = {
            "is_bullish": signal.is_bullish,
            "score": signal.entry_score,
            "rsi": signal.rsi,
            "ema_signal": signal.ema_signal
        }
        
        # Ensure D price info is captured even if row order varies
        if signal.timeframe == 'D':
            stocks_map[stock.symbol]["close_price"] = signal.close_price
            stocks_map[stock.symbol]["price_change_pct"] = signal.price_change_pct

    # 5. Final Confluence & Sorting
    final_results = list(stocks_map.values())
    for item in final_results:
        item["confluence_count"] = sum(1 for tf in item["timeframes"].values() if tf["is_bullish"])
    
    # Sort: Confluence DESC -> Daily Bullish DESC -> Daily Score DESC
    final_results.sort(key=lambda x: (
        x["confluence_count"],
        x["timeframes"].get('D', {}).get('is_bullish', False),
        x["timeframes"].get('D', {}).get('score', 0)
    ), reverse=True)

    return final_results
```

- [ ] **Step 2: Implement `GET /api/pipeline/latest`**

```python
# backend/app/routers/dashboard.py

@router.get("/pipeline/latest")
def get_pipeline_status(db: Session = Depends(get_db)):
    run = db.query(PipelineRun).order_by(PipelineRun.timestamp.desc()).first()
    if not run:
        return {"status": "never_run", "market_context": []}
        
    # MarketSnapshot uses Date, PipelineRun uses DateTime
    market = db.query(MarketSnapshot).filter(MarketSnapshot.date == run.timestamp.date()).all()
    
    return {
        "status": run.status,
        "scored_at": run.timestamp,
        "stocks_fetched": run.stocks_fetched,
        "tier1_count": run.tier1_count,
        "tier2_count": run.tier2_count,
        "stocks_scored": run.stocks_scored,
        "market_context": [
            {"symbol": m.symbol, "close": m.close, "change_pct": m.change_pct} 
            for m in market
        ]
    }
```

- [ ] **Step 3: Register router**

```python
# backend/app/main.py
app.include_router(dashboard.router, prefix="/api")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/dashboard.py backend/app/main.py
git commit -m "api: add unified dashboard and pipeline status endpoints"
```

### Task 4: Frontend Component Redesign

**Files:**
- Modify: `frontend/src/api/client.js`
- Create: `frontend/src/components/StockCard.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Update API client**

Update `fetchResults` and `fetchPipelineStatus` to use new endpoints.

- [ ] **Step 2: Build `StockCard` component**

Implement the dense layout with Confluence Badge, Timeframe Indicators, and Fundamental row.

- [ ] **Step 3: Update `Dashboard` with Summary Bar and Filters**

Add aggregate stats row. Implement client-side filtering for Confluence and Sector (using dynamically derived sectors).

- [ ] **Step 4: Implement Loading/Empty states**

Add skeleton loaders to the grid. Add "Pipeline never run" and "No results" views.

- [ ] **Step 5: Verify UI**

Run: `npm run dev` and check Dashboard functionality.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "ui: implement rich dashboard cards, funnel stats, and market context"
```
