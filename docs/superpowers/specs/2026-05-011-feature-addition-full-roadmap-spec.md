# Screener AI — Feature Additions Spec

**Version:** 1.0
**Scope:** 8 frontend/fullstack features across Dashboard, StockDetail, Discover, and shared components
**Purpose:** Implementation-ready specification for an AI coding agent

---

## Codebase Anchors (Read Before Implementing Anything)

The agent must understand these existing pieces before touching any file:

- **`GlobalSearch`** (`frontend/src/components/GlobalSearch.jsx`) — already implements a `Cmd+K` modal with overlay, input ref, keyboard listeners, and symbol filtering. It fetches from `/api/screener/results` and extracts `symbol` strings. **Feature F2 extends this file rather than creating a new one.**
- **`DataTable`** (`frontend/src/components/ui/DataTable.jsx`) — already has a `sortConfig` state, `requestSort`, and sort icons (`ArrowUp`, `ArrowDown`, `ArrowUpDown`). It sorts on `col.accessor(row)` or `row[col.key]`. **Feature F3 uses this component as-is** — `ScreenResultTable` needs to be deleted and replaced with `DataTable`.
- **`ScreenResultTable`** (`frontend/src/components/ScreenResultTable.jsx`) — a custom table that duplicates `DataTable`'s functionality but without sorting. It is used only in `Discover.jsx`. This file will be **deleted** as part of F3.
- **`useFetch`** (`frontend/src/hooks/useFetch.js`) — generic data hook. All new data fetching uses this hook. Do not write `useEffect + fetch` patterns from scratch.
- **`usePipeline`** (`frontend/src/hooks/usePipeline.js`) — already polls `/api/pipeline/latest` and exposes `stats` which contains `stocks_fetched`, `stocks_scored`, `tier1_count`. After Phase 1 implementation, it also exposes `is_stale` and `data_age_hours`.
- **`response_cache`** (`backend/app/core/cache.py`) — in-process singleton from Phase 1. New backend endpoints should use it where appropriate.
- **Score composition** — from `scorer.py`: Daily score = Technical (max 70) + Fundamental (max 30). Technical breakdown: EMA Alignment 20pts, MACD 20pts, RSI 15pts, Volume 15pts. Fundamental breakdown: PE 10pts, Pledge 5pts, ROE 5pts, ROCE 5pts, D/E 5pts. The `TechnicalSignal` model stores `entry_score` (combined), but does NOT store sub-scores individually. The breakdown must be inferred from the signal's indicator fields.
- **`PipelineRun`** model — has `stocks_fetched`, `stocks_scored`, `tier1_count`, `tier2_count`. Does NOT have a `total_symbols` field. Total can be inferred as `tier1_count` being the denominator for Tier 1 progress, and `tier2_count` for scoring progress.
- **`ScreenResultTable` column definitions** — `SCREEN_COLUMNS` and `COLUMN_META` objects are defined separately in both `ScreenResultTable.jsx` and `Discover.jsx` with slight differences. After F3, the canonical definition lives only in `Discover.jsx` (passed to `DataTable`).
- **CSS variables** — theme system uses `--color-bullish`, `--color-bearish`, `--color-primary`, `--color-text`, `--color-text-muted`, `--color-bg-secondary`, `--color-bg-elevated`, `--color-border`, `--radius-sm`, `--radius-md`. Never use hardcoded hex colors.

---

## Feature F1: "What Changed Today" Banner

### What It Is

A collapsible section at the top of the Dashboard (below the summary bar, above the filter panel) showing stocks where technical signals changed since the previous pipeline run. Specifically: `is_bullish` flipped true→false or false→true on the Daily timeframe, or `confluence_count` changed by ±1 or more.

### Backend Changes

**New endpoint:** `GET /api/dashboard/changes`

Location: `backend/app/routers/dashboard.py`

```python
@router.get("/dashboard/changes")
def get_signal_changes(db: Session = Depends(get_db)):
```

**Logic:**

1. Find the two most recent distinct dates in `TechnicalSignal` for `timeframe = 'D'`:
   ```sql
   SELECT DISTINCT DATE(date) FROM technical_signals
   WHERE timeframe = 'D'
   ORDER BY DATE(date) DESC
   LIMIT 2
   ```
   If fewer than 2 dates exist, return `{"changes": [], "as_of": null, "prev_date": null}`.

2. For each symbol, get the `is_bullish` value on both dates (Daily timeframe only).

3. Compute changes:
   - `newly_bullish`: `is_bullish` was False on prev date, True on latest date
   - `turned_bearish`: `is_bullish` was True on prev date, False on latest date
   - `confluence_improved`: confluence_count increased (requires joining W and M signals too)
   - `confluence_dropped`: confluence_count decreased

4. For each changed symbol, also return: `symbol`, `name` (from Stock), `close_price`, `price_change_pct`, `entry_score` from the latest signal.

5. Limit to 20 results total (10 bullish flips + 10 bearish flips max). Sort bullish flips first, then bearish.

**Response shape:**
```json
{
  "as_of": "2026-05-09",
  "prev_date": "2026-05-08",
  "changes": [
    {
      "symbol": "RELIANCE",
      "name": "Reliance Industries",
      "change_type": "newly_bullish",
      "prev_score": 42.0,
      "curr_score": 78.0,
      "close_price": 2910.5,
      "price_change_pct": 1.8
    }
  ]
}
```

**Caching:** Cache with key `"dashboard_changes"`, TTL 600 seconds (10 minutes). Invalidated by `response_cache.invalidate()` in orchestrator on pipeline completion (already wired from Phase 1).

**New API client function** in `frontend/src/api/client.js`:
```js
export const getDashboardChanges = () => apiClient.get('/dashboard/changes');
```

