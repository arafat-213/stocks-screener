# Paper Trading & Alert Alignment Design Spec

**Date:** 2026-05-30
**Status:** Draft

## 1. Goal
Align the Alert Engine and Paper Trading Engine to ensure that signals triggering email alerts also result in visible Paper Trading entries. Enhance the Portfolio dashboard to display "Pending" trades that are awaiting a pullback entry.

## 2. Architecture

### 2.1 Reliable Market Regime (Shared State)
To prevent the situation where Alerts fire but Paper Trading skips due to differing regime checks:
- **Pipeline Orchestrator (`backend/app/pipeline/orchestrator.py`):** At the end of every run, explicitly call `process_symbol` for `^NSEI` (Nifty 50). This ensures the `TechnicalSignal` table always has a fresh `is_bullish` flag for the index.
- **Shared Utility:** Create a helper in `backend/app/pipeline/utils.py` (or similar) called `get_market_regime(db)`.
- **Alert Engine (`backend/app/alerts/engine.py`):** Use the shared helper.
- **Paper Trading Engine (`backend/app/paper_trading/engine.py`):** Replace its internal `_get_regime` (which fetches fresh YFinance data) with the shared helper that reads from the DB.

### 2.2 Visibility: Syncing "Pending" Trades
To make the automated engine transparent to the user:
- **Status Update:** The `TradeJournal.status` field will now support `pending`.
- **Sync Service (`backend/app/backtest/sync_service.py`):**
    - Update `sync_paper_to_journal` to handle `PaperPosition` with `status="pending"`.
    - If a journal entry doesn't exist for a pending position, create it.
    - If a pending position is `expired` or `invalidated` in the paper engine, update the journal entry status to `skipped` or `expired`.
- **Engine Update (`backend/app/paper_trading/engine.py`):** Call `sync_paper_to_journal` immediately after creating a new pending position in `scan_for_new_signals`.

### 2.3 Frontend: Enhanced Portfolio Dashboard
- **`Portfolio.jsx`:**
    - Add a new "Pending" section or integrate into the "Open" table with a distinct "PENDING PULLBACK" badge.
    - For pending trades:
        - Show "Target Entry" (EMA20 level) instead of "Current P&L".
        - Show "Closeness" (how near the price got to the pullback zone).
        - Disable the "Close Trade" button for pending items (or change it to "Dismiss").

## 3. Implementation Plan Overview

### Task 1: Pipeline & Database Reliability
- Ensure `^NSEI` is always scored.
- Create shared regime check utility.
- Align Alert and Paper engines to use the shared check.

### Task 2: Sync Pending State
- Update `sync_paper_to_journal` to support `pending` and `expired` states.
- Ensure Paper Trading engine calls sync on signal discovery.

### Task 3: Portfolio UI Updates
- Update `journal` router to return pending status correctly.
- Update React components to render the "Pending" state beautifully.

## 4. Testing Strategy
- **Manual Verification:** Run the pipeline for a day where Nifty is bullish and verify a pending trade is created and visible in the UI.
- **Unit Tests:** Verify `sync_paper_to_journal` correctly maps paper states to journal states.
- **Regression:** Ensure manual trade entry still works without being affected by the new `paper` source logic.
