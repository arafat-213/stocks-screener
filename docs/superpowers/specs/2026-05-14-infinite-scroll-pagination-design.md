# Design Spec: Dashboard Infinite Scroll Pagination

**Date:** 2026-05-14
**Status:** Draft
**Topic:** Performance optimization for the Main Dashboard via server-side pagination and frontend infinite scrolling.

---

## 1. Problem Statement
The current `/api/dashboard/screener/results` endpoint returns the entire "Elite List" (~1,100+ stocks) in a single JSON payload. 
- **Payload Size:** High (Multi-MB)
- **Frontend Performance:** Sorting and filtering 1000+ items in a table/grid is becoming laggy.
- **Initial Load:** Slow, as the user must wait for the full list before anything renders.

## 2. Proposed Solution
Implement **Offset-based Pagination** on the backend and **Infinite Scrolling** on the frontend using the `IntersectionObserver` API.

---

## 3. Backend Architecture Changes

### 3.1 API Endpoint Evolution
`GET /api/dashboard/screener/results`

**Request Parameters:**
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `offset` | int | 0 | Starting index for the slice. |
| `limit` | int | 50 | Number of items to return. |
| `sector` | string | null | (Optional) Filter by sector. |
| `confluence`| string | null | (Optional) '3' or '2+'. |
| `sort_by` | string | 'confluence' | Sort priority: 'confluence', 'score', 'rsi', 'pe'. |

**Response Schema:**
```json
{
  "total": 1099,
  "offset": 0,
  "limit": 50,
  "has_more": true,
  "items": [
    {
      "symbol": "BBTC.NS",
      "name": "...",
      "confluence_count": 1,
      "timeframes": { "D": {...}, "W": {...}, "M": {...} },
      "fundamentals": { ... }
    }
  ]
}
```

### 3.2 SQL Refactoring (`backend/app/routers/dashboard.py`)
- **Query Consolidation:** Use SQLAlchemy to calculate `confluence_count` in the database using a `CASE` statement inside `func.sum()`.
- **Server-Side Sorting:** Move the logic from `final_results.sort()` to a SQL `ORDER BY` clause.
  - *Default Sort:* `confluence_count DESC`, then `TechnicalSignal.is_bullish DESC`, then `TechnicalSignal.entry_score DESC`.
- **Filtering:** Apply `WHERE` clauses for `sector` and `confluence` before the `LIMIT` and `OFFSET`.

---

## 4. Frontend Architecture Changes

### 4.1 Infinite Scroll Hook (`useInfiniteScroll.js`)
Create a new hook to manage the observation of a "Sentinel" element at the bottom of the list.

### 4.2 Dashboard Component (`Dashboard.jsx`)
- **State Management:**
  - `stocks`: Now an array that grows (appends new batches).
  - `page`: Track current offset or page index.
  - `hasMore`: Boolean to stop fetching when `total` is reached.
- **Filter Reset:** When a filter (Sector/Confluence) is changed:
  1. Clear `stocks` array.
  2. Reset `page` to 0.
  3. Trigger fresh fetch.
- **View Modes:**
  - Both **Table** and **Grid** views will render the "Sentinel" at the bottom of their respective containers.

### 4.3 Watchlist Mode
- A toggle in the UI will switch between "All Stocks" (Paginated) and "My Watchlist" (Client-side filtered).
- When "My Watchlist" is active:
  - Infinite scroll is disabled.
  - The UI uses the existing `isWatched` local filter on the **entire** available dataset (or a fallback fetch if the list is empty).

---

## 5. Success Criteria
1. Initial dashboard load time reduced by >70%.
2. JSON payload size for initial load reduced to <100KB.
3. User can scroll through 1000+ stocks without noticeable lag or large memory spikes.
4. Sorting/Filtering results correctly reflect the entire universe, not just the visible page.

## 6. Testing Strategy
- **Backend:** Unit tests for the query logic with different `limit` and `offset` values.
- **Integration:** Verify that changing a filter resets the pagination state correctly.
- **Manual:** Check for "flicker" or double-fetching during infinite scroll triggers.