### Frontend Changes

**New component:** `frontend/src/components/ChangeBanner.jsx`

Props: `{ changes: array, asOf: string, prevDate: string, loading: bool }`

Structure:
```jsx
<div className="change-banner card">
  <button className="change-banner-toggle" onClick={toggle}>
    <Zap size={16} />
    <span>Signal Changes Since {prevDate}</span>
    <span className="change-count-pill">{changes.length}</span>
    <ChevronDown size={14} className={isOpen ? 'rotated' : ''} />
  </button>

  {isOpen && (
    <div className="change-banner-body">
      <div className="change-group">
        <span className="change-group-label bullish">↑ Turned Bullish</span>
        {newlyBullish.map(c => <ChangeChip key={c.symbol} item={c} />)}
      </div>
      <div className="change-group">
        <span className="change-group-label bearish">↓ Turned Bearish</span>
        {turnedBearish.map(c => <ChangeChip key={c.symbol} item={c} />)}
      </div>
    </div>
  )}
</div>
```

`ChangeChip` is an internal sub-component (same file):
```jsx
const ChangeChip = ({ item }) => (
  <Link to={`/stocks/${item.symbol}`} className="change-chip">
    <span className="chip-symbol">{item.symbol}</span>
    <span className="chip-score">{item.curr_score?.toFixed(0)}</span>
    <span className={`chip-change ${item.price_change_pct >= 0 ? 'positive' : 'negative'}`}>
      {item.price_change_pct >= 0 ? '+' : ''}{item.price_change_pct?.toFixed(1)}%
    </span>
  </Link>
)
```

Default state: **collapsed** (isOpen = false). Use `localStorage.getItem('changeBannerOpen')` to persist preference across page loads.

**New CSS:** `frontend/src/components/ChangeBanner.css`

Key styles:
- `.change-banner`: `border-left: 3px solid var(--color-primary)` to visually distinguish from summary bar
- `.change-count-pill`: small rounded badge, `background: var(--color-primary)`, white text
- `.change-group-label.bullish`: `color: var(--color-bullish)`
- `.change-group-label.bearish`: `color: var(--color-bearish)`
- `.change-chip`: `display: inline-flex`, `gap: 6px`, `padding: 4px 10px`, `border-radius: var(--radius-sm)`, `background: var(--color-bg-elevated)`, `text-decoration: none`
- `.rotated`: `transform: rotate(180deg)`, `transition: transform 0.2s`
- If `changes.length === 0`, render a muted "No signal changes since last run." inline instead of the groups.

**Usage in `Dashboard.jsx`:**

```jsx
// Add import
import ChangeBanner from '../components/ChangeBanner';
import { getDashboardChanges } from '../api/client';

// Add fetch (near other useFetch calls)
const { data: changesData, loading: changesLoading } = useFetch(getDashboardChanges);

// Render: insert between summary-bar and filters-container
<ChangeBanner
  changes={changesData?.changes || []}
  asOf={changesData?.as_of}
  prevDate={changesData?.prev_date}
  loading={changesLoading}
/>
```

Do not render `ChangeBanner` during the initial skeleton loading state (when `stocksLoading && !hasData`).

---

## Feature F2: Stock Search / Command Palette

### What It Is

The `GlobalSearch` component already exists and is nearly complete. It opens on `Cmd+K`, has an overlay, an input, and filters symbols. The gaps to fix:

1. It fetches from `/api/screener/results` which only returns **scored stocks** (stocks that passed Tier 1+2 screening). Unscored or newly-listed stocks are invisible.
2. It shows only `symbol` in the result list — no company name.
3. There is no keyboard navigation (arrow keys, Enter to select).
4. On mobile it appears as a trigger in the mobile header but the modal doesn't adapt to viewport height.

### Backend Changes

**New endpoint:** `GET /api/stocks/search?q=RELIANCE`

Location: `backend/app/routers/stocks.py`

```python
@router.get("/stocks/search")
def search_stocks(q: str = "", db: Session = Depends(get_db)):
```

Logic:
1. If `q` is empty or fewer than 2 characters, return `[]`.
2. Query `Stock` table: `WHERE symbol ILIKE '%{q}%' OR name ILIKE '%{q}%'`. Use SQLAlchemy `ilike`. Limit 15 results.
3. Order: exact symbol match first (`symbol == q.upper()`), then symbol starts-with, then name contains.
4. Return: `[{ "symbol": str, "name": str, "sector": str }]`

No caching on this endpoint — queries are cheap (Stock table is small, ~2000 rows) and query strings vary too much to cache effectively.

**New API client function:**
```js
export const searchStocks = (q) => apiClient.get(`/stocks/search?q=${encodeURIComponent(q)}`);
```

### Frontend Changes

**Modify `frontend/src/components/GlobalSearch.jsx`** — do not create a new file.

**Change 1: Use the new search endpoint instead of pre-loading all symbols**

Remove the `useEffect` that calls `fetchResults()` and stores all symbols in state. Replace with debounced search:

```jsx
// Remove:
const [symbols, setSymbols] = useState([]);
// useEffect that calls fetchResults()...

// Add:
const [results, setResults] = useState([]);  // [{symbol, name, sector}]
const debounceRef = useRef(null);

// In the onChange handler for the input:
const handleQueryChange = (e) => {
  const val = e.target.value;
  setQuery(val);
  clearTimeout(debounceRef.current);
  if (val.length < 2) { setResults([]); return; }
  debounceRef.current = setTimeout(() => {
    searchStocks(val).then(res => setResults(res.data)).catch(() => {});
  }, 200); // 200ms debounce
};
```

**Change 2: Show name in results**

