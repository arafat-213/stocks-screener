# Decouple Pipeline Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the stock screening pipeline to decouple data persistence from quality filtering. This ensures technical screens (like 52w Low) can access the full universe of stocks while quality-focused screens remain selective.

**Architecture:** We will modify `orchestrator.py` to remove the hard `continue` for stocks failing Tier 2 checks. Instead, we will store quality flags for all stocks. We then update specific screen queries and the main dashboard router to apply these quality filters explicitly.

**Tech Stack:** Python (FastAPI, SQLAlchemy).

---

### Task 1: Pipeline Decoupling

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Remove the Early Exit for Quality Checks**
In `backend/app/pipeline/orchestrator.py`, locate the scoring loop and remove the conditional that skips stocks based on `profitability_streak_passed` or `de_check_passed`.

```python
# FIND THIS BLOCK:
            # Tier 2 Filters
            if not cache.profitability_streak_passed or not cache.de_check_passed:
                continue

# REMOVE IT OR COMMENT IT OUT.
```

- [ ] **Step 2: Update survivors count to reflect new logic**
Ensure `tier2_survivors_count` counts every stock that reaches this stage, regardless of the quality flag values.

- [ ] **Step 3: Commit**
```bash
git add backend/app/pipeline/orchestrator.py
git commit -m "refactor(pipeline): decouple scoring from quality filters"
```

---

### Task 2: Update Quality-Sensitive Screens

**Files:**
- Modify: `backend/app/screens/value.py`

- [ ] **Step 1: Update `screen_steady_compounders`**
Ensure it explicitly checks for `profitability_streak_passed`.
```python
# Modify query in screen_steady_compounders:
            TechnicalSignal.above_200ema == True,
            FundamentalCache.roce >= 0.15,
            FundamentalCache.dividend_consistency == True,
            FundamentalCache.profitability_streak_passed == True # ADD THIS
```

- [ ] **Step 2: Update `screen_undervalued_fundamentals`**
Ensure it explicitly checks for `de_check_passed` (and optionally `profitability_streak_passed` if intended).
```python
# Modify query in screen_undervalued_fundamentals:
            FundamentalCache.roe >= 0.15,
            FundamentalCache.ev_to_ebitda < 20,
            FundamentalCache.de_check_passed == True # ADD THIS
```

- [ ] **Step 3: Update `screen_low_debt_midcap`**
It already checks `de_check_passed`. Ensure it also checks `profitability_streak_passed` to maintain the original high-quality bar.
```python
# Modify query in screen_low_debt_midcap:
    results = db.query(FundamentalCache.symbol).filter(
        and_(
            FundamentalCache.de_check_passed == True,
            FundamentalCache.fcf_positive == True,
            FundamentalCache.profitability_streak_passed == True # ADD THIS
        )
    )
```

- [ ] **Step 4: Commit**
```bash
git add backend/app/screens/value.py
git commit -m "feat(screens): add explicit quality filters to value strategies"
```

---

### Task 3: Preserve Main Dashboard Quality

**Files:**
- Modify: `backend/app/routers/dashboard.py`

- [ ] **Step 1: Apply Quality Filters to Interactive Screener**
In `backend/app/routers/dashboard.py`, the `get_dashboard_results` endpoint should continue to serve only high-quality stocks by default. Add the quality conditions to the query.

```python
# Modify query_results join in get_dashboard_results:
    query_results = db.query(TechnicalSignal, Stock, FundamentalData, FundamentalCache).\
        join(Stock, TechnicalSignal.symbol == Stock.symbol).\
        # ... existing joins ...
        filter(TechnicalSignal.date == max_date).\
        filter(FundamentalCache.profitability_streak_passed == True).\ # ADD THIS
        filter(FundamentalCache.de_check_passed == True).all()         # ADD THIS
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/routers/dashboard.py
git commit -m "feat(api): maintain quality filters for main dashboard results"
```

---

### Task 4: Verification

- [ ] **Step 1: Verify all unit tests still pass**
Run: `cd backend && source venv/bin/activate && export PYTHONPATH=. && pytest`
- [ ] **Step 2: Commit**
```bash
# No changes usually, but if tests were updated:
git add .
git commit -m "test: verify pipeline decoupling"
```
