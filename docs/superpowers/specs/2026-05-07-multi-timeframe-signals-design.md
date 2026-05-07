# Multi-Timeframe Signal Engine Design

## Goal
Implement a scoring engine that analyzes stocks across Daily (D), Weekly (W), and Monthly (M) timeframes to identify confluence-based buy signals.

## Architecture

### 1. Database Schema Refactor (`technical_signals`)
The `DailyScore` table will be renamed to `technical_signals` with the following schema:
- `id`: Integer, Primary Key.
- `symbol`: String, ForeignKey("stocks.symbol").
- `date`: Date (Candle close date: e.g., Friday for W, Month-end for M).
- `timeframe`: String(1) ('D', 'W', 'M').
- `is_bullish`: Boolean (Explicitly stored result of tiered logic).
- `score`: Float (Combined score for D, Trend-weight for W/M).
- `rsi`: Float.
- `macd`: Float.
- `ema_signal`: String ('bullish', 'neutral', 'bearish').
- `volume_signal`: String.
- `rsi_signal`: String.
- `scored_at`: DateTime (Pipeline execution timestamp).

**Constraint:** `UniqueConstraint('symbol', 'date', 'timeframe')`.

### 2. Multi-Timeframe Scorer
- **Data Fetching:** Increase `yfinance` period to `3y` to ensure valid Monthly EMA26 calculations.
- **Resampling Utility:**
    - OHLCV aggregation: `Open: first`, `High: max`, `Low: min`, `Close: last`, `Volume: sum`.
    - Incomplete Candle Handling: Drop the current incomplete candle for W and M timeframes before scoring.
- **Tiered Bullish Logic:**
    - **Daily (Execution):** MACD > Signal & MACD > 0, EMA stack (5 > 13 > 26), RSI recovery or 50-cross.
    - **Weekly (Trend):** RSI > 50, Price > EMA26.
    - **Monthly (Context):** RSI > 50, Price > EMA13 OR Price > EMA26.
- **Score Definition:**
    - **Daily:** Combined Technical (70) + Fundamental (30) = Max 100 pts.
    - **Weekly/Monthly:** Technical only = Max 70 pts (skip fundamental components as they are timeframe-agnostic).

### 3. Confluence & Reporting
- **Confluence Rule:** A stock is ranked by the number of `is_bullish` timeframes (0-3) for a given date.
- **Ranking Query (Conceptual):**
  ```sql
  SELECT 
      symbol,
      SUM(CASE WHEN is_bullish THEN 1 ELSE 0 END) as confluence_count,
      MAX(CASE WHEN timeframe = 'D' THEN score ELSE 0 END) as daily_score
  FROM technical_signals
  WHERE date = :date
  GROUP BY symbol
  ORDER BY confluence_count DESC, daily_score DESC
  LIMIT 20
  ```

## Migration Strategy
1. Create Alembic migration to:
    - Rename `daily_scores` -> `technical_signals`.
    - Add `id` (PK), `timeframe`, `is_bullish`, `rsi_signal`, `scored_at`.
    - Drop old PK constraint and add `UniqueConstraint`.
2. Backfill (Historical Approximation):
    - Set `timeframe = 'D'` for all existing rows.
    - Set `is_bullish = true` where `ema_signal == 'bullish'`. *Note: This is a known lossy approximation for historical rows to distinguish trend state.*
    - Set `scored_at = date`.

## Implementation Tasks (Conceptual)
1. **Migration:** Alembic script for table refactor.
2. **Utils:** Add `resample_ohlcv` helper to `pipeline/utils.py`.
3. **Scorer:** Refactor `scorer.py` to accept a timeframe and apply tiered logic.
4. **Orchestrator:** Update `orchestrator.py` to handle 3y data, resampling, and multi-timeframe persistence.
5. **Reporter:** Update query to calculate confluence.