```jsx
// Replace result-item render:
<div key={s.symbol} className="result-item" onClick={() => handleSelect(s.symbol)}>
  <div className="result-main">
    <span className="result-symbol">{s.symbol}</span>
    <span className="result-name text-muted">{s.name}</span>
  </div>
  <span className="result-sector text-xs text-muted">{s.sector}</span>
</div>
```

**Change 3: Keyboard navigation**

Add `selectedIndex` state (default -1). Wire `ArrowUp`, `ArrowDown`, `Enter` in the existing `keydown` handler:

```jsx
// Inside handleKeyDown (already exists for Cmd+K / Escape):
if (isOpen) {
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    setSelectedIndex(i => Math.min(i + 1, results.length - 1));
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    setSelectedIndex(i => Math.max(i - 1, 0));
  }
  if (e.key === 'Enter' && selectedIndex >= 0) {
    e.preventDefault();
    handleSelect(results[selectedIndex].symbol);
  }
}
```

Reset `selectedIndex` to -1 on query change.

Apply `className={`result-item ${i === selectedIndex ? 'selected' : ''}`}` to each result row. Add CSS: `.result-item.selected { background: var(--color-bg-elevated); }`.

**Change 4: Show "No results" state correctly**

The existing `filtered.length > 0` check becomes `results.length > 0`. Add a loading state: while `query.length >= 2` and `results` is empty (and debounce hasn't fired yet), show a spinner or "Searching..." text rather than "No stocks found".

**CSS additions to `GlobalSearch.css`:**
```css
.result-symbol { font-weight: 600; font-size: 0.9rem; }
.result-name   { font-size: 0.8rem; margin-left: 8px; }
.result-main   { display: flex; align-items: baseline; }
.result-sector { font-size: 0.75rem; }
.result-item.selected { background: var(--color-bg-elevated); }
```

**Remove** the `useMemo` for `filtered` — it's no longer needed since results come from the API.

**Do not change** the trigger button appearance, the overlay, the Cmd+K keyboard shortcut, or the `navigate` call — these all work correctly.

---

## Feature F3: Sortable Columns in ScreenResultTable

### What It Is

`ScreenResultTable.jsx` is a hand-rolled table that cannot sort. `DataTable.jsx` is a fully-featured sortable table. The fix is to delete `ScreenResultTable` and wire `DataTable` into `Discover.jsx` using the existing `COLUMN_META` definitions already present there.

### Why No Backend Changes

All data is already fetched. Sorting is client-side only.

### Frontend Changes

**Step 1: Delete `frontend/src/components/ScreenResultTable.jsx`**

This file is only imported in `Discover.jsx`. It will not be used anywhere after this change.

**Step 2: Modify `frontend/src/pages/Discover.jsx`**

Remove the import of `ScreenResultTable`. The `DataTable` import already exists in `Discover.jsx`.

The `COLUMN_META` object in `Discover.jsx` already defines columns with `sortable: true` and `accessor` functions. However, the `score` column's accessor needs to be correct for screen results (which come from `/screens/{slug}`, not from `/screener/results`):

```js
// In Discover.jsx COLUMN_META, fix the score accessor:
score: {
  label: 'Score',
  key: 'score',
  sortable: true,
  accessor: (row) => row.score ?? row.timeframes?.D?.score ?? 0,
  render: (v) => v != null ? v.toFixed(1) : '—'
},
```

Screen results from the screen endpoint have a top-level `score` field (set by the materializer from `score_used`). The `timeframes?.D?.score` fallback handles the interactive tab which uses `/screener/results` data.

**Step 3: Replace `ScreenResultTable` usage with `DataTable`**

In `Discover.jsx`, the `selectedSlug` results section currently renders:
```jsx
<DataTable
  columns={getColumnsForSlug(selectedSlug)}
  data={strategyResults}
  loading={loadingStrategyResults}
  initialSort={{ key: 'score', direction: 'desc' }}
/>
```

This is already using `DataTable`. Verify this is the case — if `ScreenResultTable` is still present in the JSX, replace it. The `getColumnsForSlug` helper maps slug → column key array → `COLUMN_META` entries, which is already wired correctly.

**Step 4: Verify `DataTable` handles missing `accessor`**

In `DataTable.jsx`, the sort logic is:
```js
const accessor = col?.accessor || (row => row[sortConfig.key]);
```

This is correct. Columns without an explicit `accessor` fall back to `row[col.key]`. No changes needed to `DataTable.jsx`.

**Step 5: Confirm `ScreenResultTable` is not imported anywhere else**

Search for `ScreenResultTable` imports across the codebase. It should only appear in `Discover.jsx`. If found elsewhere, update those imports to use `DataTable` with equivalent column definitions.

---

## Feature F4: Score Breakdown in StockDetail

### What It Is

A visual breakdown of how the 100-point score is composed, shown in the StockDetail side column below the Technical Insights card. For Daily timeframe only (Weekly/Monthly are binary 0 or 70, not interesting to break down).

### No Backend Changes Required

All necessary indicator values are already returned by `GET /api/stocks/{symbol}` in the `scores.D` object: `rsi`, `ema_signal`, `volume_signal`, `rsi_signal`, `macd`, `adx`. The sub-scores must be inferred client-side from these fields.

### Score Inference Logic

This logic must be implemented in the frontend as a pure function. It mirrors the rules in `scorer.py`:

```js
// frontend/src/utils/scoreBreakdown.js  (new file)

/**
 * Infers the sub-score breakdown from a Daily signal object.
 * Returns an array of { label, earned, max, signal } objects.
 *
 * All inference is approximate — we don't store sub-scores in the DB.
 * The source of truth for rules is backend/app/pipeline/scorer.py.
 */
export function inferScoreBreakdown(dailySignal, fundamentals) {
  if (!dailySignal) return [];

  const breakdown = [];

  // Technical sub-scores (max 70)

  // EMA Alignment: 20 pts — bullish if ema_signal === 'bullish'
  breakdown.push({
    label: 'EMA Alignment',
    earned: dailySignal.ema_signal === 'bullish' ? 20 : 0,
    max: 20,
    signal: dailySignal.ema_signal || 'neutral',
    category: 'technical'
  });

  // MACD: 20 pts — macd > 0 is a proxy (actual rule: macd > signal AND macd > 0)
  // We don't have signal_line in the API response, so use ema_signal as a proxy
  // since both require bullish alignment. If ema_signal is bullish, MACD likely earned too.
  // Be conservative: only award if ema_signal === 'bullish' (they are correlated in scorer.py)
  breakdown.push({
    label: 'MACD',
    earned: dailySignal.ema_signal === 'bullish' ? 20 : 0,
    max: 20,
    signal: dailySignal.macd > 0 ? 'bullish' : 'bearish',
    category: 'technical'
  });

  // RSI: 15 pts — use rsi_signal field
  const rsiEarned =
    dailySignal.rsi_signal === 'bullish_recovery' ? 15 :
    dailySignal.rsi_signal === 'bullish_crossing' ? 15 :
    dailySignal.rsi_signal === 'bullish_strong'   ? 5  : 0;
  breakdown.push({
    label: 'RSI',
    earned: rsiEarned,
    max: 15,
    signal: dailySignal.rsi_signal || 'neutral',
    category: 'technical'
  });

  // Volume: 15 pts — use volume_signal field
  breakdown.push({
    label: 'Volume',
    earned: dailySignal.volume_signal === 'bullish' ? 15 : 0,
    max: 15,
    signal: dailySignal.volume_signal || 'neutral',
    category: 'technical'
  });

  // Fundamental sub-scores (max 30) — inferred from fundamentals object
  // PE: max 10 pts
  const pe = fundamentals?.pe;
  const peEarned = pe == null ? 0 : pe < 25 ? 10 : pe < 40 ? 6 : pe < 60 ? 2 : 0;
  breakdown.push({
    label: 'P/E Ratio',
    earned: peEarned,
    max: 10,
    signal: pe ? `PE ${pe.toFixed(1)}` : 'no data',
    category: 'fundamental'
  });

  // ROE: max 5 pts (roe from fundamentals, stored as decimal e.g. 0.15)
  const roe = fundamentals?.roe;
  const roeEarned = roe == null ? 0 : roe > 0.15 ? 5 : roe > 0.10 ? 2 : 0;
  breakdown.push({
    label: 'ROE',
    earned: roeEarned,
    max: 5,
    signal: roe ? `${(roe * 100).toFixed(1)}%` : 'no data',
    category: 'fundamental'
  });

  // ROCE: max 5 pts — not in StockDetail fundamentals response currently
  // Include with earned=0 and signal='no data' so the bar still renders
  breakdown.push({
    label: 'ROCE',
    earned: 0,  // not available in current API response
    max: 5,
    signal: 'no data',
    category: 'fundamental'
  });

  // Pledge: max 5 pts — not in StockDetail response
  breakdown.push({
    label: 'Pledge',
    earned: 0,
    max: 5,
    signal: 'no data',
    category: 'fundamental'
  });

  // D/E: max 5 pts
  const de = fundamentals?.debt_equity;
  const deEarned = de == null ? 0 : de < 0.5 ? 5 : de < 1.0 ? 2 : 0;
  breakdown.push({
    label: 'Debt/Equity',
    earned: deEarned,
    max: 5,
    signal: de != null ? `D/E ${de.toFixed(2)}` : 'no data',
    category: 'fundamental'
  });

  return breakdown;
}
```

**Add a note in the component** (via a small info icon + tooltip or muted text): "Sub-scores are inferred from indicator fields. Pledge and ROCE data require a cache refresh." This prevents confusion when those rows show 0.

### Frontend Changes

**New component:** `frontend/src/components/ScoreBreakdown.jsx`

Props: `{ breakdown: array, totalScore: number }`

```jsx
import './ScoreBreakdown.css';

const ScoreBreakdown = ({ breakdown, totalScore }) => {
  const technical = breakdown.filter(b => b.category === 'technical');
  const fundamental = breakdown.filter(b => b.category === 'fundamental');

  return (
    <div className="score-breakdown">
      <div className="breakdown-total">
        <span className="breakdown-total-label">Total Score</span>
        <span className="breakdown-total-value">{totalScore?.toFixed(1)}</span>
        <span className="breakdown-total-max">/ 100</span>
      </div>

      <div className="breakdown-section">
        <div className="breakdown-section-label">Technical <span className="muted">(max 70)</span></div>
        {technical.map(item => <BreakdownRow key={item.label} item={item} />)}
      </div>

      <div className="breakdown-section">
        <div className="breakdown-section-label">Fundamental <span className="muted">(max 30)</span></div>
        {fundamental.map(item => <BreakdownRow key={item.label} item={item} />)}
      </div>

      <p className="breakdown-disclaimer">
        * Pledge and ROCE values may show 0 if cache is outdated.
      </p>
    </div>
  );
};

const BreakdownRow = ({ item }) => {
  const pct = item.max > 0 ? (item.earned / item.max) * 100 : 0;
  const isZero = item.earned === 0;

  return (
    <div className="breakdown-row">
      <div className="breakdown-row-label">{item.label}</div>
      <div className="breakdown-bar-container">
        <div
          className={`breakdown-bar-fill ${isZero ? 'zero' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="breakdown-row-pts">
        <span className={isZero ? 'muted' : 'earned'}>{item.earned}</span>
        <span className="muted">/{item.max}</span>
      </div>
      <div className="breakdown-row-signal muted">{item.signal}</div>
    </div>
  );
};
```

**New CSS:** `frontend/src/components/ScoreBreakdown.css`

```css
.score-breakdown { display: flex; flex-direction: column; gap: 16px; }
.breakdown-total { display: flex; align-items: baseline; gap: 6px; margin-bottom: 4px; }
.breakdown-total-label { font-size: 0.75rem; color: var(--color-text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
.breakdown-total-value { font-size: 1.8rem; font-weight: 700; color: var(--color-primary); }
.breakdown-total-max { font-size: 0.9rem; color: var(--color-text-muted); }
.breakdown-section { display: flex; flex-direction: column; gap: 8px; }
.breakdown-section-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text-muted); margin-bottom: 4px; }
.breakdown-row { display: grid; grid-template-columns: 90px 1fr 44px 80px; align-items: center; gap: 8px; }
.breakdown-row-label { font-size: 0.8rem; }
.breakdown-bar-container { height: 6px; background: var(--color-bg-elevated); border-radius: 3px; overflow: hidden; }
.breakdown-bar-fill { height: 100%; background: var(--color-primary); border-radius: 3px; transition: width 0.4s ease; }
.breakdown-bar-fill.zero { background: var(--color-bg-elevated); }
.breakdown-row-pts { font-size: 0.8rem; text-align: right; }
.earned { color: var(--color-primary); font-weight: 600; }
.muted { color: var(--color-text-muted); }
.breakdown-row-signal { font-size: 0.7rem; color: var(--color-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.breakdown-disclaimer { font-size: 0.7rem; color: var(--color-text-muted); margin: 0; font-style: italic; }
```

**Usage in `StockDetail.jsx`:**

```jsx
import ScoreBreakdown from '../components/ScoreBreakdown';
import { inferScoreBreakdown } from '../utils/scoreBreakdown';

// Inside the component, derive breakdown:
const breakdown = inferScoreBreakdown(dailyScore, fundamentals);

// Add as a new card in the side-col, after the Fundamental Data card:
<div className="score-card">
  <h3>Score Breakdown</h3>
  <ScoreBreakdown breakdown={breakdown} totalScore={dailyScore?.score} />
</div>
```

**Also update `GET /api/stocks/{symbol}` response** to include `roce` and `pledged_percent` in fundamentals — these are already in `FundamentalCache` and `FundamentalData` but not currently returned by `get_stock_detail`:

```python
# In backend/app/routers/stocks.py, in get_stock_detail:
fundamentals = {
    "pe": fund_data.pe if fund_data else None,
    "roe": fund_cache.roe if fund_cache else (fund_data.roe if fund_data else None),
    "roce": fund_cache.roce if fund_cache else None,           # ADD THIS
    "pledged_percent": fund_data.pledged_percent if fund_data else None,  # ADD THIS
    "debt_equity": fund_cache.de_ratio if fund_cache else (fund_data.debt_equity if fund_data else None),
    "sector": fund_cache.sector if fund_cache else (stock.sector if stock else None),
    "eps_growth": fund_data.eps_growth if fund_data else None,
    "market_cap": fund_data.market_cap if fund_data else (stock.market_cap if stock else None)
}
```

Update `scoreBreakdown.js` to use the now-available `roce` and `pledged_percent` values once the API returns them.

---

## Feature F5: Watchlist

### What It Is

A star icon on each stock card and table row. Starred stocks are saved to `localStorage` as a JSON array of symbols. A "Watchlist" filter chip on the Dashboard shows only starred stocks. No backend changes — this is purely client-side state.

### Frontend Changes

**New hook:** `frontend/src/hooks/useWatchlist.js`

```js
import { useState, useCallback } from 'react';

const STORAGE_KEY = 'screener_watchlist';

export const useWatchlist = () => {
  const [watchlist, setWatchlist] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch {
      return new Set();
    }
  });

  const toggle = useCallback((symbol) => {
    setWatchlist(prev => {
      const next = new Set(prev);
      if (next.has(symbol)) {
        next.delete(symbol);
      } else {
        next.add(symbol);
      }
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]));
      } catch {}
      return next;
    });
  }, []);

  const isWatched = useCallback((symbol) => watchlist.has(symbol), [watchlist]);
  const clear = useCallback(() => {
    setWatchlist(new Set());
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  return { watchlist, toggle, isWatched, count: watchlist.size, clear };
};
```

**New component:** `frontend/src/components/WatchlistStar.jsx`

```jsx
import { Star } from 'lucide-react';
import './WatchlistStar.css';

const WatchlistStar = ({ symbol, isWatched, onToggle }) => (
  <button
    className={`watchlist-star ${isWatched ? 'watched' : ''}`}
    onClick={(e) => { e.preventDefault(); e.stopPropagation(); onToggle(symbol); }}
    title={isWatched ? 'Remove from watchlist' : 'Add to watchlist'}
    aria-label={isWatched ? 'Remove from watchlist' : 'Add to watchlist'}
  >
    <Star size={16} fill={isWatched ? 'currentColor' : 'none'} />
  </button>
);

export default WatchlistStar;
```

`e.preventDefault()` and `e.stopPropagation()` are critical — both `StockCard` and table rows are wrapped in `<Link>` components, and the click must not navigate.

```css
/* frontend/src/components/WatchlistStar.css */
.watchlist-star {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  transition: color 0.15s, transform 0.15s;
}
.watchlist-star:hover { color: var(--color-primary); transform: scale(1.15); }
.watchlist-star.watched { color: var(--color-primary); }
```

**Modify `StockCard.jsx`:**

```jsx
import WatchlistStar from './WatchlistStar';

// Add prop: onToggleWatch, isWatched
// In card-top div, add star next to symbol:
<div className="symbol-row">
  <span className="stock-symbol">{symbol.replace('.NS', '')}</span>
  <span className="sector-tag">{sector}</span>
  <WatchlistStar symbol={symbol} isWatched={isWatched} onToggle={onToggleWatch} />
</div>
```

**Modify `Dashboard.jsx`:**

```jsx
import { useWatchlist } from '../hooks/useWatchlist';
import WatchlistStar from '../components/WatchlistStar';

const { toggle, isWatched, count } = useWatchlist();

// Add 'watchlist' option to confluence filter chips:
{['all', 'watchlist', '3', '2+'].map(c => (
  <label key={c} className={`radio-label ${confluenceFilter === c ? 'active' : ''}`}>
    <input type="radio" name="confluence" value={c} checked={confluenceFilter === c}
      onChange={(e) => setConfluenceFilter(e.target.value)} />
    {c === 'all' ? 'All Stocks'
      : c === 'watchlist' ? `Watchlist (${count})`
      : c === '3' ? '3/3 Only'
      : '2/3+'}
  </label>
))}

// Update filteredStocks useMemo to handle 'watchlist':
.filter(stock => {
  if (confluenceFilter === 'watchlist') return isWatched(stock.symbol);
  if (confluenceFilter === '3') return stock.confluence_count === 3;
  if (confluenceFilter === '2+') return stock.confluence_count >= 2;
  return true;
})
```

Pass `onToggleWatch={toggle}` and `isWatched={isWatched(stock.symbol)}` to each `StockCard`.

**For the table view (`DataTable`):** Add a star column as the first column in the `columns` array defined in `Dashboard.jsx`:

```js
{
  key: 'watchlist',
  label: '★',
  sortable: false,
  render: (_, row) => (
    <WatchlistStar
      symbol={row.symbol}
      isWatched={isWatched(row.symbol)}
      onToggle={toggle}
    />
  )
}
```

**FilterBottomSheet.jsx:** Add the Watchlist chip to the mobile confluence filter group alongside `all`, `3`, `2+`. Pass `count` as a prop.

---

## Feature F6: Export CSV

### What It Is

A "Download CSV" button on `ScreenResultTable` (now `DataTable` after F3) in `Discover.jsx` that exports the currently visible results using `papaparse`. One button, ~10 lines of logic.

### Why No Backend Changes

Data is already in the frontend. `papaparse` is already listed as an available library in the artifact environment and is used in the existing `Discover.jsx` dependencies.

### Frontend Changes

**New utility:** `frontend/src/utils/exportCsv.js`

```js
import Papa from 'papaparse';

/**
 * Flattens a screen result row into a plain object for CSV export.
 * Handles nested fields that DataTable renders via accessor functions.
 */
function flattenRow(row, columns) {
  const flat = {};
  for (const col of columns) {
    const rawVal = col.accessor ? col.accessor(row) : row[col.key];
    // Strip JSX renders — use the raw value, not the render output
    flat[col.label] = rawVal ?? '';
  }
  return flat;
}

export function downloadCsv(rows, columns, filename = 'screener-export.csv') {
  const flatRows = rows.map(r => flattenRow(r, columns));
  const csv = Papa.unparse(flatRows);
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
```

**Modify `Discover.jsx`:**

In the `results-card` header, next to the "Live Mode" toggle button, add:

```jsx
import { Download } from 'lucide-react';
import { downloadCsv } from '../utils/exportCsv';

// In the card-header of the strategies results section:
<button
  className="export-btn"
  onClick={() => downloadCsv(
    strategyResults,
    getColumnsForSlug(selectedSlug).filter(c => c.key !== 'symbol'),  // exclude Link columns
    `${selectedSlug}-${new Date().toISOString().split('T')[0]}.csv`
  )}
  disabled={strategyResults.length === 0}
  title="Export to CSV"
>
  <Download size={14} />
  CSV
</button>
```

The filename will be e.g. `momentum-monsters-2026-05-09.csv`.

**CSS for export button** — add to existing `Dashboard.css`:
```css
.export-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-elevated);
  color: var(--color-text);
  cursor: pointer;
  font-size: 0.8rem;
}
.export-btn:hover { border-color: var(--color-primary); }
.export-btn:disabled { opacity: 0.4; cursor: not-allowed; }
```

**Also add to interactive tab** in `Discover.jsx` above the interactive `DataTable`:
```jsx
<button className="export-btn" onClick={() => downloadCsv(filteredStocks, getColumnsForSlug('_default'))}>
  <Download size={14} /> CSV
