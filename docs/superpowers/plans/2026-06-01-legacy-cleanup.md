# Legacy Fundamental Code Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up legacy fundamental analysis "ghosts" (financial ratios, dead filters, and UI columns) while keeping Market Cap and Sector metadata.

**Architecture:** Surgical refactor of the dashboard router to strip financial metrics from the API response and a corresponding simplification of frontend components to remove obsolete columns and filters.

**Tech Stack:** Python (FastAPI, SQLAlchemy), React (Vite, Tailwind CSS).

---

### Task 1: Backend Router Refactor

**Files:**
- Modify: `backend/app/routers/dashboard.py`
- Test: `backend/tests/test_engine.py` (or existing dashboard tests)

- [ ] **Step 1: Update `get_dashboard_results` signature and initial logic**
    - Remove `fundamental_filter` parameter.
    - Remove the `sort_by == "pe"` logic block that joins `FundamentalData`.

```python
# backend/app/routers/dashboard.py

# ... in get_dashboard_results ...
def get_dashboard_results(
    response: Response,
    db: Session = Depends(get_db),
    offset: int = 0,
    limit: int = 50,
    sector: str = None,
    confluence: str = None,
    symbols: str = None,
    sort_by: str = "confluence",
    # Remove: fundamental_filter: bool = False,
):
    # Update cache key
    params_str = f"off:{offset}:lim:{limit}:sec:{sector}:conf:{confluence}:sym:{symbols}:sort:{sort_by}"
    cache_key = f"dashboard:screener_results:{params_str}"

    # ... remove the commented out if fundamental_filter block ...
    # ... remove the sort_by == "pe" block ...
```

- [ ] **Step 2: Simplify `stocks_map` and `enriched_data` structure**
    - Remove `fundamental_quality` object.
    - Reduce `fundamentals` to only `market_cap` and `market_cap_category`.
    - Stop fetching `all_funds` or simply stop using it to populate ratios.

```python
# backend/app/routers/dashboard.py

# ... inside get_dashboard_results reconstruction loop ...
    stocks_map = {
        stock.symbol: {
            "symbol": stock.symbol,
            "name": stock.name,
            "sector": stock.sector,
            "confluence_count": count,
            "close_price": None,
            "price_change_pct": None,
            # Remove fundamental_quality
            "timeframes": {},
            "fundamentals": {
                "market_cap": stock.market_cap,
                "market_cap_category": cache.market_cap_category if cache else None,
            },
        }
        for stock, cache, count in paged_stocks
    }

# ... remove the for fund in all_funds loop that populates pe, pb, roe, etc. ...
```

- [ ] **Step 3: Run existing tests to verify no regressions**
    - Run: `cd backend && pytest tests/test_engine.py` (or relevant dashboard tests)
    - Expected: PASS

- [ ] **Step 4: Commit backend changes**
    - Run: `git add backend/app/routers/dashboard.py && git commit -m "refactor(backend): remove legacy fundamental ratios from dashboard API"`

---

### Task 2: ScreenResultTable Cleanup

**Files:**
- Modify: `frontend/src/components/ScreenResultTable.jsx`

- [ ] **Step 1: Remove obsolete column metadata**
    - Delete `peg_ratio`, `ev_to_ebitda`, `dividend_yield`, `roce`, `de_ratio`, `fcf_positive`, `dividend_consistency`, `quality_tier` from `COLUMN_META`.

- [ ] **Step 2: Update `SCREEN_COLUMNS` presets**
    - Audit all presets and replace deleted columns with technical ones (e.g., `rs_score`, `rsi`) if needed.

- [ ] **Step 3: Commit frontend table changes**
    - Run: `git add frontend/src/components/ScreenResultTable.jsx && git commit -m "refactor(frontend): remove obsolete financial columns from ScreenResultTable"`

---

### Task 3: FilterBottomSheet Cleanup

**Files:**
- Modify: `frontend/src/components/FilterBottomSheet.jsx`

- [ ] **Step 1: Remove `fundamentalFilter` props**
    - Remove `fundamentalFilter` and `setFundamentalFilter` from the component arguments.

- [ ] **Step 2: Delete "Quality Filter" UI section**
    - Remove the `<section>` containing the "Quality Filter" header and the Strict/Show All buttons.

- [ ] **Step 3: Commit filter sheet changes**
    - Run: `git add frontend/src/components/FilterBottomSheet.jsx && git commit -m "refactor(frontend): remove Quality Filter from mobile filters"`

---

### Task 4: Dashboard Page Refactor

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Remove `fundamentalFilter` state and logic**
    - Delete `useState` for `fundamentalFilter`.
    - Remove `setFundamentalFilter` from `resetFilters`.

- [ ] **Step 2: Clean up `loadMore` and `useEffect` dependencies**
    - Remove `fundamentalFilter` from the dependency arrays and `fetchResults` parameters.

- [ ] **Step 3: Remove obsolete columns from `columns` definition**
    - Delete "Quality", "ROE %", and "P/E" column objects.

- [ ] **Step 4: Remove "Value (P/E)" sort option**
    - Remove the `{ value: 'pe', label: 'Value (P/E)' }` entry from the `Select` options.

- [ ] **Step 5: Delete Desktop "Quality Filter" UI**
    - Find the `ShieldCheck` icon and "Quality Filter" header within the desktop layout and remove the section.

- [ ] **Step 6: Update `handleToggleWatchlist`**
    - Simplify the `quality_tier` assignment if it's still being used, or remove it.

- [ ] **Step 7: Verify Frontend**
    - Run: `cd frontend && npm run dev`
    - Manually check the dashboard to ensure the table and filters look clean.

- [ ] **Step 8: Commit dashboard changes**
    - Run: `git add frontend/src/pages/Dashboard.jsx && git commit -m "refactor(frontend): remove legacy fundamental filters and columns from Dashboard"`
