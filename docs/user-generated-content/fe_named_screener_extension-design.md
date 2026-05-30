# Frontend Named Screener Integration Spec

## Goal

Integrate the new `/api/screens` backend endpoints into the existing React frontend. Add a dedicated **Screens** page that presents the 8 named screens (Momentum Monsters, Near Breakout, etc.) as browsable, selectable views. Update the existing Screener page to surface the new enriched fields (momentum, RS score, ADX, ROCE, PEG, FCF). Update `api/client.js` with all new endpoint bindings. No CSS framework is introduced — all styling follows existing CSS variable conventions already established in the codebase.

---

## Architecture Overview

```
src/
  api/
    client.js               ← add getScreensList, getScreenBySlug
  pages/
    Screens.jsx             ← NEW: named screen browser
    Screener.jsx            ← MODIFY: add new enriched columns
  components/
    ScreenCard.jsx          ← NEW: card for each named screen
    ScreenResultTable.jsx   ← NEW: results table for a selected screen
  App.jsx                   ← add /screens route
  components/Navigation.jsx ← add Screens nav item
```

---

## 1. API Client Updates (`src/api/client.js`)

### Current State
The file exports three functions against `http://localhost:8000/api`:
- `getTopStocks` → `GET /stocks/top`
- `getStatus` → `GET /pipeline/status`
- `runScreener` → `POST /screener/run`

Several other functions referenced in components (`fetchResults`, `fetchPipelineStatus`, `getStockDetail`, `getReportList`, `getReportByDate`) are imported from `../api/client` but not present in the uploaded `api.js`. These are assumed to exist in a separate `client.js` file not uploaded.

### New Exports to Add

Add the following to `client.js` (not the minimal `api.js`):

```javascript
// Named Screens
export const getScreensList = () => api.get('/screens');
export const getScreenBySlug = (slug, live = false) =>
  api.get(`/screens/${slug}${live ? '?live=true' : ''}`);
```

No other API changes are required. The existing `fetchResults`, `fetchPipelineStatus`, etc. remain untouched.

---

## 2. New Page: `src/pages/Screens.jsx`

### Purpose
A browsable catalogue of the 8 named screens. The user selects a screen from a grid of cards; results load in a table below (or replace the cards on mobile). This page is self-contained — it does not share state with Dashboard or Screener.

### Layout — Desktop
```
┌──────────────────────────────────────────────────┐
│  Named Screens                                   │
│  Pre-built strategies. Updated after each run.  │
├──────────────────────────────────────────────────┤
│  [Category tabs: All | Price Action | Momentum | Value | Quality]
├──────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ Screen   │ │ Screen   │ │ Screen   │  ...     │
│  │ Card     │ │ Card     │ │ Card     │          │
│  └──────────┘ └──────────┘ └──────────┘         │
├──────────────────────────────────────────────────┤
│  Results: "Momentum Monsters"  [Live ⟳] [N hits] │
│  ┌──────────────────────────────────────────────┐│
│  │  Symbol │ Name │ Score │ RS │ Momentum 3M │..││
│  └──────────────────────────────────────────────┘│
└──────────────────────────────────────────────────┘
```

### Layout — Mobile
Screen cards stack in a 2-column grid. Tapping a card collapses the grid and shows the result table full-width with a back button.

### State

```javascript
const [screens, setScreens] = useState([]);          // list from GET /api/screens
const [selectedSlug, setSelectedSlug] = useState(null);
const [results, setResults] = useState([]);
const [loadingScreens, setLoadingScreens] = useState(true);
const [loadingResults, setLoadingResults] = useState(false);
const [categoryFilter, setCategoryFilter] = useState('All');
const [liveMode, setLiveMode] = useState(false);
```

### Data Flow

1. On mount: call `getScreensList()`. The response is an array of objects:
   ```json
   [
     { "slug": "momentum-monsters", "label": "Momentum Monsters",
       "description": "...", "category": "Momentum" },
     ...
   ]
   ```
