# Design Spec: Dashboard & Detail Enhancements
**Date:** 2026-05-07
**Topic:** Closing the loop on Stock Details, Reports, and Screener.

## 1. Stock Detail View (`/stocks/{symbol}`)
### Backend
- **Endpoint:** `GET /api/stocks/{symbol}`
- **Logic:**
    1. **Symbol Handling:** The incoming `symbol` might have `.NS`. Strip it for DB queries. Append it for `yfinance`.
    2. **Price Data:** Fetch last 1 year of daily OHLCV from `yfinance` on-demand.
    3. **Multi-Timeframe Scores:** Query `TechnicalSignal` for the latest 'D', 'W', and 'M' records.
    4. **Score History:** Query `TechnicalSignal` for the last 30 daily scores (`timeframe='D'`).
    5. **Fundamentals:**
        - `FundamentalCache`: Fetch `de_ratio`, `sector`.
        - `FundamentalData`: Fetch `pe`, `pb`, `roe`, `eps_growth`.
- **Response Shape:**
  ```json
  {
    "symbol": "RELIANCE",
    "name": "Reliance Industries",
    "ohlcv": [{"time": "2024-05-07", "open": 2800, "high": 2850, "low": 2790, "close": 2840}, ...],
    "scores": {
      "D": {"score": 75, "ema_signal": "Bullish", "volume_signal": "High", "rsi_signal": "Overbought", "rsi": 62},
      "W": {"score": 55, "ema_signal": "Neutral", "volume_signal": "Normal", "rsi_signal": "Neutral", "rsi": 50},
      "M": {"score": 80, "ema_signal": "Strong Bullish", "volume_signal": "Normal", "rsi_signal": "Bullish", "rsi": 68}
    },
    "score_history": [{"date": "2024-05-07", "score": 75}, ...],
    "fundamentals": {"pe": 25.4, "roe": 16.2, "debt_equity": 0.4, "sector": "Energy"}
  }
  ```

### Frontend (`StockDetail.jsx`)
- **Candlestick Chart:** Wire up `lightweight-charts` with the `ohlcv` array.
- **Confluence Panel:** Side-by-side cards for Daily, Weekly, and Monthly scores, showing all signal fields.
- **Score Trend Chart:** Small line chart (Recharts) showing the 30-day daily score trend.
- **Fundamental Table:** Display metrics from both `FundamentalCache` and `FundamentalData`.

## 2. Reports View (`/reports`)
### Backend
- **Endpoint:** `GET /api/reports` -> Returns list of distinct dates from `TechnicalSignal`.
- **Endpoint:** `GET /api/reports/latest` -> Same logic as `generate_daily_report()` but returns JSON.
- **Endpoint:** `GET /api/reports/{date}` -> Returns structured report for a specific date.
- **Logic:** Query `TechnicalSignal` joined with `Stock` to get symbols, names, confluence (count of bullish TFs), daily score, and RSI.

### Frontend (`Reports.jsx`)
- **Sidebar/List:** List of available report dates.
- **Main Content:** Table showing the ranked stocks for the selected date.

## 3. Screener View (`/screener`)
### Backend
- **Endpoint:** Reuse `GET /api/stocks/top` (or similar endpoint used by Dashboard).
- **Logic:** No new backend logic; the frontend will apply advanced filtering on the results.

### Frontend (`Screener.jsx`)
- **Filter Controls:** Inputs/Selects for:
    - Sector (dropdown)
    - Min Entry Score (slider)
    - Min ROE (number)
    - Max P/E (number)
- **Results Table:** Sortable table of stocks passing the local filters.

## 4. Implementation Priorities
1. **Backend Endpoints:** Build the `/api/stocks/{symbol}` and report endpoints first.
2. **Stock Detail Wiring:** Get the chart and MTF confluence rendering.
3. **Reports UI:** Build the historical browser.
4. **Screener UI:** Build the filter bar.
