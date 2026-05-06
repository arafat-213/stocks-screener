# Stock AI Terminal Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the frontend to a professional "Terminal Aesthetic" with a high-density sidebar and grid layout.

**Architecture:** Two-pane layout with a fixed sidebar for system status and a responsive main grid for stock data. Uses CSS variables for consistent design tokens.

**Tech Stack:** React, Lucide-React, Vanilla CSS.

---

### Task 1: Setup & CSS Design Tokens

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/App.css`

- [ ] **Step 1: Update design tokens in `index.css`**

```css
:root {
  --sidebar-width: 260px;
  --bg-primary: #ffffff;
  --bg-secondary: #f9fafb;
  --text-primary: #111827;
  --text-secondary: #6b7280;
  --border-color: #e5e7eb;
  --accent-color: #16a34a; /* Green */
  --danger-color: #dc2626; /* Red */
  --warning-color: #d97706; /* Yellow/Orange */
  
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
```

- [ ] **Step 2: Add global layout styles in `index.css`**

```css
body {
  margin: 0;
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, sans-serif;
}

#root {
  display: flex;
  min-height: 100vh;
}
```

- [ ] **Step 3: Commit CSS changes**

```bash
git add frontend/src/index.css frontend/src/App.css
git commit -m "style: add dashboard design tokens and global layout"
```

---

### Task 2: Sidebar & Two-Pane Layout Refactor

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/App.css`

- [ ] **Step 1: Refactor `App.jsx` structure**

```javascript
import React, { useEffect, useState } from 'react';
import { Layout, Play, Activity } from 'lucide-react';
import { getTopStocks, getStatus, runScreener } from './api';
import ScoreCard from './components/ScoreCard';
import './App.css';

function App() {
  const [stocks, setStocks] = useState([]);
  const [status, setStatus] = useState({ status: 'idle' });

  const fetchData = async () => {
    try {
      const [stocksRes, statusRes] = await Promise.all([getTopStocks(), getStatus()]);
      setStocks(stocksRes.data);
      setStatus(statusRes.data);
    } catch (err) {
      console.error("Fetch failed", err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleRun = async () => {
    await runScreener();
    fetchData();
  };

  return (
    <div className="dashboard-container">
      <aside className="sidebar">
        <div className="sidebar-header">
          <Activity className="icon-accent" />
          <h1>Stock AI</h1>
        </div>
        
        <div className="status-module">
          <div className="status-indicator">
            <span className={`dot ${status.status}`}></span>
            <span className="status-text">Pipeline: {status.status.toUpperCase()}</span>
          </div>
          <p className="last-run">Scored: {status.scored || 0}</p>
        </div>

        <button 
          className="run-button" 
          onClick={handleRun} 
          disabled={status.status === 'running'}
        >
          <Play size={16} />
          Run Screener
        </button>
      </aside>

      <main className="main-content">
        <header className="content-header">
          <h2>Top Scored Stocks</h2>
          <span className="timestamp">Real-time Analysis</span>
        </header>
        
        <div className="stock-grid">
          {stocks.map(s => <ScoreCard key={s.symbol} stock={s} />)}
        </div>
      </main>
    </div>
  );
}

export default App;
```

- [ ] **Step 2: Add sidebar and grid styles in `App.css`**

```css
.dashboard-container {
  display: flex;
  width: 100%;
}

.sidebar {
  width: var(--sidebar-width);
  background: var(--bg-primary);
  border-right: 1px solid var(--border-color);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 32px;
  position: fixed;
  height: 100vh;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sidebar-header h1 {
  font-size: 20px;
  margin: 0;
  font-weight: 700;
}

.main-content {
  margin-left: var(--sidebar-width);
  flex-grow: 1;
  padding: 40px;
}

.stock-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.run-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s;
}

.run-button:hover:not(:disabled) {
  background: var(--border-color);
}
```

- [ ] **Step 3: Commit layout changes**

```bash
git add frontend/src/App.jsx frontend/src/App.css
git commit -m "feat: implement two-pane dashboard layout and sidebar"
```

---

### Task 3: Terminal Aesthetic ScoreCard Update

**Files:**
- Modify: `frontend/src/components/ScoreCard.jsx`

- [ ] **Step 1: Implement new `ScoreCard` structure**

```javascript
import React from 'react';

export default function ScoreCard({ stock }) {
  const isHighRsi = stock.rsi > 70;
  const isLowRsi = stock.rsi < 30;
  const isBuy = stock.signal === 'BUY';
  const isSell = stock.signal === 'SELL';

  return (
    <div className="score-card">
      <div className="card-header">
        <span className="symbol">{stock.symbol}</span>
        <span className="score-value">{stock.score}</span>
      </div>
      <div className="divider"></div>
      <div className="metrics-grid">
        <div className="metric">
          <label>RSI</label>
          <span className={`value ${isHighRsi ? 'danger' : isLowRsi ? 'success' : ''}`}>
            {stock.rsi.toFixed(2)}
          </span>
        </div>
        <div className="metric">
          <label>SIGNAL</label>
          <span className={`value bold ${isBuy ? 'success' : isSell ? 'danger' : ''}`}>
            {stock.signal}
          </span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add ScoreCard styles in `App.css`**

```css
.score-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  padding: 16px;
  border-radius: 4px;
  transition: border-color 0.2s;
}

.score-card:hover {
  border-color: var(--text-secondary);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.symbol {
  font-weight: 700;
  font-size: 18px;
}

.score-value {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 600;
}

.divider {
  height: 1px;
  background: var(--border-color);
  margin-bottom: 12px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.metric {
  display: flex;
  flex-direction: column;
}

.metric label {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-secondary);
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.metric .value {
  font-family: var(--font-mono);
  font-size: 14px;
}

.success { color: var(--accent-color); }
.danger { color: var(--danger-color); }
.bold { font-weight: 700; }
```

- [ ] **Step 3: Commit ScoreCard changes**

```bash
git add frontend/src/components/ScoreCard.jsx frontend/src/App.css
git commit -m "feat: update ScoreCard to professional terminal aesthetic"
```

---

### Task 4: Cleanup & Verification

- [ ] **Step 1: Move Design Spec and Plan to project docs**

Run:
```bash
mkdir -p docs/superpowers/specs docs/superpowers/plans
cp /home/bacancy/.gemini/tmp/stock-ai/4be19376-5c2e-40b4-812b-dc83449746d5/plans/2026-05-06-dashboard-design.md docs/superpowers/specs/
cp /home/bacancy/.gemini/tmp/stock-ai/4be19376-5c2e-40b4-812b-dc83449746d5/plans/2026-05-06-dashboard-implementation.md docs/superpowers/plans/
```

- [ ] **Step 2: Run frontend and verify look & feel**

Run: `cd frontend && npm run dev`
Expected: Dashboard opens with a professional sidebar on the left and a clean grid of stocks. Colors (Green/Red) are correctly applied to RSI and Signals.

- [ ] **Step 3: Final Commit**

```bash
git add docs/superpowers/
git commit -m "docs: add dashboard design and implementation plan"
```
