# Frontend Named Screener Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the new `/api/screens` backend endpoints into the existing React frontend, adding a dedicated Screens page and enriching the existing Screener page with new filterable metrics.

**Architecture:** We will first fix core backend logic in the materializer to handle tuple results from screens. Then, we update the backend FastAPI routers to expose enriched metrics. We consolidate the frontend API client, ensuring all imports are fixed before deletion. Finally, we build the new Screens page and enhance the existing Screener page.

**Tech Stack:** Python (FastAPI, SQLAlchemy), React (Vite, React Router), CSS Variables.

---

### Task 0: Backend Core Logic Fixes

**Files:**
- Modify: `backend/app/screens/materializer.py`

- [ ] **Step 1: Fix tuple handling in `materialize_all_screens`**

Update the result processing loop in `backend/app/screens/materializer.py` to handle tuples, dicts, and objects.

```python
                for rank, item in enumerate(results, start=1):
                    # Handle tuples (symbol, score), dicts, or SQLAlchemy objects
                    if isinstance(item, tuple):
                        symbol = item[0]
                        score = item[1] if len(item) > 1 else 0.0
                        timeframe = 'D'
                    elif isinstance(item, dict):
                        symbol = item.get('symbol')
                        score = item.get('score', 0.0)
                        timeframe = item.get('timeframe', 'D')
                    else:
                        symbol = getattr(item, 'symbol', None)
                        score = getattr(item, 'entry_score', 0.0)
                        timeframe = getattr(item, 'timeframe', 'D')

                    if not symbol:
                        continue
```

- [ ] **Step 2: Run a dry-run check**
Verify the code is robust against `None` scores by using a default `0.0`.

- [ ] **Step 3: Commit**
```bash
git add backend/app/screens/materializer.py
git commit -m "fix(backend): handle tuple results in screen materializer"
```

---

### Task 1: Backend Router Updates for Enriched Fields

**Files:**
- Modify: `backend/app/routers/screens.py`
- Modify: `backend/app/routers/dashboard.py`

- [ ] **Step 1: Update `screens.py` to expose all required fields**
Modify `get_screen_results` in `backend/app/routers/screens.py`. Add all technical and fundamental fields to the result dictionary in both the DB-fetch and live-execution paths.

```python
results.append({
    "symbol": symbol,
    "name": stock.name,
    "rank": i + 1,
    "score": score,
    "sector": stock.sector,
    "market_cap": stock.market_cap,
    "rs_score": tech.rs_score if tech else None,
    "momentum_1m": tech.momentum_1m if tech else None,
    "momentum_3m": tech.momentum_3m if tech else None,
    "adx": tech.adx if tech else None,
    "ema_slope": tech.ema_slope_20 if tech else None,
    "pct_from_52w_high": tech.pct_from_52w_high if tech else None,
    "pct_from_52w_low": tech.pct_from_52w_low if tech else None,
    "week52_high": tech.week52_high if tech else None,
    "week52_low": tech.week52_low if tech else None,
    "pct_from_resistance": tech.pct_from_resistance if tech else None,
    "volume_breakout": tech.volume_breakout if tech else None,
    "above_200ema": tech.above_200ema if tech else None,
    "peg_ratio": fund.peg_ratio if fund else None,
    "ev_to_ebitda": fund.ev_to_ebitda if fund else None,
    "dividend_yield": fund.dividend_yield if fund else None,
    "roce": fund.roce if fund else None,
    "de_ratio": fund.de_ratio if fund else None,
    "fcf_positive": fund.fcf_positive if fund else None,
    "dividend_consistency": fund.dividend_consistency if fund else None,
    "market_cap_category": fund.market_cap_category if fund else None,
})
```

- [ ] **Step 2: Update `dashboard.py` to join `FundamentalCache`**
In `backend/app/routers/dashboard.py`, update `get_dashboard_results` to join `FundamentalCache` and include fallback logic for `roe`.

```python
# Join update
query_results = db.query(TechnicalSignal, Stock, FundamentalData, FundamentalCache).\
    join(Stock, TechnicalSignal.symbol == Stock.symbol).\
    outerjoin(latest_fund, Stock.symbol == latest_fund.c.symbol).\
    outerjoin(FundamentalData, (FundamentalData.symbol == latest_fund.c.symbol) & (FundamentalData.date == latest_fund.c.max_date)).\
    outerjoin(FundamentalCache, Stock.symbol == FundamentalCache.symbol).\
    filter(TechnicalSignal.date == max_date).all()

# Dict update
"roe": cache.roe if (cache and cache.roe is not None) else (fund.roe if fund else None),
```

- [ ] **Step 3: Commit**
```bash
git add backend/app/routers/screens.py backend/app/routers/dashboard.py
git commit -m "feat(backend): expose enriched fields in screens and dashboard routers"
```

---

### Task 2: API Client Consolidation & Import Fixes

**Files:**
- Modify: `frontend/src/api/client.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx` (and others)
- Delete: `frontend/src/api.js`

- [ ] **Step 1: Add new endpoints to `client.js`**
```javascript
export const getScreensList = () => apiClient.get('/screens');
export const getScreenBySlug = (slug, live = false) =>
  apiClient.get(`/screens/${slug}${live ? '?live=true' : ''}`);
```

- [ ] **Step 2: Update all imports**
Rename imports from `../api` to `../api/client` across the frontend.

- [ ] **Step 3: Delete `api.js` after verification**
```bash
rm frontend/src/api.js
```

- [ ] **Step 4: Commit**
```bash
git add .
git commit -m "refactor(frontend): consolidate api client and update imports"
```

---

### Task 3: Screen Components Implementation

**Files:**
- Create: `frontend/src/components/ScreenCard.css`
- Create: `frontend/src/components/ScreenCard.jsx`
- Create: `frontend/src/components/ScreenResultTable.jsx`

- [ ] **Step 1: Implement `ScreenCard` component and styles**
- [ ] **Step 2: Implement `ScreenResultTable` with column mapping**
- [ ] **Step 3: Commit**
```bash
git add frontend/src/components/
git commit -m "feat(frontend): add ScreenCard and ScreenResultTable components"
```

---

### Task 4: Screens Page Implementation

**Files:**
- Create: `frontend/src/pages/Screens.jsx`

- [ ] **Step 1: Implement `Screens.jsx` with category filtering and results fetching**
- [ ] **Step 2: Commit**
```bash
git add frontend/src/pages/Screens.jsx
git commit -m "feat(frontend): implement Named Screens page"
```

---

### Task 5: Screener Enhancements

**Files:**
- Modify: `frontend/src/pages/Screener.jsx`

- [ ] **Step 1: Add new filters and table columns to `Screener.jsx`**
- [ ] **Step 2: Commit**
```bash
git add frontend/src/pages/Screener.jsx
git commit -m "feat(frontend): enhance interactive screener with momentum and RS metrics"
```

---

### Task 6: Routing and Navigation

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/Navigation.jsx`

- [ ] **Step 1: Register `/screens` route and add Nav item**
- [ ] **Step 2: Final Verification**
Run dev server and verify all pages load and fetch data correctly.
- [ ] **Step 3: Commit**
```bash
git add frontend/src/App.jsx frontend/src/components/Navigation.jsx
git commit -m "feat(frontend): add Screens to navigation and routing"
```
