# Backtesting Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a full-stack backtesting engine that allows users to optimize parameters (threshold, stop-loss, etc.) by simulating trades on historical NSE data.

**Architecture:** A sequential background runner (O(n) scoring) that fetches historical OHLCV data, computes technical signals using `pandas-ta`, and simulates trade entry/exit logic. Results are persisted in PostgreSQL and visualized via a React dashboard.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pandas-ta, yfinance, React (Vite), Recharts.

---

### Task 1: Database Schema & Migrations

**Files:**
- Modify: `backend/app/db/models.py`
- Create: Alembic migration files

- [ ] **Step 1: Add BacktestRun and BacktestTrade models**

Update `backend/app/db/models.py` to include the new models.

```python
import uuid
import datetime
from sqlalchemy import Column, String, Float, DateTime, Text, Integer, ForeignKey, Date
# ... existing imports

class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    run_id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)
    status          = Column(String, nullable=False) # 'pending', 'running', 'complete', 'failed'
    config          = Column(Text, nullable=False)   # JSON string
    symbols_total   = Column(Integer, default=0)
    symbols_done    = Column(Integer, default=0)
    error_message   = Column(Text, nullable=True)
    total_trades     = Column(Integer, nullable=True)
    winning_trades   = Column(Integer, nullable=True)
    win_rate         = Column(Float, nullable=True)
    avg_return_pct   = Column(Float, nullable=True)
    median_return_pct = Column(Float, nullable=True)
    best_trade_pct   = Column(Float, nullable=True)
    worst_trade_pct  = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    sharpe_ratio     = Column(Float, nullable=True)
    total_return_pct = Column(Float, nullable=True)
    benchmark_return_pct = Column(Float, nullable=True)
    equity_curve_json = Column(Text, nullable=True)

class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    run_id          = Column(String, ForeignKey('backtest_runs.run_id'), nullable=False)
    symbol          = Column(String, nullable=False)
    sector          = Column(String, nullable=True)
    signal_date     = Column(Date, nullable=False)
    entry_date      = Column(Date, nullable=False)
    exit_date       = Column(Date, nullable=False)
    exit_reason     = Column(String, nullable=False) # 'holding_period', 'stop_loss', 'target'
    signal_score    = Column(Float, nullable=False)
    entry_price     = Column(Float, nullable=False)
    exit_price      = Column(Float, nullable=False)
    return_pct      = Column(Float, nullable=False)
    rsi_at_signal   = Column(Float, nullable=True)
    adx_at_signal   = Column(Float, nullable=True)
    ema_signal      = Column(String, nullable=True)
```

- [ ] **Step 2: Generate and run migrations**

