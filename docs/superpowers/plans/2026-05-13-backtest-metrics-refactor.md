# Backtest Metrics and Capital Logic Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor backtest engine to use realistic portfolio capital, properly filtered benchmark comparisons, and time-aware Sharpe ratios.

**Architecture:** 
- Update `BacktestRun` model with `starting_capital` and `position_size`.
- Slice benchmark data in `run_backtest` based on trade entry dates.
- Refactor `compute_metrics` to calculate PnL and Sharpe Ratio from daily equity series.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, pandas.

---

### Task 1: DB Schema Migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/migrations/versions/<new_migration>.py`

- [ ] **Step 1: Add columns to BacktestRun model**
Add `starting_capital` and `position_size` to the `BacktestRun` class in `backend/app/db/models.py`.

```python
class BacktestRun(Base):
    # ... existing columns ...
    starting_capital = Column(Float, nullable=True)
    position_size    = Column(Float, nullable=True)
```

- [ ] **Step 2: Generate Alembic migration**
Run: `cd backend && alembic revision --autogenerate -m "add_capital_and_position_size_to_backtest_run"`

- [ ] **Step 3: Apply migration**
Run: `cd backend && alembic upgrade head`

- [ ] **Step 4: Commit**
```bash
git add backend/app/db/models.py backend/migrations/versions/
git commit -m "db: add starting_capital and position_size to backtest_runs"
```

---

### Task 2: Update Configuration and API Models

**Files:**
- Modify: `backend/app/backtest/engine.py`
- Modify: `backend/app/routers/backtest.py`

- [ ] **Step 1: Update BacktestConfig dataclass**
In `backend/app/backtest/engine.py`, add the new fields with defaults.

```python
@dataclass
class BacktestConfig:
    # ... existing ...
    starting_capital: float = 1000000.0
    position_size: float = 10000.0
```

- [ ] **Step 2: Update BacktestRequest Pydantic model**
In `backend/app/routers/backtest.py`, add fields to `BacktestRequest`.

```python
class BacktestRequest(BaseModel):
    # ... existing ...
    starting_capital: float = Field(default=1000000.0, ge=10000)
    position_size: float = Field(default=10000.0, ge=100)
```

- [ ] **Step 3: Pass new fields in start_backtest**
In `backend/app/routers/backtest.py`, update `start_backtest` to populate these fields in both the DB record and the engine config.

- [ ] **Step 4: Commit**
```bash
git add backend/app/backtest/engine.py backend/app/routers/backtest.py
git commit -m "feat: add starting_capital and position_size to config and api"
```

---

### Task 3: Refactor Benchmark Filtering

**Files:**
- Modify: `backend/app/backtest/engine.py:run_backtest`

- [ ] **Step 1: Implement benchmark slicing**
In `run_backtest`, after all trades are collected, calculate the correct date range and slice `benchmark_df`.

```python
# In run_backtest, before compute_metrics:
if all_trades:
    first_entry = min(t.entry_date for t in all_trades)
    effective_from = config.date_from or first_entry
    effective_to = config.date_to or datetime.date.today()
    
    benchmark_df = benchmark_df[
      (benchmark_df.index.normalize() >= pd.Timestamp(effective_from)) &
      (benchmark_df.index.normalize() <= pd.Timestamp(effective_to))
    ]
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/backtest/engine.py
git commit -m "fix: slice benchmark data to match backtest trade range"
```

---

### Task 4: Refactor Metrics and Sharpe Ratio

**Files:**
- Modify: `backend/app/backtest/engine.py:compute_metrics`

- [ ] **Step 1: Update PnL and Total Return logic**
Use `config.starting_capital` and `config.position_size`. 

**Critical:** Ensure the call site in `run_backtest` passes the `config` object to `compute_metrics`.

```python
# In compute_metrics:
total_pnl = sum((r / 100) * config.position_size for r in returns)
total_return_pct = (total_pnl / config.starting_capital) * 100

# In run_backtest, verify this call passes the config:
metrics = compute_metrics(all_trades, benchmark_df, config)
# NOT the old form: compute_metrics(all_trades, benchmark_df, BacktestConfig())
```

- [ ] **Step 2: Update Equity Curve and Sharpe Ratio**
Re-calculate Sharpe using daily returns from the equity curve.

```python
import numpy as np
# Inside compute_metrics
equity_series = pd.Series([pt['equity'] for pt in equity_curve])
if len(equity_series) > 1:
    daily_returns = equity_series.pct_change().dropna()
    if not daily_returns.empty and daily_returns.std() > 0:
        sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        sharpe_ratio = 0.0
```

- [ ] **Step 3: Commit**
```bash
git add backend/app/backtest/engine.py
git commit -m "feat: refactor metrics and add time-aware Sharpe ratio"
```

---

### Task 5: Router Serialization and Verification

**Files:**
- Modify: `backend/app/routers/backtest.py:_serialize_run`
- Create: `backend/tests/unit/test_backtest_metrics_refactor.py`

- [ ] **Step 1: Update _serialize_run**
Expose `starting_capital` and `position_size` in the API response.

- [ ] **Step 2: Write verification unit tests**
Create a test that specifically checks:
1. Benchmark slicing logic.
2. `total_return_pct` vs `avg_return_pct` discrepancy when capital is large.
3. Sharpe ratio calculation correctness.

- [ ] **Step 3: Run all tests**
Run: `pytest backend/tests/unit/test_backtest_metrics_refactor.py backend/tests/unit/test_backtest_engine.py`

- [ ] **Step 4: Commit**
```bash
git add backend/app/routers/backtest.py backend/tests/unit/
git commit -m "test: verify backtest metrics refactor"
```
