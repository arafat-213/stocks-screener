# Journal API Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the journal API to use the centralized `apiClient` in `frontend/src/api/client.js` and remove the redundant `journal.js` file.

**Architecture:** Move API methods to `client.js`, standardize on individual function exports using `apiClient`.

**Tech Stack:** React, Axios (via `apiClient`)

---

### Task 1: Add Journal API methods to `client.js`

**Files:**
- Modify: `frontend/src/api/client.js`

- [ ] **Step 1: Append Journal API methods**

Add the following to the end of `frontend/src/api/client.js`:

```javascript
// Journal
export const getJournalOpen = () => apiClient.get('/journal/open');
export const getJournalClosed = () => apiClient.get('/journal/closed');
export const getJournalStats = () => apiClient.get('/journal/stats');
export const createJournalEntry = (data) => apiClient.post('/journal/', data);
export const closeJournalEntry = (id, data) => apiClient.patch(`/journal/${id}/close`, data);
```

- [ ] **Step 2: Verify code syntax**

Ensure the file is syntactically correct and methods are exported.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.js
git commit -m "feat(api): add journal API methods to centralized client"
```

### Task 2: Remove Redundant `journal.js`

**Files:**
- Delete: `frontend/src/api/journal.js`

- [ ] **Step 1: Delete the file**

Run: `rm frontend/src/api/journal.js`

- [ ] **Step 2: Verify deletion**

Run: `ls frontend/src/api/journal.js`
Expected: File not found error.

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(api): remove redundant journal.js"
```

### Task 3: Global Search and Cleanup

**Files:**
- Modify: Any files found importing `journalApi` (previously checked, but good to double-check).

- [ ] **Step 1: Search for `journalApi` references**

Run: `grep -r "journalApi" frontend/src`
Expected: No results.

- [ ] **Step 2: Search for `api/journal` imports**

Run: `grep -r "api/journal" frontend/src`
Expected: No results.

- [ ] **Step 3: Final Verification**

Ensure `frontend/src/pages/Journal.jsx` still works (it was a placeholder and didn't have imports anyway).