2. Render `ScreenCard` for each, filtered by `categoryFilter`.
3. On card click: set `selectedSlug`, call `getScreenBySlug(slug, liveMode)`. Response:
   ```json
   { "screen": "momentum-monsters", "count": 24, "results": [...] }
   ```
4. Render `ScreenResultTable` with `results`.
5. "Live ⟳" toggle re-fetches with `live=true`. Show a subtle loading indicator on the table without clearing existing results (avoids flash).

### `ScreenCard` Component (`src/components/ScreenCard.jsx`)

Props: `{ screen, isSelected, onClick }`

Where `screen` is `{ slug, label, description, category }`.

Renders:
- Category badge (colour-coded: Momentum = amber, Value = blue, Price Action = teal, Quality = purple — use existing `--color-bullish` / `--color-bearish` or extend with CSS vars scoped to this component).
- Screen label as heading.
- Description text (2-line clamp via CSS).
- Selected state: border highlight using `--color-bullish`, subtle background shift.
- No skeleton needed — screen list loads fast (static metadata, no DB query).

### `ScreenResultTable` Component (`src/components/ScreenResultTable.jsx`)

Props: `{ results, slug, loading }`

Columns vary by screen category. Use a column config map keyed by slug:

```javascript
const SCREEN_COLUMNS = {
  'momentum-monsters':      ['symbol', 'name', 'rs_score', 'momentum_3m', 'adx', 'score'],
  'value-with-momentum':    ['symbol', 'name', 'peg_ratio', 'momentum_1m', 'ema_slope', 'score'],
  'near-breakout':          ['symbol', 'name', 'pct_from_resistance', 'volume_breakout', 'score'],
  '52w-high':               ['symbol', 'name', 'pct_from_52w_high', 'week52_high', 'score'],
  '52w-low':                ['symbol', 'name', 'pct_from_52w_low', 'week52_low', 'score'],
  'low-debt-midcap':        ['symbol', 'name', 'market_cap_category', 'de_ratio', 'fcf_positive', 'score'],
  'undervalued-fundamentals':['symbol', 'name', 'peg_ratio', 'ev_to_ebitda', 'dividend_yield', 'score'],
  'steady-compounders':     ['symbol', 'name', 'roce', 'dividend_consistency', 'above_200ema', 'score'],
  '_default':               ['symbol', 'name', 'score', 'rsi', 'confluence_count'],
};
```

Column header labels and formatters:

```javascript
const COLUMN_META = {
  symbol:               { label: 'Symbol',      fmt: v => v },
  name:                 { label: 'Name',         fmt: v => v },
  score:                { label: 'Score',        fmt: v => v?.toFixed(1) ?? '—' },
  rs_score:             { label: 'RS Score',     fmt: v => v?.toFixed(0) ?? '—' },
  momentum_1m:          { label: '1M Mom %',     fmt: v => v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—' },
  momentum_3m:          { label: '3M Mom %',     fmt: v => v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—' },
  adx:                  { label: 'ADX',          fmt: v => v?.toFixed(1) ?? '—' },
  peg_ratio:            { label: 'PEG',          fmt: v => v?.toFixed(2) ?? '—' },
  ev_to_ebitda:         { label: 'EV/EBITDA',   fmt: v => v?.toFixed(1) ?? '—' },
  dividend_yield:       { label: 'Div Yield',    fmt: v => v != null ? `${(v * 100).toFixed(2)}%` : '—' },
  roce:                 { label: 'ROCE %',       fmt: v => v != null ? `${(v * 100).toFixed(1)}%` : '—' },
  de_ratio:             { label: 'D/E',          fmt: v => v?.toFixed(2) ?? '—' },
  pct_from_52w_high:    { label: '% from High',  fmt: v => v != null ? `${v.toFixed(1)}%` : '—' },
  pct_from_52w_low:     { label: '% from Low',   fmt: v => v != null ? `${v.toFixed(1)}%` : '—' },
  week52_high:          { label: '52W High',     fmt: v => v != null ? `₹${v.toLocaleString('en-IN')}` : '—' },
  week52_low:           { label: '52W Low',      fmt: v => v != null ? `₹${v.toLocaleString('en-IN')}` : '—' },
  pct_from_resistance:  { label: '% to Break',   fmt: v => v != null ? `${v.toFixed(1)}%` : '—' },
  volume_breakout:      { label: 'Vol Break',    fmt: v => v ? '✓' : '—' },
  fcf_positive:         { label: 'FCF+',         fmt: v => v ? '✓' : '—' },
  dividend_consistency: { label: 'Div 3Y',       fmt: v => v ? '✓' : '—' },
  above_200ema:         { label: '>200 EMA',     fmt: v => v ? '✓' : '—' },
  market_cap_category:  { label: 'Cap',          fmt: v => v ?? '—' },
  ema_slope:            { label: 'EMA Trend',    fmt: v => v != null ? (v > 0 ? '↑' : '↓') : '—' },
  confluence_count:     { label: 'Conf.',        fmt: v => v != null ? `${v}/3` : '—' },
  rsi:                  { label: 'RSI',          fmt: v => v?.toFixed(1) ?? '—' },
};
```

