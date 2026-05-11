
---
FOR AI AGENTS: DO NOT READ THIS FILE YET OR TRY TO IMPLEMENT ANY OF THIS YET

## Bugs

**1. Field name mismatch in `StockDetail.jsx`**
The component reads `data.fundamentals?.debt_to_equity` but the API returns `debt_equity`. This means D/E ratio always shows "N/A" even when data exists.

**2. RSI chart Y-axis is wrong**
```jsx
// StockDetail.jsx
<YAxis domain={[0, 10]} />  // RSI range is 0–100, not 0–10
```
The score history line will be squashed flat against the bottom of the chart.

**3. `ema_signal` case mismatch**
The backend returns `'bullish'` (lowercase) but both `StockCard.jsx` and `StockDetail.jsx` compare against `'Bullish'` (capitalized). EMA signal badges will always show the bearish/wrong style.

```jsx
// StockCard.jsx — always false
daily.ema_signal === 'Bullish'

// StockDetail.jsx — same issue
scoreData.ema_signal === 'Bullish'
```

**4. Variable shadowing in `Discover.jsx`**
The component imports `fetchResults` from `../api/client` at the top, then defines a local async function also named `fetchResults` inside a `useEffect`. The outer import gets shadowed inside the interactive tab's `loadData` callback. This works by accident today but is fragile.

**5. Skeleton table headers don't match live table headers in `MarketTable.jsx`**
The skeleton shows RSI and EMA columns. The live table shows RS Score, ADX, ROE %, P/E. Users see a layout shift when data loads.

**6. Market cap display math is wrong in `StockDetail.jsx`**
```jsx
₹{(data.fundamentals?.market_cap / 1000).toFixed(0)}k Cr
```
yfinance returns market cap in absolute INR (e.g. 5,000,000,000,000). Dividing by 1000 gives a meaningless number. You need to divide by 10,000,000 to get Crores, then optionally by 1000 to get "k Cr". The `StockCard.jsx` has a correct `formatMCap` helper — use that instead.

**7. `fetchData` missing from `useEffect` dependency array**
`fetchData` is defined inside the component but the `setInterval` effect has an empty dependency array. This captures a stale closure. Move `fetchData` outside the component or wrap it in `useCallback`.

---

## UX & Design Issues

**8. No user-facing error states**
Every `catch` block just does `console.error`. If the API is down, users see a perpetual loading spinner or silently empty data. You need at least one error banner or toast.

**9. "Test (50)" button has no loading indicator**
`handleRunPipeline` in `Dashboard.jsx` has no local loading state. The button doesn't disable while the request is in-flight, so users can double-submit.

**10. Polling happens regardless of pipeline state**
The dashboard polls every 15 seconds unconditionally. When the pipeline isn't running this is pure waste. Smart polling would look like: fast interval (5s) when status is `'running'`, slow interval (60s) when idle.

**11. `Intelligence.jsx` date list has no limit or search**
If you've run the pipeline daily for 6 months, there are 120+ dates in a scrollable list with no search, grouping by month, or "latest" default highlight. This will become unusable quickly.

**12. `StockDetail.jsx` doesn't surface the richest data**
The backend returns RS score, momentum (1m/3m/6m/12m), ADX, 52-week range, resistance level, and volume breakout for each stock. The detail page shows none of this — only P/E, ROE, D/E, and market cap. The data exists in the API response; it just isn't rendered.

**13. No global stock search**
There's no way to jump directly to a stock by typing its symbol. Users have to find it by scrolling the table or knowing which screen it appears in.

**14. `ScreenResultTable` has no sorting**
Column headers are static. On a 50-row result, users can't sort by momentum, ADX, or score to find the best entries.

**15. No "last updated" timestamp on the Dashboard**
Users have no idea if they're looking at today's data or last week's. The `pipeline.scored_at` field is available but only shown on the System page.

**16. Inline styles are inconsistent with the CSS class system**
`Dashboard.jsx`, `Discover.jsx`, and `Intelligence.jsx` have dozens of `style={{ display: 'flex', gap: '32px', ... }}` inline. This makes theming and responsive overrides harder. The layout CSS should live in the CSS files.

---

## Architecture Issues

**17. Pipeline control is duplicated across Dashboard and System**
`handleRunPipeline` and `handleStopPipeline` are copied identically in both `Dashboard.jsx` and `System.jsx`. This should be a shared hook — `usePipeline()` — that both pages consume.

**18. `MarketTable` and `ScreenResultTable` are parallel implementations**
Both render tabular stock data with similar columns, links, and formatting. As you add features (sorting, column hiding, export) you'll have to maintain two separate components. A single `DataTable` component with a column config prop would handle both.

**19. No API loading/error abstraction**
Every page implements its own `loading`, `error`, and `useEffect` fetch pattern. A `useFetch(apiFn, deps)` hook would remove ~30 lines of boilerplate per page and centralize error handling.

---
