# Design Spec: Strategy Risk Upgrades (Smart Regime & Market Breadth) - FINAL PIVOT

**Date:** 2026-06-04
**Status:** Finalized (Post-Diagnostic)
**Topic:** Transitioning from "Price-Only" Regime to "Breadth-Aware" Portfolio Management.

## 1. Audit & Diagnostic Summary
*   **Failed Experiment (D10):** Forcing "Cash" (0% size) during low-trend (ADX < 20) periods successfully eliminated "trash" trades (69% Win Rate) but destroyed alpha (Sharpe 1.38, missed 50% of benchmark gains).
*   **Core Finding:** The Index price/ADX is a lagging indicator of market health. We need a "Market Breadth" filter to identify when a choppy index hides a strong underlying participation (the "Internal Bull Market").
*   **Redundancy Fix:** Sector concentration logic already exists in the engine; implementation will be limited to a configuration default update.

## 2. Proposed "Smart Regime" Engine

### 2.1 Market Breadth (The Participation Floor)
Implement a global participation filter to prevent entries during "hollow" rallies while enabling entries during "hidden" bull markets.

- **Config Update:** Add `min_market_breadth_pct: float = 40.0` to `UnifiedTradingConfig`.
- **Logic Implementation:**
    1. **Pre-calculation:** During `run_backtest` init, calculate `breadth_map` (`{date: pct_above_200ema}`).
    2. **Execution:** In `simulate_portfolio`, skip new entries if `breadth_map[current_date] < min_market_breadth_pct`.
- **Goal:** Filter out "Index-only" rallies where only a few large caps are moving.

### 2.2 Breadth-Adjusted Regime (Smart Overrides)
Instead of a hard ADX floor, use Breadth to dynamically adjust the `NEUTRAL` regime.

- **Proposed Logic:**
    - If Index is BULL (RSI > 55, ADX > 20) -> **Full Size (12%)**.
    - If Index is CHOP (Low ADX) AND **Breadth > 60%** -> **Upgrade to Full Size (12%)**. (Hidden Bull Market)
    - If Index is CHOP AND **Breadth < 40%** -> **Force Cash (0%)**. (Dangerous Sideways)
    - Else -> **Reduced Size (7%)**.

### 2.3 Sector Concentration (Configuration)
Enable the existing safeguard.
- **Action:** Update `UnifiedTradingConfig.max_sector_positions` default from `0` to `3`.

## 3. Technical Implementation (`backend/app/backtest/engine.py`)

### 3.1 Market Breadth Calculation (On-the-Fly)
Instead of querying the database, the Breadth Map will be calculated dynamically using the OHLCV Parquet data already loaded into memory.
**Advantages:**
- **Zero Database Dependency:** Eliminates the need for a multi-year `technical_signals` backfill.
- **Zero Look-ahead Bias:** Uses the exact same price series used for backtesting.
- **Performance:** Vectorized pandas operations across the 500-stock universe take < 50ms.

```python
def _calculate_breadth_map(all_dfs):
    # Vectorized calculation:
    # 1. Align all 'Close' and 'EMA_200' series into matrices.
    # 2. Compute (Close > EMA_200).sum(axis=1) / active_stocks.
    # Returns {date: percentage_float}
    pass
```

### 3.2 Portfolio Integration
- `run_backtest` will compute the `breadth_map` once after data loading.
- The map will be cached in `_SIGNAL_RUN_CACHE` to support rapid parameter sweeps.
- `simulate_portfolio` and `simulate_trades` will use the map to gate-keep entries.

## 4. Verification & Success Criteria
- **Primary Goal:** Recover the **Sharpe Ratio to > 2.20** while maintaining a **Win Rate > 55%**.
- **Secondary Goal:** Total Return must exceed the Benchmark (86%) with a **Max Drawdown < 7.0%**.
- **Test Case:** Run backtest on 2023 "Sideways" period. Verify the model stays in cash during the Aug-Oct dip (low breadth) but enters early in Nov (rising breadth) despite index ADX still being low.