</button>
```

---

## Feature F7: Pagination

### What It Is

Page size controls (25 / 50 / 100) and prev/next navigation on the Dashboard table view and the Discover results tables. Not needed for grid view (cards render fine at 100+). Virtual scrolling is out of scope — simple pagination is sufficient.

### Why No Backend Changes

The Dashboard fetches all scored stocks in one call (currently ~200–400 after filters). Pagination is client-side slice only. Screen results are already limited to ~50 rows server-side. So the main beneficiary is the Dashboard table view.

### Frontend Changes

**New component:** `frontend/src/components/ui/Pagination.jsx`

```jsx
import { ChevronLeft, ChevronRight } from 'lucide-react';
import './Pagination.css';

const PAGE_SIZE_OPTIONS = [25, 50, 100];

const Pagination = ({ total, page, pageSize, onPageChange, onPageSizeChange }) => {
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1 && total <= PAGE_SIZE_OPTIONS[0]) return null;

  return (
    <div className="pagination">
      <div className="page-size-controls">
        <span className="pagination-label">Rows:</span>
        {PAGE_SIZE_OPTIONS.map(size => (
          <button
            key={size}
            className={`page-size-btn ${pageSize === size ? 'active' : ''}`}
            onClick={() => { onPageSizeChange(size); onPageChange(1); }}
          >
            {size}
          </button>
        ))}
      </div>

      <div className="page-nav">
        <span className="pagination-info">
          {((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, total)} of {total}
        </span>
        <button
          className="page-btn"
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1}
        >
          <ChevronLeft size={16} />
        </button>
        <button
          className="page-btn"
          onClick={() => onPageChange(page + 1)}
          disabled={page === totalPages}
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
};

