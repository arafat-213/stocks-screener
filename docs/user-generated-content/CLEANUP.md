The pipeline refactoring for the Technical Momentum Engine has left several legacy "ghosts" in the codebase. Since we've moved to a 100-point technical system, the following areas are now
  either dead code, redundant logic, or architectural mismatches:

#3.  1. Database & Models (backend/app/db/models.py) [STATUS: UNRESOLVED]
   * Legacy Tables: FundamentalData and FundamentalCache are now 90% obsolete. They still hold market_cap and pledged_percent, but the other ~15 fields (ROE, ROCE, Debt/Equity, etc.) are
     dead weight.
   * Zombie Columns:
       * ScreenResult, AlertLog, Watchlist, and TradeJournal all still carry a quality_tier column ('A', 'B', 'C'). Since we now use a continuous 0-100 score, these "Tiers" are meaningless
         and often empty.
       * PipelineRun still tracks tier1_count and tier2_count, which no longer reflect the current single-pass logic.
   * Verification: Checked backend/app/db/models.py - these tables and columns still exist.

#2.  2. Dashboard Logic (backend/app/routers/dashboard.py) [STATUS: PARTIALLY RESOLVED]
   * Heavily Impacted: This is the most "cluttered" file. It still:
       * Joins FundamentalCache and FundamentalData on every dashboard fetch, even though we only need market_cap. This is a performance drag.
       * Still supports Sorting by PE Ratio (sort_by == "pe"), which will now return unpredictable results or just nulls.
       * The enriched_data structure returns a large fundamentals object with mostly null values to the frontend.
   * UI No-Op: The fundamental_filter parameter is still accepted but is effectively a "No-Op" in the logic.
   * Status: `dashboard.py` has been partially cleaned. `get_dashboard_results` now only joins `FundamentalCache` for `market_cap_category`. Sorting by `pe` has been removed (now only supports `score`, `rsi`, `confluence`).

#1.  3. Pipeline "Debris" (backend/app/pipeline/) [STATUS: PARTIALLY RESOLVED]
   * screener.py: This file is now ~80% dead code. Functions like fetch_and_cache_deep_fundamentals, check_profitability_streak, and passes_tier1_fast_filters (with its old 200 Cr liquidity
     rule) are no longer used by the Orchestrator but still exist in the module.
   * scorer.py: Contains calculate_fundamental_score and calculate_combined_score. These should be unified into a single MomentumScorer to remove the overhead of checking for non-existent
     fundamental data.
   * Status: `scorer.py` is now a shim calling `MomentumScorer`. `calculate_fundamental_score` and `calculate_combined_score` have been removed. `screener.py` still contains unused legacy functions like `needs_cache_refresh`.

#4.  4. Backtest Engine (backend/app/backtest/engine.py) [STATUS: RESOLVED]
   * Logic Divergence: The backtester still tries to calculate a "Fundamental Score" if a flag is set, which will now fail or return 0.
   * Signal Tiering: It uses a private _compute_signal_tier function (returning Tiers 1-4) that is completely different from the 0-100 scoring logic used by the rest of the app. This creates
     a "truth mismatch" between backtest results and live scanner results.
   * Verification: Checked backend/app/backtest/engine.py - `_compute_signal_tier` and fundamental scoring logic have been removed. It now uses `MomentumScorer` consistently.

#6.  5. Frontend UI Components [STATUS: PARTIALLY RESOLVED]
   * ScreenResultTable.jsx: Still contains formatters and column definitions for peg_ratio, roce, and de_ratio. These columns will appear as "—" or empty, cluttering the table.
   * Dashboard Filters: The UI still shows a "Fundamental Filter" toggle and "Quality Tier" badges in the Watchlist/Journal, which are now functionally dead.
   * Status: `ScreenResultTable.jsx` no longer contains fundamental columns (PEG, ROCE, etc.). However, `Backtest.jsx` still shows a "Fundamental Filter" toggle.

#5.  6. Pledging Data Source [STATUS: RESOLVED]
   * The "Binary Killer" Gap: While we implemented the pledged_percent > 30% filter, the data source is currently a random simulation in update_pledging.py. We need to decide if we want to
     hook this up to a real BSE/NSE feed or keep it as a placeholder.
   * Status: `update_pledging.py` has been removed. The pipeline no longer uses random pledging data.
