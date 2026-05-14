# Dashboard Infinite Scroll Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize dashboard performance by implementing server-side pagination (50 items per batch) and frontend infinite scrolling, while moving sorting/filtering to the database.

**Architecture:** 
1. **Backend:** Refactor SQLAlchemy query in `dashboard.py` to use SQL-level `ORDER BY`, `WHERE`, `LIMIT`, and `OFFSET`. 
2. **Frontend:** Update `Dashboard.jsx` to use an `IntersectionObserver` for incremental loading and handle filter resets.
3. **Watchlist:** Add a specific "Fetch by Symbols" capability to the API to support the client-side local-storage watchlist without needing the full universe.

**Tech Stack:** FastAPI, SQLAlchemy, React, IntersectionObserver API.

---

### Task 1: Backend API Refactoring (SQL-level Logic)

**Files:**
- Modify: `backend/app/routers/dashboard.py`

- [ ] **Step 1: Refactor query to include SQL-level confluence and sorting**
- [ ] **Step 2: Add Filtering and Pagination params**
- [ ] **Step 3: Update existing tests or add new ones**

---

### Task 2: Frontend API Client Update

**Files:**
- Modify: `frontend/src/api/client.js`

- [ ] **Step 1: Update `fetchResults` to accept parameters**

---

### Task 3: Dashboard Infinite Scroll Implementation

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Replace `useFetch` with manual state management for incremental loading**
- [ ] **Step 2: Implement `IntersectionObserver` sentinel**
- [ ] **Step 3: Handle Filter Resets**

---

### Task 4: Watchlist Mode Logic

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Implement "Watchlist Mode" toggle**

---

### Task 5: Verification & Cleanup

- [ ] **Step 1: Verify pagination loads 50 items initially**
- [ ] **Step 2: Verify scrolling to bottom triggers next 50**
- [ ] **Step 3: Verify sector filtering resets list and starts from offset 0**
- [ ] **Step 4: Verify watchlist view still works with local storage symbols**