export default Pagination;
```

```css
/* frontend/src/components/ui/Pagination.css */
.pagination { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; gap: 16px; flex-wrap: wrap; }
.page-size-controls { display: flex; align-items: center; gap: 6px; }
.pagination-label { font-size: 0.8rem; color: var(--color-text-muted); }
.page-size-btn { background: var(--color-bg-elevated); border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 4px 10px; font-size: 0.8rem; cursor: pointer; color: var(--color-text); }
.page-size-btn.active { border-color: var(--color-primary); color: var(--color-primary); font-weight: 600; }
.page-nav { display: flex; align-items: center; gap: 8px; }
.pagination-info { font-size: 0.8rem; color: var(--color-text-muted); }
.page-btn { background: var(--color-bg-elevated); border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 4px 8px; cursor: pointer; color: var(--color-text); display: flex; align-items: center; }
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.page-btn:not(:disabled):hover { border-color: var(--color-primary); }
```

**Modify `Dashboard.jsx`:**

```jsx
import Pagination from '../components/ui/Pagination';

// Add state:
const [page, setPage] = useState(1);
const [pageSize, setPageSize] = useState(50);

// Reset to page 1 when filters change:
useEffect(() => { setPage(1); }, [confluenceFilter, selectedSectors]);

// Paginated slice (after filteredStocks useMemo):
const paginatedStocks = useMemo(() => {
  const start = (page - 1) * pageSize;
  return filteredStocks.slice(start, start + pageSize);
}, [filteredStocks, page, pageSize]);