Each row links to `/stocks/${symbol}` using `<Link>` — same pattern as existing `MarketTable`.

If `loading` is true and `results.length > 0`, apply a `0.5` opacity to the table body (stale data indicator) rather than replacing with a spinner.

If `loading` is true and `results.length === 0`, show 8 skeleton rows matching the column count.

---

## 3. Modified Page: `src/pages/Screener.jsx`

### Current State
The existing Screener page fetches from `fetchResults()` (the dashboard endpoint, `GET /screener/results`) and shows: Symbol, Sector, Confluence, Daily Score, ROE, P/E.

It functions as a manual filter tool — the user adjusts Sector, minScore, minROE, maxPE and sees results update client-side.

### What Changes

The Screener page is **not replaced** — it remains the manual filter tool. Two additions:

**Addition 1 — New columns in the results table:**

Add these columns after the existing P/E column. All values come from the same `fetchResults()` response — the backend now populates these fields on the `TechnicalSignal` and `FundamentalCache` models. No new API call needed.

| Column | Source field | Format |
|---|---|---|
| Momentum 3M | `timeframes.D.momentum_3m` | `+12.4%` with colour (green/red) |
| RS Score | `timeframes.D.rs_score` | Integer 0–100 |
| ADX | `timeframes.D.adx` | One decimal |
| Above 200 EMA | `timeframes.D.above_200ema` | `✓` / `—` |

**Addition 2 — New filter inputs:**

Add below the existing Max P/E input, in the same filter grid:

```
Min RS Score (slider 0–100, default 0)
Min Momentum 3M % (number input, placeholder "e.g. 10")
ADX ≥ (number input, placeholder "e.g. 20")
Cap Category (select: All | Largecap | Midcap | Smallcap)
```

Wire these into the existing `filters` state object and `filteredStocks` `useMemo`:

```javascript
// Add to filters state:
const [filters, setFilters] = useState({
  sector: 'All',
  minScore: 0,
  minROE: '',
  maxPE: '',
  minRS: 0,          // NEW
  minMom3m: '',      // NEW
  minADX: '',        // NEW
  capCategory: 'All' // NEW
});

// Add to filteredStocks filter chain:
const matchRS    = (stock.timeframes?.D?.rs_score ?? 0) >= filters.minRS;
const matchMom   = !filters.minMom3m || (stock.timeframes?.D?.momentum_3m ?? -999) >= parseFloat(filters.minMom3m);
const matchADX   = !filters.minADX   || (stock.timeframes?.D?.adx ?? 0) >= parseFloat(filters.minADX);
const matchCap   = filters.capCategory === 'All' || stock.fundamentals?.market_cap_category === filters.capCategory.toLowerCase();
return matchSector && matchScore && matchROE && matchPE && matchRS && matchMom && matchADX && matchCap;
```

Add to `sortConfig` options:

