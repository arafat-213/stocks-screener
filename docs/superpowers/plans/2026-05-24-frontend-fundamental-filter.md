# Frontend Fundamental Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to toggle fundamental hard-filtering and visualize fundamental quality for all stocks on the dashboard.

**Architecture:** Add `fundamentalFilter` state to Dashboard, pass it to backend, and render `fundamental_quality` badges.

**Tech Stack:** React, Tailwind CSS, Lucide Icons.

---

### Task 1: Dashboard State and API Integration

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Add `fundamentalFilter` state**

```javascript
  const [fundamentalFilter, setFundamentalFilter] = useState(true);
```

- [ ] **Step 2: Update `loadMore` to pass `fundamental_filter`**

```javascript
      const data = await fetchResults({
        offset: currentOffset,
        limit: 50,
        sector: selectedSectors.join(','),
        confluence: confluenceFilter === 'watchlist' ? undefined : confluenceFilter,
        symbols: confluenceFilter === 'watchlist' ? [...watchlist].join(',') : undefined,
        sort_by: sortBy,
        fundamental_filter: fundamentalFilter // Add this
      });
```

- [ ] **Step 3: Add `fundamentalFilter` to dependency arrays**

Update `useEffect` that triggers `loadMore(true)`:
```javascript
  useEffect(() => {
    loadMore(true);
  }, [selectedSectors, confluenceFilter, sortBy, fundamentalFilter]);
```

### Task 2: UI Toggle in Dashboard Header

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`
- Modify: `frontend/src/components/FilterBottomSheet.jsx`

- [ ] **Step 1: Add toggle UI to Dashboard desktop filter section**

Add a toggle button/checkbox in the desktop filter bar.

- [ ] **Step 2: Pass state and setter to `FilterBottomSheet`**

```javascript
      <FilterBottomSheet
        // ...
        fundamentalFilter={fundamentalFilter}
        setFundamentalFilter={setFundamentalFilter}
      />
```

- [ ] **Step 3: Add toggle UI to `FilterBottomSheet`**

### Task 3: Fundamental Quality Badges

**Files:**
- Modify: `frontend/src/components/StockCard.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Update `StockCard.jsx` to show quality badges**

Render badges for `profitability_ok` and `debt_ok` from `fundamental_quality`.

- [ ] **Step 2: Update `columns` in `Dashboard.jsx` (Table view)**

Add a "Quality" column that renders these badges.

---