// In table view, render paginatedStocks instead of filteredStocks:
<DataTable columns={columns} data={paginatedStocks} ... />

// Render Pagination below the DataTable (only in table view):
{viewMode === 'table' && (
  <Pagination
    total={filteredStocks.length}
    page={page}
    pageSize={pageSize}
    onPageChange={setPage}
    onPageSizeChange={setPageSize}
  />
)}
```

Grid view renders all `filteredStocks` without pagination (cards are lightweight enough). Do NOT paginate the grid view.

**Modify `Discover.jsx`** — add pagination to the strategies results table only if `strategyResults.length > 25`:

```jsx
const [discoverPage, setDiscoverPage] = useState(1);
const [discoverPageSize, setDiscoverPageSize] = useState(25);

// Reset on slug change:
useEffect(() => { setDiscoverPage(1); }, [selectedSlug]);

const paginatedStrategyResults = useMemo(() => {
  const start = (discoverPage - 1) * discoverPageSize;
  return strategyResults.slice(start, start + discoverPageSize);
}, [strategyResults, discoverPage, discoverPageSize]);

// Pass paginatedStrategyResults to DataTable instead of strategyResults
// Render Pagination below the DataTable
```

---

## Feature F8: Pipeline Progress Bar

### What It Is

A thin progress bar below the "Pipeline Running" status badge in the Dashboard summary bar, showing `stocks_fetched / estimated_total` as a percentage. When the pipeline is not running, the bar is hidden.

### Backend Changes

**Add `total_symbols` to `PipelineRun`** — currently the total is not stored anywhere. When the pipeline starts, it calls `get_nse_symbols()` which returns the full list. Store the count at run start.

**Modify `backend/app/db/models.py`:**
```python
class PipelineRun(Base):
    # ... existing fields ...
    total_symbols = Column(Integer, default=0)   # ADD THIS
