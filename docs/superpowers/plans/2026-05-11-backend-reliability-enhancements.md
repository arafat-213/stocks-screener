# Backend Reliability & Logic Enhancement Implementation Plan (Revised)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address critical bugs, logic errors, and architectural gaps in the backend to ensure a stable, secure, and accurate stock screening pipeline.

**Architecture:** Refactor background task management, CORS setup, scoring logic, and database queries. Transition to FastAPI lifespan events, implement DB-backed stop signals, and improve scoring models with clear point budgets.

**Tech Stack:** Python, FastAPI, SQLAlchemy, PostgreSQL, APScheduler, Alembic.

---

### Task 1: Critical Reliability & Security Fixes

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/routers/stocks.py`
- Modify: `backend/app/routers/screens.py`
- Modify: `backend/app/pipeline/orchestrator.py`
- Modify: `backend/app/db/models.py` (add `stop_requested` to `PipelineRun`)

- [ ] **Step 1: Add pipeline concurrency guard**
Modify `backend/app/routers/stocks.py` to check for an existing `PipelineRun` with `status='running'`. Return `HTTP 409 Conflict` if one is active.

- [ ] **Step 2: Fix background task DB session**
Modify `backend/app/routers/stocks.py` to open a new session inside the background task instead of passing the request session. Use a closure or wrapper to ensure session closure.

- [ ] **Step 3: Fix CORS configuration**
Modify `backend/app/main.py`. Change `allow_origins` to `["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]` and keep `allow_credentials=True`.

- [ ] **Step 4: Replace global `_STOP_SIGNAL` with DB-backed flag**
  - Add `stop_requested` boolean column to `PipelineRun` in `backend/app/db/models.py`.
  - Update `request_pipeline_stop()` in `orchestrator.py` to update the latest `PipelineRun` in the DB.
  - Update `run_pipeline` check loops to query the DB for the `stop_requested` flag.

- [ ] **Step 5: Add date filter to `TechnicalSignal` joins**
Modify `backend/app/routers/screens.py` and `backend/app/routers/dashboard.py`. Add a subquery or join condition to ensure only the latest `TechnicalSignal.date` per symbol is joined.

- [ ] **Step 6: Migrate to FastAPI lifespan events**
Modify `backend/app/main.py` to use the `lifespan` context manager for scheduler start/shutdown. Remove `@app.on_event`.

- [ ] **Step 7: Verify Fixes with new tests**
  - Create `backend/tests/api/test_reliability.py` to test CORS, concurrency, and session safety.
  - Run all tests: `cd backend && source venv/bin/activate && export PYTHONPATH=. && python -m pytest tests/api/test_reliability.py`

### Task 2: Logic & Scoring Improvements

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`
- Modify: `backend/app/pipeline/scorer.py`
- Modify: `backend/app/pipeline/screener.py`
- Modify: `backend/app/pipeline/reporter.py`

- [ ] **Step 1: Fix RS score computation**
Modify `_compute_rs_ranks` in `backend/app/pipeline/orchestrator.py` to calculate `rs_score = stock.momentum_12m - benchmark_return` before percentile-ranking.

- [ ] **Step 2: Dynamic `dividend_consistency` check**
Modify `backend/app/pipeline/screener.py` to calculate the three required years dynamically (Current-1, Current-2, Current-3).

- [ ] **Step 3: Formalize W/M score ceiling**
  - Keep W/M scores as pure technical trend indicators (max 70 pts).
  - Update `backend/app/pipeline/scorer.py` comments to explicitly state this ceiling.
  - (Frontend adjustment handled in separate FE task: display "Trend Only" or similar).

- [ ] **Step 4: Redistribute Fundamental Score (30 pts budget)**
Modify `calculate_fundamental_score` in `backend/app/pipeline/scorer.py` using the following budget:
  - PE: 10 pts
  - Pledge: 5 pts
  - ROE: 5 pts
  - ROCE: 5 pts
  - Debt/Equity: 5 pts
  - Total: 30 pts.

- [ ] **Step 5: Fix date filter in `reporter.py`**
Modify `backend/app/pipeline/reporter.py` to filter using `TechnicalSignal.date` (market date) instead of `scored_at` (timestamp).

- [ ] **Step 6: Creation of `test_scorer_improved.py` and verification**
  - Create `backend/tests/unit/test_scorer_improved.py` with test cases for the new point distribution and RS logic.
  - Run: `python -m pytest tests/unit/test_scorer_improved.py`

### Task 3: Scalability & Architecture Gaps

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`
- Modify: `backend/app/screens/materializer.py`
- Modify: `backend/app/screens/value.py`
- Create: `backend/migrations/versions/xxxx_add_history_to_screens.py`

- [ ] **Step 1: Memory optimization (`hist_cache`)**
Modify `run_pipeline` in `orchestrator.py`. If `len(tier1_survivors) > 300`, process stocks in chunks or sequentially to avoid holding all OHLCV data in memory.

- [ ] **Step 2: `ScreenResult` History Migration**
  - Create Alembic migration to add `computed_at` (Date) to `ScreenResult`.
  - Update existing rows to use today's date for `computed_at`.

- [ ] **Step 3: Update Materialization Logic**
Modify `materialize_all_screens` in `backend/app/screens/materializer.py`. Delete only the records matching the current `computed_at` date before inserting new ones (instead of `TRUNCATE`).

- [ ] **Step 4: Optimize `screen_low_debt_midcap` query**
Modify `backend/app/screens/value.py` to use a single SQL join between `FundamentalCache` and `Stock` instead of fetching symbols then querying.

- [ ] **Step 5: Adaptive sleep in fundamental fetching**
Modify `fetch_and_cache_deep_fundamentals` in `backend/app/pipeline/screener.py` to skip `time.sleep()` on the final batch.

### Task 4: Minor Issues & Final Verification

**Files:**
- Modify: `backend/app/pipeline/utils.py`
- Modify: `backend/app/routers/reports.py`
- Modify: `backend/app/pipeline/reporter.py`

- [ ] **Step 1: Fix minor issues**
  - Add comments about MCAP units in `screener.py`.
  - Fix Postgres date casting in `reports.py` (use `func.cast(TechnicalSignal.date, Date)`).
  - Add logging to `get_financial_row` in `utils.py`.
  - Fix `__file__` path resolution in `reporter.py` using `pathlib` or absolute paths.

- [ ] **Step 2: Final Verification**
Run the entire backend test suite: `python -m pytest`
Confirm no regressions and all new reliability tests pass.