```javascript
// Add to handleSort eligible keys:
'rs_score'    → stock.timeframes?.D?.rs_score
'momentum_3m' → stock.timeframes?.D?.momentum_3m
```

Add to the sort `<select>`:
```jsx
<option value="rs_score">RS Score</option>
<option value="momentum_3m">Momentum 3M</option>
```

No layout changes needed — the filter grid uses `auto-fit` and the table scrolls horizontally on overflow (verify `table-container` has `overflow-x: auto` in existing CSS; add if missing).

---

## 4. Navigation Updates (`src/components/Navigation.jsx`)

### Add Screens nav item

Add a new entry to the `navItems` array:

```javascript
import { Layers } from 'lucide-react'; // Add to existing lucide import

const navItems = [
  { to: '/', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
  { to: '/screener', label: 'Screener', icon: <Filter size={20} /> },
  { to: '/screens', label: 'Screens', icon: <Layers size={20} /> },  // NEW
  { to: '/reports', label: 'Reports', icon: <FileText size={20} /> },
];
```

This automatically appears in both the desktop sidebar and the mobile bottom nav — no other Navigation changes needed.

---

## 5. App.jsx — New Route

```jsx
import Screens from './pages/Screens';   // Add import

// Add inside <Routes>:
<Route path="/screens" element={<Screens />} />
```

---

## 6. Loading & Error States

### `Screens.jsx`

| State | Behaviour |
|---|---|
| `loadingScreens = true` | Show 8 placeholder `ScreenCard` skeletons (grey boxes, same dimensions as real cards) |
| `getScreensList` fails | Show inline error banner: "Could not load screens. Check that the pipeline has run at least once." with a retry button |
| `selectedSlug` set, `loadingResults = true`, `results.length === 0` | Show skeleton rows in `ScreenResultTable` |
| `selectedSlug` set, `loadingResults = true`, `results.length > 0` | Dim existing table (stale indicator), no spinner |
| `results.length === 0` after load | Empty state: "No stocks match this screen right now. Results update after each pipeline run." |
| API returns `404` for a slug | Show: "This screen is not available. The pipeline may not have run since it was added." |

### `Screener.jsx` error states are unchanged.

---

## 7. Implementation Tasks

1. **`src/api/client.js`** — Add `getScreensList` and `getScreenBySlug`. Verify existing exports (`fetchResults`, `fetchPipelineStatus`, `getStockDetail`, `getReportList`, `getReportByDate`) are present; if `client.js` and `api.js` are separate files, consolidate into one or ensure imports resolve correctly across pages.

2. **`src/components/ScreenCard.jsx`** — Implement with props as specified. Include CSS inline or in a new `ScreenCard.css` following the naming convention of existing component CSS files.

3. **`src/components/ScreenResultTable.jsx`** — Implement with column config map and formatter map. Ensure `<Link to={...}>` wraps each row, matching the pattern in `MarketTable.jsx`.

4. **`src/pages/Screens.jsx`** — Implement full page with state, data flow, category tab filtering, and responsive mobile behaviour.

5. **`src/pages/Screener.jsx`** — Add 4 new filter inputs, 4 new filter conditions in `filteredStocks`, 2 new sort options, and 4 new table columns. Verify `table-container` has `overflow-x: auto`.

6. **`src/components/Navigation.jsx`** — Add `Layers` import and Screens nav item.

7. **`src/App.jsx`** — Add Screens import and route.

---

## 8. What Is Explicitly Out of Scope

- No changes to `Dashboard.jsx`, `Reports.jsx`, `StockDetail.jsx`, or any component not listed above.
- No new CSS framework, utility library, or state management library.
- No changes to the `FilterBottomSheet` — it is Dashboard-specific and does not need to surface screen filters.
- No real-time polling on the Screens page — screen results are materialized daily; polling adds no value.
- No pagination — the backend caps results at 50 per screen; rendering all rows is acceptable.
- The `live` mode toggle (`?live=true`) is a developer convenience; it is exposed in the UI as a small toggle button but is not prominently marketed to end users.
