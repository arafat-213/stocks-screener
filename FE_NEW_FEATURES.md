
## Feature Gaps Worth Prioritizing

**"What changed today" banner** — a small section at the top of the Dashboard showing stocks where `is_bullish` flipped or confluence changed today. The data already exists across pipeline runs; this is purely a frontend aggregation.

**Stock search / command palette** — a `Cmd+K` style modal that lets users type a symbol and jump to the detail page. One input, one API call, high-value daily use.

**Sortable columns in `ScreenResultTable`** — click a column header, arrow indicator shows direction, sort client-side. The data is already there.

**Score breakdown in `StockDetail`** — a horizontal bar or small table showing how the 100 points are distributed (EMA: 20, MACD: 20, RSI: 15, Volume: 15, P/E: 20). Makes the score trustworthy rather than a black box.

**Watchlist** — star icon on each card/row, saved to `localStorage` initially (no auth needed). A "Watchlist" filter chip on the Dashboard surfaces only starred stocks.

**Export CSV** — a download button on `ScreenResultTable`. `Papa.unparse(results)` + a `Blob` download is about 5 lines and very high perceived value for traders who want to work in spreadsheets.

**Pagination or virtual scrolling** — the market table could render 500+ rows. Without pagination, the DOM becomes slow and scrolling degrades. Add a simple page size control (25/50/100) with prev/next.

**Pipeline progress bar** — instead of just showing "X fetched | Y scored", render a thin progress bar using `stocks_fetched / total_symbols` so users can estimate time remaining.
