# Named Screener Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the pipeline into a data enrichment engine and implement a "Named Screens" platform where screens are queries over persisted signals and fundamentals.

**Architecture:** 
1. **Schema Expansion:** Add columns to `technical_signals` and `fundamental_cache` for rich indicators. Create `screen_results` for materialization.
2. **Enrichment Engine:** Update `scorer.py` and `screener.py` to compute new metrics (Momentum, RS, ROCE, PEG, etc.).
3. **Optimized Pipeline:** Loosen Tier 1 filters, implement adaptive fetching for yfinance, and bulk-update RS scores.
4. **Screener Library:** Implement a screen registry and modular query functions.
5. **Materialization & API:** Materialize results at pipeline end and expose via a new screens API.

**Tech Stack:** Python (FastAPI), SQLAlchemy, Alembic, pandas-ta, yfinance.

---

### Task 0: Codebase Orientation (Read-only)

**Files:**
- Read: `backend/app/db/models.py`
- Read: `backend/app/pipeline/orchestrator.py`
- Read: `backend/app/pipeline/screener.py`
- Read: `backend/app/main.py`

- [ ] **Step 1: Read shared files**
Read the full content of `backend/app/db/models.py`, `backend/app/pipeline/orchestrator.py`, `backend/app/pipeline/screener.py`, and `backend/app/main.py` to ensure accurate context for implementation.

- [ ] **Step 2: Verify existing patterns**
Ensure understanding of existing `get_row` utility in `screener.py` and current `TechnicalSignal` model structure.

---

### Task 1: Database Schema Expansion (Alembic)

**Files:**
- Create: `backend/migrations/versions/<new_migration>.py`
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Update ORM Models**
Add new columns to `TechnicalSignal` and `FundamentalCache`. Create `ScreenResult` with columns: `id`, `screen_slug`, `symbol` (FK), `timeframe` (String(1)), `rank`, `score_used`, `computed_at`. No unique constraint — full table truncation before each write makes it unnecessary.

- [ ] **Step 2: Generate Migration**
Run: `alembic revision --autogenerate -m "add named screener fields and results table"`

- [ ] **Step 3: Verify Migration**
Inspect the generated migration file to ensure all columns (momentum, rs_score, adx, roce, peg, etc.) are present and correct.

- [ ] **Step 4: Apply Migration**
Run: `alembic upgrade head`

- [ ] **Step 5: Commit**
```bash
git add backend/app/db/models.py backend/migrations/versions/
git commit -m "db: add named screener fields and results table"
```

---

### Task 2: Robust Financial Extraction Utility

**Files:**
- Modify: `backend/app/pipeline/utils.py`
- Modify: `backend/app/pipeline/screener.py`

- [ ] **Step 1: Implement `get_financial_row` in `utils.py`**
Move and extend the existing `get_row` logic from `screener.py` to use a `FIELD_KEYWORDS` mapping with ordered keyword matching for net_income, revenue, ebit, total_assets, current_liab, op_cashflow, and capex.

- [ ] **Step 2: Update `screener.py` to use `get_financial_row`**
Refactor `check_profitability_streak` AND add stub extraction calls for `ebit`, `total_assets`, `current_liab`, `op_cashflow`, `capex` using `get_financial_row` so Task 5 has the scaffolding ready to fill in.

- [ ] **Step 3: Commit**
```bash
git add backend/app/pipeline/utils.py backend/app/pipeline/screener.py
git commit -m "feat: implement robust financial row extraction utility"
```

---

### Task 3: Extended Technical Scoring

**Files:**
- Modify: `backend/app/pipeline/scorer.py`
- Test: `backend/tests/unit/test_scorer_improved.py`

- [ ] **Step 1: Update `calculate_technical_score`**
Add computation for Momentum (1m, 3m, 6m, 12m), ADX, EMA200, EMA slope, 52w High/Low stats, and Resistance level. All new fields must be gated individually — if `len(df) < N` for a given indicator, set that field to `None` rather than falling through to a NaN. EMA200 and momentum_12m require `len(df) >= 252`. Do not raise the global `min_bars` guard — gate each field independently.

