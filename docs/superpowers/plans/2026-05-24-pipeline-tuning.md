# Pipeline Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronize dashboard, screens, and scoring logic with backtest reality and improve pipeline resilience.

**Architecture:** Refactor hard filters into soft filters in the dashboard, ensure technical scoring runs even on fundamental fetch failures, and align RSI bounds and actionability checks across screens.

**Tech Stack:** Python, FastAPI, SQLAlchemy.

---

### Task 1: Dashboard Soft Filters

**Files:**
- Modify: `backend/app/routers/dashboard.py`

- [ ] **Step 1: Add `fundamental_filter` parameter to `get_dashboard_results`**

Update signature:
```python
def get_dashboard_results(
    response: Response,
    db: Session = Depends(get_db),
    offset: int = 0,
    limit: int = 50,
    sector: str = None,
    confluence: str = None,
    symbols: str = None,
    sort_by: str = "confluence",
    fundamental_filter: bool = True,  # New param
):
```

- [ ] **Step 2: Implement conditional filtering based on `fundamental_filter`**

Replace hard filters:
```python
    # 3. Base Query for filtering and counting
    query = db.query(Stock, FundamentalCache, confluence_sub.c.confluence_count).\
        join(confluence_sub, Stock.symbol == confluence_sub.c.symbol).\
        outerjoin(FundamentalCache, Stock.symbol == FundamentalCache.symbol)
    
    if fundamental_filter:
        query = query.filter(FundamentalCache.profitability_streak_passed == True).\
            filter(FundamentalCache.de_check_passed == True)
```

- [ ] **Step 3: Include `fundamental_quality` in the response**

Update `stocks_map` construction to include quality metadata.

### Task 2: Robust Scoring in Pipeline

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Update scoring loop to handle missing or failed fundamental cache**

Modify L420-422:
```python
                cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).first()

                # Even if cache fetch failed (version -1) or missing, we still score technically.
                # Pass cache=None to process_symbol so fund_score defaults to 0.
                scoring_cache = None
                if cache and cache.cache_version != -1:
                    scoring_cache = cache
```

- [ ] **Step 2: Add explicit documentation for Tier 1 threshold**

Add comment near L273 explaining the 40/70 score threshold.

### Task 3: RSI Bound Alignment

**Files:**
- Modify: `backend/app/screens/momentum.py`

- [ ] **Step 1: Lower RSI floor to 35 in momentum screens**

Update `TechnicalSignal.rsi >= 40` to `TechnicalSignal.rsi >= 35` in:
- `screen_ema_crossover_signals`
- `screen_volume_surge`
- `screen_actionable_entries`

### Task 4: Value Screen Actionability

**Files:**
- Modify: `backend/app/screens/value.py`

- [ ] **Step 1: Add actionability checks to value screens**

Add to `filter()` block in `screen_steady_compounders` and `screen_qarp`:
```python
            TechnicalSignal.is_bullish == True,
            TechnicalSignal.rsi >= 40,
            TechnicalSignal.rsi < 75,
            TechnicalSignal.ema_slope_20 > 0,
```

---
