# Frontend API & Route Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Setup frontend API service and routing for the Trade Journal feature.

**Architecture:** Create a dedicated API service for journal operations using axios and add the corresponding route to the React application.

**Tech Stack:** React, axios, react-router-dom

---

### Task 1: Create journal API service

**Files:**
- Create: `frontend/src/api/journal.js`

- [ ] **Step 1: Create the API service file**

```javascript
// frontend/src/api/journal.js
import axios from 'axios';
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const journalApi = {
  getOpen: () => axios.get(`${API_BASE}/journal/open`),
  getClosed: () => axios.get(`${API_BASE}/journal/closed`),
  getStats: () => axios.get(`${API_BASE}/journal/stats`),
  create: (data) => axios.post(`${API_BASE}/journal/`, data),
  close: (id, data) => axios.patch(`${API_BASE}/journal/${id}/close`, data),
};
```

### Task 2: Create placeholder Journal page

**Files:**
- Create: `frontend/src/pages/Journal.jsx`

- [ ] **Step 1: Create a minimal placeholder component**

```javascript
import React from 'react';

const Journal = () => {
  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold">Trade Journal</h1>
      <p>Journal content coming soon...</p>
    </div>
  );
};

export default Journal;
```

### Task 3: Add Route to App.jsx

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Update App.jsx with Journal route and import**

```javascript
// frontend/src/App.jsx
import { Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeProvider';
import MainLayout from './components/MainLayout';

// Pages
import Dashboard from './pages/Dashboard';
import Watchlist from './pages/Watchlist';
import StockDetail from './pages/StockDetail';
import Discover from './pages/Discover';
import Intelligence from './pages/Intelligence';
import System from './pages/System';
import Backtest from './pages/Backtest';
import PaperTrading from './pages/PaperTrading';
import Journal from './pages/Journal';

function App() {
  return (
    <ThemeProvider>
      <MainLayout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/stocks/:symbol" element={<StockDetail />} />
          <Route path="/discover" element={<Discover />} />
          <Route path="/paper" element={<PaperTrading />} />
          <Route path="/intel" element={<Intelligence />} />
          <Route path="/system" element={<System />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/journal" element={<Journal />} />
        </Routes>
      </MainLayout>
    </ThemeProvider>
  );
}

export default App;
```

### Task 4: Verify and Commit

- [ ] **Step 1: Verify syntax**

Run: `node -c frontend/src/api/journal.js` (basic syntax check for node-compatible JS)

- [ ] **Step 2: Commit changes**

```bash
git add frontend/src/api/journal.js frontend/src/pages/Journal.jsx frontend/src/App.jsx
git commit -m "feat: frontend api and route for journal"
```
