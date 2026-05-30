# Frontend: Chart Aware Trade setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the React frontend to display actionable trade setups (Entry, Stop, Target) and support ATR-based backtesting configurations.

**Architecture:**
1. **Presentation Layer:** Create reusable `SetupBadge` and `TradingPlan` components to visualize the `setup` object provided by the backend.
2. **Component Integration:** Inject these components into `StockCard`, `DataTable`, and `StockDetail` page.
3. **Configuration Layer:** Update the `Backtest` page state and UI to support new ATR-based parameters.

**Tech Stack:** React, Lucide-React, CSS Modules (or plain CSS as per project convention).

---

### Task 1: Create SetupBadge Component

**Files:**
- Create: `frontend/src/components/SetupBadge.jsx`
- Create: `frontend/src/components/SetupBadge.css`

- [ ] **Step 1: Write the component**

```jsx
import './SetupBadge.css';

const SETUP_LABELS = {
  ema_crossover: 'EMA Cross',
  pullback_to_ema20: 'EMA20 Pullback',
  resistance_breakout: 'Breakout',
  trend_continuation: 'Trend',
};

const SetupBadge = ({ setup }) => {
  if (!setup) return null;

  const label = SETUP_LABELS[setup.setup_type] || 'Setup';

  return (
    <div className={`setup-badge setup-${setup.setup_type}`}>
      {label}
    </div>
  );
};

export default SetupBadge;
```

- [ ] **Step 2: Create CSS**

```css
.setup-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.setup-ema_crossover { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
.setup-pullback_to_ema20 { background: rgba(16, 185, 129, 0.15); color: #10b981; }
.setup-resistance_breakout { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.setup-trend_continuation { background: rgba(107, 114, 128, 0.15); color: #6b7280; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SetupBadge.*
git commit -m "feat: add SetupBadge component for trade types"
```

---

### Task 2: Integrate SetupBadge in StockCard

**Files:**
- Modify: `frontend/src/components/StockCard.jsx`

- [ ] **Step 1: Import and Render**

Modify `frontend/src/components/StockCard.jsx` to destructure `setup` from `stock` and render the `SetupBadge` next to the symbol.

```jsx
// frontend/src/components/StockCard.jsx
import SetupBadge from './SetupBadge';
// ...
const StockCard = ({ stock, isWatched, onToggleWatch }) => {
  const {
    symbol,
    name,
    sector,
    close_price,
    price_change_pct,
    timeframes,
    fundamentals,
    confluence_count,
    setup // Destructure setup
  } = stock;
// ...
// Inside .symbol-row
<span className="stock-symbol">{symbol.replace('.NS', '')}</span>
<SetupBadge setup={setup} />
<span className="sector-tag">{sector}</span>
```

- [ ] **Step 2: Verify visually (Manual)**

Check the Dashboard grid view to ensure the badge appears for stocks with setups.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StockCard.jsx
git commit -m "feat: display setup badge on stock cards"
```

---

### Task 3: Create TradingPlan Component

**Files:**
- Create: `frontend/src/components/TradingPlan.jsx`
- Create: `frontend/src/components/TradingPlan.css`

- [ ] **Step 1: Write the component**

```jsx
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
          <div className="value">₹{setup.entry_zone.low} - ₹{setup.entry_zone.high}</div>
        </div>

        <div className="plan-item stop">
          <label><ShieldAlert size={14} /> Stop Loss</label>
          <div className="value negative">₹{setup.stop_loss}</div>
          <span className="basis">{setup.stop_basis}</span>
        </div>

        <div className="plan-targets">
          <label><Target size={14} /> Targets (R-Multiple)</label>
          <div className="target-list">
            {setup.targets.map((t, i) => (
              <div key={i} className="target-pill">
                <span className="rr">{t.rr}R</span>
                <span className="price">₹{t.level}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="plan-footer">
        <span>Risk per share: ₹{setup.risk_per_share}</span>
        <span>ATR: {setup.atr}</span>
      </div>
    </div>
  );
};

export default TradingPlan;
```

- [ ] **Step 2: Create CSS**

```css
.trading-plan-card {
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 12px;
  padding: 16px;
  margin-top: 16px;
}

.plan-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  text-transform: capitalize;
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
  color: #6b7280;
  margin-bottom: 4px;
}