- [ ] **Step 2: Update `calculate_combined_score` return dict**
Ensure all new technical fields are returned in the result dictionary.

- [ ] **Step 3: Update/Add Tests**
Verify new indicators are computed correctly with mock data, handling insufficient data cases (returning `None`).

- [ ] **Step 4: Commit**
```bash
git add backend/app/pipeline/scorer.py backend/tests/unit/test_scorer_improved.py
git commit -m "feat: compute extended technical indicators with data guards"
```

---

### Task 4: Loosen Tier 1 Filters

**Files:**
- Modify: `backend/app/pipeline/screener.py`

- [ ] **Step 1: Update `passes_tier1_fast_filters`**
Adjust thresholds for Market Cap (₹200 Cr -> `20_000_000_000`), P/E (300), and remove ROE/Pledge gates. Update liquidity check to ₹2 Cr (`20_000_000`).

- [ ] **Step 2: Commit**
```bash
git add backend/app/pipeline/screener.py
git commit -m "feat: loosen tier 1 filters for broader screening"
```

---

### Task 5: Adaptive Fundamental Fetching (Screener Only)

**Files:**
- Modify: `backend/app/pipeline/screener.py`

- [ ] **Step 1: Update `fetch_and_cache_deep_fundamentals`**
Implement adaptive rate limiting (4.0s inter-batch sleep) and exponential backoff for `yf.Ticker` requests (initial 2s, max 3 attempts). Mark repeated failures with `cache_version = -1`.

- [ ] **Step 2: Implement Fundamental Extraction**
Fill in the stubs from Task 2 to compute ROCE, PEG, FCF, Price/FCF, and Dividend Consistency using the robust `get_financial_row` utility. Update Market Cap Category based on INR thresholds.

- [ ] **Step 3: Commit**
```bash
git add backend/app/pipeline/screener.py
git commit -m "feat: adaptive fundamental fetching and rich metrics extraction"
```

---

### Task 6: RS Bulk Update & Orchestrator Logic

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Implement `_compute_rs_ranks`**
Fetch benchmark using `RS_BENCHMARK_CANDIDATES = ["^CRSLDX", "^NSEI"]`. Try each in order; use the first that returns a series with >= 250 non-null rows. Log which symbol was selected at INFO level. Compute 12-month return on benchmark, then excess return per symbol, then percentile rank using `rank / count * 100` (no scipy dependency).

- [ ] **Step 2: Implement Bulk Update & Cache-Skip**
Update the scoring loop to skip `FundamentalCache` rows where `cache_version == -1`. Use `db.bulk_update_mappings` to update `rs_score` for all daily signals in one operation.

- [ ] **Step 3: Commit**
```bash
git add backend/app/pipeline/orchestrator.py
git commit -m "feat: implement bulk RS score computation and orchestrator cache-skip"
```

---

### Task 7: Screen Library & Materialization

**Files:**
- Create: `backend/app/screens/` (base.py, price_action.py, value.py, momentum.py, registry.py)
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Implement Screen Functions**
Implement query functions for all 8 screens (52w-high, 52w-low, near-breakout, low-debt-midcap, undervalued-fundamentals, momentum-monsters, value-with-momentum, steady-compounders) in the registry.

- [ ] **Step 2: Implement `materialize_all_screens`**
Issue `db.query(ScreenResult).delete()` (full truncation, no date filter) before writing new rows. Each screen function must set `timeframe` on its results — this becomes the `timeframe` column in `ScreenResult`.

- [ ] **Step 3: Commit**
```bash
git add backend/app/screens/ backend/app/pipeline/orchestrator.py
git commit -m "feat: implement screen library and materialization"
```

---

### Task 8: Screens API

**Files:**
- Create: `backend/app/routers/screens.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Implement Routes**
`GET /api/screens` (list metadata) and `GET /api/screens/{slug}` (materialized results with `live` fallback support).

- [ ] **Step 2: Register Router in `main.py`**
Include the `screens_router` in the FastAPI application.

- [ ] **Step 3: Commit**
```bash
git add backend/app/routers/screens.py backend/app/main.py
git commit -m "feat: add screens api endpoints"
```