```

**Generate Alembic migration:**
```bash
alembic revision --autogenerate -m "add_total_symbols_to_pipeline_run"
alembic upgrade head
```

**Modify `backend/app/pipeline/orchestrator.py`:**

After `symbols = get_nse_symbols(limit=limit)`, add:
```python
run.total_symbols = len(symbols)
db.commit()
```

**Modify `GET /api/pipeline/latest` response** in `dashboard.py` to include `total_symbols`:
```python
result = {
    ...
    "total_symbols": run.total_symbols or 0,
    ...
}
```

### Frontend Changes

**New component:** `frontend/src/components/PipelineProgress.jsx`

```jsx
import './PipelineProgress.css';

const PipelineProgress = ({ fetched, scored, total, tier1Count }) => {
  // Phase 1: Fetching (0% to 50% of bar)
  // Phase 2: Scoring (50% to 100% of bar)
  // Use tier1_count as the denominator for scoring phase if total unknown

  const fetchPct = total > 0 ? Math.min((fetched / total) * 100, 100) : 0;
  const scorePct = tier1Count > 0 ? Math.min((scored / tier1Count) * 100, 100) : 0;

  // Overall: fetching is first half, scoring is second half
  const overallPct = total > 0
    ? Math.min(((fetched / total) * 50) + (scored / Math.max(tier1Count, 1)) * 50, 100)
    : fetchPct;

  return (
    <div className="pipeline-progress">
      <div className="progress-bar-track">
        <div
          className="progress-bar-fill"
          style={{ width: `${overallPct}%` }}
        />
      </div>
      <div className="progress-labels">
        <span>Fetch: {fetched}{total > 0 ? `/${total}` : ''}</span>
        <span>{overallPct.toFixed(0)}%</span>
        <span>Score: {scored}{tier1Count > 0 ? `/${tier1Count}` : ''}</span>
      </div>
    </div>
  );
};