.plan-item .value {
  font-size: 1.1rem;
  font-weight: 700;
  font-family: monospace;
}

.plan-item .basis {
  font-size: 0.7rem;
  color: #9ca3af;
}

.plan-targets {
  grid-column: span 2;
}

.target-list {
  display: flex;
  gap: 12px;
}

.target-pill {
  display: flex;
  flex-direction: column;
  background: rgba(16, 185, 129, 0.08);
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.target-pill .rr { font-size: 0.7rem; font-weight: 600; color: #10b981; }
.target-pill .price { font-weight: 700; font-family: monospace; }

.plan-footer {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #9ca3af;
  border-top: 1px solid var(--border-color, #f3f4f6);
  padding-top: 12px;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TradingPlan.*
git commit -m "feat: add TradingPlan component"
```

---

### Task 4: Integrate TradingPlan in StockDetail Page

**Files:**
- Modify: `frontend/src/pages/StockDetail.jsx`

- [ ] **Step 1: Import and Render**

```jsx
// frontend/src/pages/StockDetail.jsx
import TradingPlan from '../components/TradingPlan';
// ...
const StockDetail = () => {
  // ...
  const setup = data?.setup; // Capture setup from API response
  // ...
  // Find a good place to render, e.g., above or below ScoreBreakdown
  <div className="detail-sidebar">
    <TradingPlan setup={setup} />
    <ScoreBreakdown breakdown={breakdown} score={dailyScore?.score} />
    {/* ... */}
  </div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/StockDetail.jsx
git commit -m "feat: display trading plan on stock detail page"
```

---

### Task 5: Update Backtest Configuration UI

**Files:**
- Modify: `frontend/src/pages/Backtest.jsx`

- [ ] **Step 1: Update State and Handlers**

Update the `config` state to include new ATR fields.

```jsx
// frontend/src/pages/Backtest.jsx
const [config, setConfig] = useState(() => ({
  // ... existing
  use_atr_stops: false,
  atr_multiplier: 2.0,
  risk_reward_ratio: 2.0,
}));
```

- [ ] **Step 2: Add UI Controls**

Add a new section in the settings panel for ATR-based exits.

```jsx
{/* Inside Settings panel */}
<div className="config-section">
  <h3><ShieldCheck size={16} /> Risk Management</h3>

  <Toggle
    label="Use ATR-based Stops & Targets"
    checked={config.use_atr_stops}
    onChange={(val) => setConfig(prev => ({ ...prev, use_atr_stops: val }))}
  />

  {config.use_atr_stops ? (
    <div className="sub-settings mt-4 space-y-4">
      <Slider
        label="ATR Multiplier (Stop Loss)"
        min={1.0}
        max={5.0}
        step={0.1}
        value={config.atr_multiplier}
        onChange={(val) => setConfig(prev => ({ ...prev, atr_multiplier: val }))}
      />
      <Slider
        label="Risk/Reward Ratio (Targets)"
        min={1.0}
        max={10.0}
        step={0.5}
        value={config.risk_reward_ratio}
        onChange={(val) => setConfig(prev => ({ ...prev, risk_reward_ratio: val }))}
      />
    </div>
  ) : (
    <div className="sub-settings mt-4 space-y-4">
      <Slider
        label="Stop Loss %"
        min={1}
        max={25}
        value={config.stop_loss_pct}
        onChange={(val) => setConfig(prev => ({ ...prev, stop_loss_pct: val }))}
      />
      <Slider
        label="Profit Target %"
        min={0}
        max={100}
        value={config.target_pct}
        onChange={(val) => setConfig(prev => ({ ...prev, target_pct: val }))}
      />
    </div>
  )}
</div>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Backtest.jsx
git commit -m "feat: add ATR configuration to backtest UI"
```

---

### Task 6: Add Setup Column to DataTable

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Update columns**

Modify the columns definition in `Dashboard.jsx` to include a "Setup" column that renders the `SetupBadge`.

```jsx
// frontend/src/pages/Dashboard.jsx
const columns = [
  // ... existing
  {
    header: 'Setup',
    accessor: 'setup',
    render: (setup) => <SetupBadge setup={setup} />
  },
  // ...
];
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Dashboard.jsx
git commit -m "feat: add Setup column to dashboard table"
```
