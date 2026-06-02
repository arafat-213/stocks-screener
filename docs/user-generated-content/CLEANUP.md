The pipeline refactoring for the Technical Momentum Engine has left several legacy "ghosts" in the codebase. Since we've moved to a 100-point technical system, the following areas are now
  either dead code, redundant logic, or architectural mismatches:

#2.  2. Dashboard Logic (backend/app/routers/dashboard.py) [STATUS: RESOLVED]
   * Heavily Impacted: This is the most "cluttered" file. It still:
       * Joins FundamentalCache and FundamentalData on every dashboard fetch, even though we only need market_cap. This is a performance drag.
       * Still supports Sorting by PE Ratio (sort_by == "pe"), which will now return unpredictable results or just nulls.
       * The enriched_data structure returns a large fundamentals object with mostly null values to the frontend.
   * UI No-Op: The fundamental_filter parameter is still accepted but is effectively a "No-Op" in the logic.
   * Status: `dashboard.py` has been optimized. `get_dashboard_results` now calculates `market_cap_category` on the fly, avoiding the join to `FundamentalCache`. Sorting by `pe` has been removed.
...
#1.  3. Pipeline "Debris" (backend/app/pipeline/) [STATUS: RESOLVED]
   * screener.py: This file was ~80% dead code. Functions like fetch_and_cache_deep_fundamentals, check_profitability_streak, and passes_tier1_fast_filters have been removed.
   * scorer.py: This shim has been removed, and all callers (including the Backtest Engine) now use `MomentumScorer` directly.
   * Status: Legacy files `screener.py`, `scorer.py`, and the unused `test_backoff_logic.py` have been deleted. `engine.py` was refactored to use `MomentumScorer` directly.

#4.  4. Backtest Engine (backend/app/backtest/engine.py) [STATUS: RESOLVED]
   * Logic Divergence: The backtester still tries to calculate a "Fundamental Score" if a flag is set, which will now fail or return 0.
   * Signal Tiering: It uses a private _compute_signal_tier function (returning Tiers 1-4) that is completely different from the 0-100 scoring logic used by the rest of the app. This creates
     a "truth mismatch" between backtest results and live scanner results.
   * Status: Logic has been centralized in `TechnicalStrategy`. `engine.py` now uses the same scoring engine as the live pipeline.

#6.  5. Frontend UI Components [STATUS: PARTIALLY RESOLVED]
   * ScreenResultTable.jsx: Still contains formatters and column definitions for peg_ratio, roce, and de_ratio. These columns will appear as "—" or empty, cluttering the table.
   * Dashboard Filters: The UI still shows a "Fundamental Filter" toggle and "Quality Tier" badges in the Watchlist/Journal, which are now functionally dead.
   * Status: `ScreenResultTable.jsx` no longer contains fundamental columns (PEG, ROCE, etc.). However, `Backtest.jsx` still shows a "Fundamental Filter" toggle.

#5.  6. Pledging Data Source [STATUS: RESOLVED]
   * The "Binary Killer" Gap: While we implemented the pledged_percent > 30% filter, the data source is currently a random simulation in update_pledging.py. We need to decide if we want to
     hook this up to a real BSE/NSE feed or keep it as a placeholder.
   * Status: `update_pledging.py` has been removed. The pipeline no longer uses random pledging data.
