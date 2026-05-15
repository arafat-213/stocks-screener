# Trading Plan Component Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a reusable `TradingPlan` component to display actionable trade setup details.

**Architecture:** A presentation component and its associated CSS, using design tokens for theme consistency.

**Tech Stack:** React, Lucide Icons, CSS Modules (simulated via global/scoped CSS).

---

### Task 1: Create TradingPlan.jsx

**Files:**
- Create: `frontend/src/components/TradingPlan.jsx`

- [ ] **Step 1: Write the component code**

```jsx
import React from 'react';
import { Target, ShieldAlert, Zap } from 'lucide-react';
import './TradingPlan.css';

const TradingPlan = ({ setup }) => {
  if (!setup) return null;

  return (
    <div className="trading-plan-card">
      <div className="plan-header">
        <Zap size={18} className="text-primary" />
        <h3>Trading Plan: {setup.setup_type.replace(/_/g, ' ')}</h3>
      </div>
      
      <div className="plan-grid">
        <div className="plan-item entry">
          <label>Entry Zone</label>
          <div className="value">₹{setup.entry_zone.low.toFixed(2)} - ₹{setup.entry_zone.high.toFixed(2)}</div>
        </div>
        
        <div className="plan-item stop">
          <label><ShieldAlert size={14} /> Stop Loss</label>
          <div className="value bearish">₹{setup.stop_loss.toFixed(2)}</div>
          <span className="basis">{setup.stop_basis}</span>
        </div>
        
        <div className="plan-targets">
          <label><Target size={14} /> Targets (R-Multiple)</label>
          <div className="target-list">
            {setup.targets.map((t, i) => (
              <div key={i} className="target-pill">
                <span className="rr">{t.rr}R</span>
                <span className="price">₹{t.level.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      
      <div className="plan-footer">
        <span>Risk per share: ₹{setup.risk_per_share.toFixed(2)}</span>
        <span>ATR: {setup.atr.toFixed(1)}</span>
      </div>
    </div>
  );
};

export default TradingPlan;
```

### Task 2: Create TradingPlan.css

**Files:**
- Create: `frontend/src/components/TradingPlan.css`

- [ ] **Step 1: Write the CSS**

```css
.trading-plan-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: var(--shadow-sm);
  margin-top: 16px;
}

.plan-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  text-transform: capitalize;
}

.plan-header h3 {
  font-size: 1rem;
  color: var(--color-text);
  margin: 0;
}

.text-primary {
  color: var(--color-primary);
}

.plan-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.plan-item label, .plan-targets label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.75rem;
  color: var(--color-text-muted);
  margin-bottom: 4px;
}

.plan-item .value {
  font-size: 1.1rem;
  font-weight: 700;
  font-family: var(--font-mono);
}

.plan-item .value.bearish {
  color: var(--color-bearish);
}

.plan-item .basis {
  font-size: 0.7rem;
  color: var(--color-text-muted);
}

.plan-targets {
  grid-column: span 2;
}

.target-list {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.target-pill {
  display: flex;
  flex-direction: column;
  background: rgba(34, 197, 94, 0.08);
  padding: 8px 12px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(34, 197, 94, 0.2);
}

.target-pill .rr {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--color-bullish);
}

.target-pill .price {
  font-weight: 700;
  font-family: var(--font-mono);
}

.plan-footer {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--color-text-muted);
  border-top: 1px solid var(--color-border);
  padding-top: 12px;
}
```

### Task 3: Verification & Commit

- [ ] **Step 1: Check for syntax errors**

Run: `npx eslint frontend/src/components/TradingPlan.jsx` (if available) or just manual check.

- [ ] **Step 2: Commit changes**

```bash
git add frontend/src/components/TradingPlan.*
git commit -m "feat: add TradingPlan component"
```
