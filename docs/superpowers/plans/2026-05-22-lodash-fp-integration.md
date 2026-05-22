# lodash/fp Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace unsafe property access and array methods with `lodash/fp` safe operations across the frontend to eliminate "cannot read properties of undefined" errors.

**Architecture:** Direct modular imports from `lodash/fp/` to ensure tree-shaking and functional programming style (iteratee-first, data-last).

**Tech Stack:** React (Vite), lodash, Vitest.

---

### Task 1: Environment Setup

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install dependencies**
Run: `cd frontend && npm install lodash && npm install --save-dev @types/lodash`

- [ ] **Step 2: Verify installation**
Run: `ls frontend/node_modules/lodash/fp/map.js`
Expected: File exists.

- [ ] **Step 3: Commit**
```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: install lodash and types"
```

---

### Task 2: Refactor MarketTable.jsx (High Impact)

**Files:**
- Modify: `frontend/src/components/MarketTable.jsx`

- [ ] **Step 1: Update imports**
```javascript
import map from 'lodash/fp/map';
import size from 'lodash/fp/size';
// ... other imports
```

- [ ] **Step 2: Replace unsafe .map and .length**
```javascript
// Before: {Array.isArray(stocks) && stocks.map((stock, idx) => ...
// After: {map((stock, idx) => ( ... ), stocks)}

// Before: stocks.length
// After: size(stocks)
```

- [ ] **Step 3: Run build to check syntax**
Run: `cd frontend && npm run build`
Expected: Successful build.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/components/MarketTable.jsx
git commit -m "refactor: use lodash/fp in MarketTable"
```

---

### Task 3: Refactor ScreenResultTable.jsx (High Impact)

**Files:**
- Modify: `frontend/src/components/ScreenResultTable.jsx`

- [ ] **Step 1: Update imports**
```javascript
import map from 'lodash/fp/map';
// ...
```

- [ ] **Step 2: Replace unsafe .map**
Transform the nested mapping in `ScreenResultTable` to use `map(fn, data)`.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/components/ScreenResultTable.jsx
git commit -m "refactor: use lodash/fp in ScreenResultTable"
```

---

### Task 4: Batch Refactor Remaining Components

**Files:**
- Modify: `frontend/src/components/ChangeBanner.jsx`
- Modify: `frontend/src/components/FilterBottomSheet.jsx`
- Modify: `frontend/src/components/GlobalSearch.jsx`
- Modify: `frontend/src/components/MainLayout.jsx`
- Modify: `frontend/src/components/ScoreBreakdown.jsx`
- Modify: `frontend/src/components/StockCardSkeleton.jsx`

- [ ] **Step 1: Systematic replacement**
Iterate through each file and replace `.map(fn)` with `map(fn, data)` and `.filter(fn)` with `filter(fn, data)`. Ensure imports are added.

- [ ] **Step 2: Verify with build**
Run: `cd frontend && npm run build`

- [ ] **Step 3: Commit**
```bash
git add frontend/src/components/
git commit -m "refactor: apply lodash/fp to remaining components"
```

---

### Task 5: Refactor Pages and Utilities

**Files:**
- Modify: `frontend/src/pages/**/*` (if applicable)
- Modify: `frontend/src/utils/**/*`

- [ ] **Step 1: Scan and replace**
Search for remaining `.map`, `.filter`, `.length` on data objects in `pages/` and `utils/`. Apply the same transformation.

- [ ] **Step 2: Commit**
```bash
git add frontend/src/pages/ frontend/src/utils/
git commit -m "refactor: apply lodash/fp to pages and utils"
```

---

### Task 6: Final Validation & Smoke Test

- [ ] **Step 1: Run all tests**
Run: `cd frontend && npm test`
Expected: All tests pass.

- [ ] **Step 2: Final production build**
Run: `cd frontend && npm run build`
Expected: Success.
