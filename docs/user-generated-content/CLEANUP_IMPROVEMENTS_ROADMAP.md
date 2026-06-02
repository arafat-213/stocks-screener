# Stock AI Execution Roadmap

This document outlines the recommended sequence for implementing improvements and cleaning up legacy technical debt. This "Hybrid Approach" balances the need for foundational stability with the desire for strategic advancement.

---

## Phase 1: Foundational Stability (Immediate Priority) [STATUS: RESOLVED]
**Goal:** Fix critical data integrity issues and prevent system crashes.

1.  **Enforce the NSE Suffix (#1):** [STATUS: RESOLVED]
    *   Update `get_nse_symbols` to return `.NS` symbols.
    *   Ensure all database lookups and writes use the `.NS` suffix.
    *   Scrub the current database of raw symbols to avoid fragmented records.
2.  **Fix Timezone Fragility (#2):** [STATUS: RESOLVED]
    *   Add `df.index = df.index.tz_localize(None)` immediately after data retrieval in the fetcher/orchestrator.
    *   Ensure all internal comparisons use naive timestamps to prevent `TypeError`.
---

## Phase 2: Structural Cleanup (Clearing the Path)
**Goal:** Simplify the codebase by removing obsolete logic and redundant data structures.

3.  **Pipeline "Debris" Cleanup (Cleanup #1):**
    *   Remove unused legacy functions from `backend/app/pipeline/screener.py` (e.g., `fetch_and_cache_deep_fundamentals`, `passes_tier1_fast_filters`).
    *   Unify scoring shims in `scorer.py` into the main `MomentumScorer`.
4.  **Dashboard Optimization (Cleanup #2):**
    *   Refactor `backend/app/routers/dashboard.py` to remove unnecessary joins and return cleaner data structures.
    *   Ensure the frontend only receives the fundamental data it actually displays (Market Cap).
5.  **Database Model Pruning (Cleanup #3):**
    *   Remove obsolete tables (`FundamentalData`, `FundamentalCache`) and redundant columns (like `quality_tier`) from `models.py`.
    *   Perform a database migration to align the schema with the current 100-point technical system.

---

## Phase 3: Architectural Unification (The "Source of Truth")
**Goal:** Centralize strategy logic and ensure the testing suite validates the modern engine.

6.  **Centralize Strategy Logic (#4):**
    *   Create `backend/app/core/strategy.py`.
    *   Unify `calculate_technical_score` so it is used by both the Live Pipeline and the Backtest Engine.
7.  **Sync Tests to Reality (#3):**
    *   Rewrite `test_scorer_fixes.py` and other outdated tests to validate the 100-point scale.
    *   Add edge-case tests for new technical tiers (EMA Crosses, MACD Decoupling).

---

## Phase 4: Strategic Tuning & Alpha
**Goal:** Optimize trading performance and implement advanced exit management.

8.  **Strategy Refining (#5 - #9):**
    *   Implement "State-Based" exit signals (handling RSI > 80 as "Overextended" rather than a score-killer).
    *   Adopt ATR-based stop losses consistently.
    *   Refactor the 200 EMA filter to be a scoring factor rather than a binary death penalty.
9.  **Validation Framework (#10):**
    *   Expose indicator weights as parameters in `UnifiedTradingConfig`.
    *   Update `parameter_sweep.py` to allow for multi-parameter optimization.

---

## Summary of Sequence
| Order | Task | Category | Why? |
| :--- | :--- | :--- | :--- |
| 1 | **NSE Suffix & Timezones** | Improvement | Prevents data corruption and crashes. |
| 2 | **Pipeline & Dashboard Cleanup** | Cleanup | Makes architectural refactoring safer. |
| 3 | **Centralized Strategy & Tests** | Improvement | Establishes a single source of truth. |
| 4 | **Math & Signal Refinement** | Improvement | Enhances trading performance (Alpha). |
