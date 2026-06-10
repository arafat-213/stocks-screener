# Design Spec: Dashboard Action Center

## 1. Overview
A hyper-focused "Action Center" section for the Dashboard to facilitate real-time trading decisions. It highlights stocks that are currently in their entry zones, nearing stop losses, or approaching targets.

## 2. User Experience (UX)
- **Location:** Dashboard page, below the market overview cards, above high-conviction digest.
- **Visibility:** Only displays when there is at least one actionable item.
- **Layout:** Three columns (Entry candidates, SL at risk, Target near).
- **Interactions:**
    - Clicking "EXECUTE" on an entry candidate opens the `ManualTradeModal` pre-filled.
    - Clicking "EXIT" on an SL/Target item opens the `CloseTradeModal`.

## 3. Technical Architecture

### 3.1 Backend (FastAPI)
- **New Endpoint:** `GET /dashboard/action-center`
- **Logic:**
    1. Query `Watchlist` where `status == "watching"`.
    2. Query `TradeJournal` where `status == "open"`.
    3. Fetch live prices for all symbols in these sets.
    4. Categorize:
        - `entry`: `watchlist.planned_entry_low <= price <= watchlist.planned_entry_high`
        - `sl_risk`: `price <= trade.stop_loss * 1.01` (within 1% of SL)
        - `target_near`: `price >= trade.target * 0.99` (within 1% of Target)
    5. Return JSON with three lists.

### 3.2 Frontend (React)
- **Component:** `ActionCenter.jsx`
- **Hook:** Use `useMarketData` or a new `useActionCenter` hook for periodic polling.
- **Aesthetics:**
    - `sl_risk` column should use `text-bearish` / `bg-red-100` accents.
    - `target_near` and `entry` columns should use `text-bullish` / `bg-green-100` accents.
    - Pulse animation for items within 0.25% of trigger.

## 4. Success Criteria
- [ ] Action Center displays only when items exist.
- [ ] Live prices correctly trigger categorization.
- [ ] Quick action buttons open correct modals with pre-filled data.
- [ ] Logic handles edge cases (missing SL/Target).