Run:
```bash
cd backend
alembic revision --autogenerate -m "add_backtest_models"
alembic upgrade head
```
Verify tables `backtest_runs` and `backtest_trades` exist in the database.

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/models.py backend/migrations/versions/*.py
git commit -m "db: add backtest models and migrations"
```

---

### Task 2: Core Engine - Data Structures & Config

**Files:**
- Create: `backend/app/backtest/engine.py`
- Create: `backend/app/backtest/__init__.py`

- [ ] **Step 0: Create package init file**

Run: `touch backend/app/backtest/__init__.py`

- [ ] **Step 1: Define Config and Result Dataclasses**

```python
# backend/app/backtest/engine.py
from dataclasses import dataclass
import datetime

@dataclass
class BacktestConfig:
    score_threshold: float = 60.0
    holding_days: int = 20
    stop_loss_pct: float = 7.0
    target_pct: float = 0.0
    include_fundamentals: bool = False
    timeframe: str = 'D'
    date_from: datetime.date = None
    date_to: datetime.date = None
    symbol_limit: int = None

@dataclass
class TradeResult:
    symbol: str
    sector: str
    signal_date: datetime.date
    entry_date: datetime.date
    exit_date: datetime.date
    exit_reason: str
    signal_score: float
    entry_price: float
    exit_price: float
    return_pct: float
    rsi_at_signal: float
    adx_at_signal: float
    ema_signal: str
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat: define backtest engine data structures"
```

---

### Task 3: Core Engine - Scoring Logic (`score_series`)

**Files:**
- Modify: `backend/app/backtest/engine.py`
- Create: `backend/tests/unit/test_backtest_engine.py`

- [ ] **Step 1: Implement `score_series` function**

Replicate scoring rules from `scorer.py` in an O(n) row-level loop. Ensure rules match `backend/app/pipeline/scorer.py` (EMA alignment, MACD, RSI recovery, Volume breakouts).

- [ ] **Step 2: Write unit test for `score_series` and future leak**

Implement `test_score_series_returns_list` and the updated `test_score_series_no_future_leak` (from the spec review).

- [ ] **Step 3: Run tests and verify**

Run: `pytest backend/tests/unit/test_backtest_engine.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/backtest/engine.py backend/tests/unit/test_backtest_engine.py
git commit -m "feat: implement O(n) scoring logic for backtesting"
```

---

### Task 4: Core Engine - Trade Simulation & Metrics

**Files:**
- Modify: `backend/app/backtest/engine.py`
- Modify: `backend/tests/unit/test_backtest_engine.py`

- [ ] **Step 1: Implement `simulate_trades`**

Logic for next-day entry and exit based on SL, Target, and Holding Days. Use intraday High/Low for SL/Target checks.

- [ ] **Step 2: Implement `compute_metrics`**

Aggregate stats (Win Rate, Sharpe, Max Drawdown) and build equity curve JSON vs `^NSEI` benchmark data.

- [ ] **Step 3: Add unit tests for simulation and metrics**

Implement `test_simulate_trades_entry_is_next_day_open`, `test_simulate_trades_stop_loss_triggered`, and `test_compute_metrics_all_winners`.

- [ ] **Step 4: Run tests and verify**

Run: `pytest backend/tests/unit/test_backtest_engine.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/backtest/engine.py backend/tests/unit/test_backtest_engine.py
git commit -m "feat: implement trade simulation and metrics calculation"
```

---

### Task 5: Core Engine - Main Runner (`run_backtest`)

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Implement `run_backtest` function**

Orchestrator that:
1. Fetches benchmark (`^NSEI`) via `fetch_stock_data('^NSEI', append_ns=False, period='3y', fetch_info=False)`.
2. Selects symbols ordered by most recent signal date — use this exact query:
```python
   from sqlalchemy import func
   symbol_query = (
       db.query(TechnicalSignal.symbol)
       .group_by(TechnicalSignal.symbol)
       .order_by(func.max(TechnicalSignal.date).desc())
       .all()
   )
   symbols = [row[0] for row in symbol_query]
   if config.symbol_limit:
       symbols = symbols[:config.symbol_limit]
```
3. For each symbol: fetch OHLCV, run `score_series`, run `simulate_trades`, write trades to DB.
4. Commit every 10 symbols. Update `run.symbols_done` every 5 symbols.
5. After all symbols: call `compute_metrics`, persist aggregate fields to `BacktestRun`, set `status = 'complete'`.
6. Wrap entire body in try/except — on exception set `status = 'failed'`, write `error_message`.

- [ ] **Step 2: Commit**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat: implement main backtest orchestrator"
```

---

### Task 6: Backend API Router

**Files:**
- Create: `backend/app/routers/backtest.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backtest` router**

Define endpoints:
- `POST /run`: Starts background task, returns `run_id`.
- `GET /runs`: Lists last 20 runs.
- `GET /{run_id}`: Poll for status/metrics.
- `GET /{run_id}/trades`: Paginated trade list (50/page) with `exit_reason` filter.

- [ ] **Step 2: Register router in `main.py`**

- [ ] **Step 3: Test API endpoints**

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/backtest.py backend/app/main.py
git commit -m "api: add backtest router and register endpoints"
```

---

### Task 7: Frontend API Client & Navigation

**Files:**
- Modify: `frontend/src/api/client.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/MainLayout.jsx`

- [ ] **Step 1: Add API client functions**

Add `runBacktest`, `getBacktestRun`, `getBacktestRuns`, and `getBacktestTrades` to `apiClient`.

- [ ] **Step 2: Add Route to `App.jsx`**

Map `/backtest` to `Backtest` page.

- [ ] **Step 3: Add Sidebar Nav Item to `MainLayout.jsx`**

Use `FlaskConical` icon from `lucide-react`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.js frontend/src/App.jsx frontend/src/components/MainLayout.jsx
git commit -m "fe: add backtest api client and navigation"
```

---

### Task 8: Backtest Dashboard UI

**Files:**
- Create: `frontend/src/pages/Backtest.jsx`
- Create: `frontend/src/pages/Backtest.css`

- [ ] **Step 1: Implement Config Panel and Progress Bar**

Sliders for SL/Target/Threshold. Polling logic to track `status === 'running'`.

- [ ] **Step 2: Implement Metrics Cards and Equity Curve**

Use `Recharts` `LineChart` for the Strategy vs Nifty 50 overlay.

- [ ] **Step 3: Implement Trades Table**

Reuse `DataTable` from `ui/DataTable.jsx`. Add filters for `exit_reason`.

- [ ] **Step 4: Implement Polling and Results State Management**

Handle loading historical runs by clicking entries in a "Recent Runs" list.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Backtest.jsx frontend/src/pages/Backtest.css
git commit -m "fe: implement full backtest dashboard"
```
