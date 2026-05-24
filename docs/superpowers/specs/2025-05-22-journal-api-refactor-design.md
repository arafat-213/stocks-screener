# Design Spec: Refactoring Journal API

**Topic**: Frontend API & Route Setup - Refactoring Journal API
**Date**: 2025-05-22
**Status**: Approved

## 1. Background
The current implementation of the journal API in `frontend/src/api/journal.js` uses raw `axios` and a separate base URL configuration. This deviates from the project's centralized API pattern established in `frontend/src/api/client.js`, which uses a pre-configured `apiClient` instance.

## 2. Goals
- Centralize all API calls within `frontend/src/api/client.js`.
- Use the `apiClient` instance for all journal-related requests.
- Standardize the naming and export pattern for journal API methods.
- Remove redundant files.

## 3. Proposed Changes

### 3.1 Modify `frontend/src/api/client.js`
Add the following methods to the end of the file:
```javascript
// Journal
export const getJournalOpen = () => apiClient.get('/journal/open');
export const getJournalClosed = () => apiClient.get('/journal/closed');
export const getJournalStats = () => apiClient.get('/journal/stats');
export const createJournalEntry = (data) => apiClient.post('/journal/', data);
export const closeJournalEntry = (id, data) => apiClient.patch(`/journal/${id}/close`, data);
```

### 3.2 Delete `frontend/src/api/journal.js`
Remove the file entirely.

### 3.3 Update Consumers
No other files currently import `journalApi`, so no updates to consumers are required.

## 4. Verification Plan
- Verify that `frontend/src/api/client.js` contains the new methods.
- Verify that `frontend/src/api/journal.js` has been deleted.
- Run a grep search to ensure no `journalApi` references remain in the codebase.
