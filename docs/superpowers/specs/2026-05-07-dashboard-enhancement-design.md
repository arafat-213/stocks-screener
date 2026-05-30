# Dashboard Enhancement Spec

## 1. Backend Schema & Models

**`TechnicalSignal` Updates:**
- `close_price` (Float, nullable=True): Closing price from the latest daily candle.
- `price_change_pct` (Float, nullable=True): Percentage change from the last two daily candles.
*(Note: These are explicitly `nullable=True` to ensure W and M timeframe rows have null values by schema contract).*

**`PipelineRun` Updates:**
- `tier1_count` (Integer, default=0): Count of stocks passing Tier 1 fast filters.
- `tier2_count` (Integer, default=0): Count of stocks passing Tier 2 deep fundamental cache checks (distinct from `stocks_scored`).

**New Table: `MarketSnapshot`**
- `date` (Date, primary_key): Date of snapshot (no time component, matching signal date format).
- `symbol` (String, primary_key): Index/benchmark symbol (e.g., `^NSEI`).
- `close` (Float): Closing value.
- `change_pct` (Float): Percentage change.

## 2. Pipeline Logic & Data Fetching

**A. Pipeline Funnel Stats (`orchestrator.py`)**
- Update orchestrator to count `tier1_survivors` into `run.tier1_count`.
- Add a dedicated counter for `run.tier2_count` to track symbols passing cache checks prior to scoring.

**B. Stock Price Snapshots**
- Inside the scoring loop for `tf == 'D'`, capture `close_price` and `price_change_pct`.
- **Guard**: Only calculate change if `len(hist) >= 2` to prevent `IndexError` on new or suspended stocks.

**C. Market/Index Snapshots**
- At pipeline completion, fetch index data for `^NSEI` (and any other tracked benchmarks).
- **Fix**: Update `fetch_stock_data` to accept an `append_ns=False` flag to prevent requesting `^NSEI.NS`.
- Upsert the results into the new `MarketSnapshot` table for the current signal date.

## 3. API Endpoints

**A. `GET /api/screener/results`**
- Returns a structured list of stocks for the latest pipeline run.
- Performs a join across `TechnicalSignal` (max date), `Stock`, and `FundamentalData`.
- **Critical Subquery**: The `FundamentalData` join must use a `MAX(date) per symbol` subquery to prevent nulls for stocks whose fundamentals weren't refreshed today.
- Groups multi-timeframe results in Python (with a code comment noting this could move to SQL if the universe scales up).
- **Default Sort**: `confluence_count` DESC -> `timeframes['D'].is_bullish` DESC -> `timeframes['D'].score` DESC.

**B. `GET /api/pipeline/latest`**
- Returns the latest completed `PipelineRun` (including funnel stats).
- Fetches and includes the latest `MarketSnapshot` records as a `market_context` array within the response.

## 4. Frontend Redesign

**A. API Client (`api/client.js`)**
- Update endpoints to match the new unified backend data structure.

**B. Stock Card Component**
- Display symbol, sector tag, `close_price`, and `price_change_pct` (green/red).
- Prominent **Confluence Badge** (e.g., 3/3).
- **Timeframe Indicators** (D/W/M) with clear visual states for bullish alignment.
- **Technical Metrics Row**: Daily score, RSI, EMA signal.
- **Fundamentals Snapshot Row**: P/E, P/B, ROE, Market Cap.

**C. Sidebar Component**
- **Pipeline Summary**: Funnel stats (`stocks_fetched` -> `tier1_count` -> `tier2_count` -> `stocks_scored`).
- **Confluence Filter**: Radio/toggle (3/3, 2/3+, All) applied client-side.
- **Sector Filter**: Checkboxes for sectors. **Rule**: Only display sectors that have at least one stock in the *current unfiltered results*.

**D. Dashboard View**
- **Summary Bar**: Aggregate stats above the grid (e.g., "89 stocks scored | 12 full confluence | Nifty 50: ▲ 0.4%").
- **Sort Controls**: Dropdown for `Confluence` (default), `Score`, `RSI`, `P/E`.
- **States**:
  - *Loading*: Render a grid of skeleton loaders (matching the new card shape).
  - *Pipeline never run*: Display a prominent CTA to run the pipeline.
  - *No results*: Show "No stocks match the selected filters" with a link to reset filters.