export default PipelineProgress;
```

```css
/* frontend/src/components/PipelineProgress.css */
.pipeline-progress { width: 100%; margin-top: 8px; }
.progress-bar-track {
  height: 4px;
  background: var(--color-bg-elevated);
  border-radius: 2px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: var(--color-bullish);
  border-radius: 2px;
  transition: width 0.5s ease;
}
.progress-labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.7rem;
  color: var(--color-text-muted);
  margin-top: 4px;
}
```

**Modify `Dashboard.jsx`:**

In the running status badge (`status === 'running'` block), add `PipelineProgress` below the existing text:

```jsx
import PipelineProgress from '../components/PipelineProgress';

// Inside the running block:
{status === 'running' && (
  <div className="summary-item status-badge running">
    <div className="flex-center-gap-12">
      <RefreshCcw size={16} className="spin" />
      <div>
        <span className="label">Pipeline Running</span>
        <span className="value fs-12">
          {pipeline?.stocks_fetched || 0} fetched | {pipeline?.stocks_scored || 0} scored
        </span>
        <PipelineProgress
          fetched={pipeline?.stocks_fetched || 0}
          scored={pipeline?.stocks_scored || 0}
          total={pipeline?.total_symbols || 0}
          tier1Count={pipeline?.tier1_count || 0}
        />
      </div>
      ...stop button...
    </div>
  </div>
)}
```

**Modify `usePipeline.js`** to expose `total_symbols` from `stats`:
```js
// stats already exposes all fields from the API response.
// No changes needed if stats is passed through as-is.
// Verify: pipeline?.total_symbols is accessible in Dashboard.
```

---

## Implementation Order

The agent should implement features in this order to minimize merge conflicts:

1. **F6 (Export CSV)** — purely additive, zero risk, highest simplicity
2. **F7 (Pagination)** — additive to Dashboard and Discover, no existing component changes
3. **F3 (Sortable Columns)** — deletes `ScreenResultTable`, replaces with existing `DataTable`
4. **F5 (Watchlist)** — new hook + new component + small changes to StockCard and Dashboard
5. **F2 (Search)** — modifies existing `GlobalSearch`, replaces fetch strategy
6. **F8 (Pipeline Progress)** — one new DB column, one new component, small Dashboard change
7. **F4 (Score Breakdown)** — new utility + new component + API addition + StockDetail change
8. **F1 (Change Banner)** — new backend endpoint + new component + Dashboard integration

---

## File Changeset Summary

**Create:**
```
frontend/src/components/ChangeBanner.jsx
frontend/src/components/ChangeBanner.css
frontend/src/components/ScoreBreakdown.jsx
frontend/src/components/ScoreBreakdown.css
frontend/src/components/WatchlistStar.jsx
frontend/src/components/WatchlistStar.css
frontend/src/components/PipelineProgress.jsx
frontend/src/components/PipelineProgress.css
frontend/src/components/ui/Pagination.jsx
frontend/src/components/ui/Pagination.css
frontend/src/hooks/useWatchlist.js
frontend/src/utils/scoreBreakdown.js
frontend/src/utils/exportCsv.js
alembic/versions/XXX_add_total_symbols_to_pipeline_run.py
```

**Modify:**
```
frontend/src/components/GlobalSearch.jsx         (F2 — replace fetch strategy, add keyboard nav, show names)
frontend/src/components/StockCard.jsx            (F5 — add WatchlistStar)
frontend/src/components/FilterBottomSheet.jsx    (F5 — add watchlist chip)
frontend/src/pages/Dashboard.jsx                (F1, F5, F7, F8)
frontend/src/pages/Discover.jsx                 (F3, F6, F7)
frontend/src/pages/StockDetail.jsx              (F4)
frontend/src/api/client.js                      (F1, F2)
backend/app/routers/dashboard.py               (F1, F8)
backend/app/routers/stocks.py                  (F2, F4)
backend/app/db/models.py                       (F8)
backend/app/pipeline/orchestrator.py           (F8)
```

**Delete:**
```
frontend/src/components/ScreenResultTable.jsx   (F3 — replaced by DataTable)
```

---

## Acceptance Criteria

- [ ] F1: `GET /api/dashboard/changes` returns structured change data. `ChangeBanner` renders collapsed by default, open/closed state persists in `localStorage`. Shows "No changes" when data is empty.
- [ ] F2: Typing 2+ chars in `GlobalSearch` triggers a debounced API call to `/stocks/search`. Results show symbol + name + sector. Arrow keys navigate the list. Enter selects. Existing `Cmd+K` trigger and overlay are unchanged.
- [ ] F3: `ScreenResultTable.jsx` is deleted. Clicking any column header in the Discover results table sorts ascending; clicking again sorts descending. Arrow indicator shows direction.
- [ ] F4: Score breakdown card appears in StockDetail side column. Each bar reflects the actual indicator values from the API. The "inferred" disclaimer is visible.
- [ ] F5: Star icon on each card and table row. Clicking star does not navigate to stock detail. `localStorage` persists stars across page refreshes. "Watchlist (N)" chip in Dashboard filters correctly.
- [ ] F6: Clicking CSV button in Discover downloads a `.csv` file with current columns and data. Filename includes the screen slug and today's date. Button is disabled when results array is empty.
- [ ] F7: Dashboard table shows 50 rows by default. Page size selector (25/50/100) works. Changing filters resets to page 1. Grid view is unaffected.
- [ ] F8: Progress bar appears in Dashboard only when pipeline is running. Bar animates smoothly as `stocks_fetched` and `stocks_scored` update. Hidden when pipeline is idle/complete.
