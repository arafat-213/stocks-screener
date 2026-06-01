# Design Doc: Legacy Fundamental Code Cleanup

**Status:** Approved
**Date:** 2026-06-01
**Author:** Gemini CLI

## 1. Objective
Following the transition to a 100-point Technical Momentum Engine, the application still contains "ghosts" of the previous fundamental analysis system. This cleanup aims to remove redundant logic, expensive database joins, and cluttered UI elements while preserving basic metadata (Market Cap and Sector) that remains useful for filtering.

## 2. Scope
- **Backend:** `backend/app/routers/dashboard.py`
- **Frontend:**
    - `frontend/src/components/ScreenResultTable.jsx` (Legacy columns)
    - `frontend/src/pages/Dashboard.jsx` (Filters state and table columns)
    - `frontend/src/components/FilterBottomSheet.jsx` (Mobile filters)

## 3. Architecture & Data Flow

### 3.1 Backend: Surgical Refactor
We will strip the API response of financial ratios while keeping the `FundamentalCache` join purely for `market_cap_category` and `sector` metadata.

**Key Changes:**
- **Remove `sort_by == "pe"`:** Remove the logic that joins `FundamentalData` to sort by P/E ratio.
- **Simplify `enriched_data`:**
    - Remove the `fundamental_quality` object from the response.
    - Reduce the `fundamentals` object to only: `{ "market_cap": stock.market_cap, "market_cap_category": cache.market_cap_category }`.
    - Delete mapping for: `pe`, `pb`, `roe`, `roce`, `peg`, `yield`, `debt_equity`.
- **Remove Param:** Remove `fundamental_filter` from `get_dashboard_results` signature and logic.

### 3.2 Frontend: UI Simplification
Clean up the components to reflect the new technical-only data structure and remove "ghost" filters.

**Key Changes in `ScreenResultTable.jsx`:**
- **Delete `COLUMN_META` entries:** `peg_ratio`, `ev_to_ebitda`, `dividend_yield`, `roce`, `de_ratio`, `fcf_positive`, `dividend_consistency`, `quality_tier`.
- **Update `SCREEN_COLUMNS`:** Ensure all preset screen columns use only technical or metadata fields.

**Key Changes in `Dashboard.jsx`:**
- **State Removal:** Remove `fundamentalFilter` state and logic.
- **Table Column Removal:** Remove the "Quality", "ROE %", and "P/E" columns from the `columns` array.
- **Sort Option Removal:** Remove the "Value (P/E)" option from the sort `Select` component.
- **Filter UI Removal (Desktop):** Delete the inline "Quality Filter" section (Strict / Show All buttons) found within the `!isMobile` desktop layout block.
- **API Integration:** Remove `fundamental_filter` from the `fetchResults` call parameters.

**Key Changes in `FilterBottomSheet.jsx`:**
- **Prop Removal:** Remove `fundamentalFilter` and `setFundamentalFilter` from props.
- **Filter UI Removal:** Delete the "Quality Filter" section.

## 4. Database Integrity
**Constraint:** `FundamentalCache` and `FundamentalData` tables MUST remain in the database. No migrations or deletions of table data will be performed.

## 5. Verification Plan
- **Backend:** Run `pytest` to ensure the dashboard router still functions and returns the expected technical data.
- **Frontend:** Manual verification of the Results Table to ensure no "—" ghost columns remain and that the "Market Cap" badge still displays correctly.
- **Performance:** Confirm the removal of the `FundamentalData` join reduces query complexity for the main dashboard fetch.
