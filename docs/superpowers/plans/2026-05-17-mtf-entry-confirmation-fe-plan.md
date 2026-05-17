# Frontend: Multi-Timeframe Entry Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the two new backend config fields (`require_weekly_confirmation`, `require_monthly_confirmation`) in the Backtest UI so users can enable or disable each MTF confirmation gate independently before running a backtest.

**Architecture:** All changes are contained to `Backtest.jsx` and a new test file. Two `Toggle` components are added to the existing "Strategy Filters" section, mirroring the pattern already used by `use_regime_filter` and `require_volume_breakout`. Config state initialisation and the reset handler are updated to include both fields. The recent run summary chip is extended to surface MTF gate status at a glance. A vitest test file validates the initial config values and toggle interaction without a server.

**Tech Stack:** React 19, Vite 8, vitest, @testing-library/react — vitest and RTL are not yet installed and must be added in Task 1.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `frontend/package.json` | Modify | Add `vitest`, `@testing-library/react`, `@testing-library/user-event`, `jsdom` as devDependencies; add `test` script |
| `frontend/vite.config.js` | Modify or create | Add `test` block with jsdom environment so vitest can run React components |
| `frontend/src/pages/Backtest.jsx` | Modify | Initial config state, reset handler, two Toggle controls, run summary chip |
| `frontend/src/pages/__tests__/Backtest.mtf.test.jsx` | Create | Component tests for new toggle controls |

---

## Task 1: Install and Configure vitest + React Testing Library

**Files:**
- Modify: `frontend/package.json`
- Modify or create: `frontend/vite.config.js`

### Context

The project has no test runner. vitest is the correct choice because it shares the same Vite config and supports JSX out of the box with `@vitejs/plugin-react`, which is already installed.

- [ ] **Step 1: Install test dependencies**

```bash
cd frontend
npm install --save-dev vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom
```

Expected: packages added to `node_modules`, `package.json` devDependencies updated.

- [ ] **Step 2: Add a `test` script to `package.json`**

Open `frontend/package.json`. The `scripts` block currently is:

```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "lint": "eslint .",
  "preview": "vite preview"
}
```

Replace it with:

```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "test": "vitest run",
  "test:watch": "vitest"
}
```

- [ ] **Step 3: Add vitest config to `vite.config.js`**

Check whether `frontend/vite.config.js` exists:

```bash
ls frontend/vite.config.js
```

If it exists, open it and add the `test` block. If it does not exist, create it with this full content:

```js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.js'],
  },
});
```

- [ ] **Step 4: Create the test setup file**

```bash
cat > frontend/src/test-setup.js << 'EOF'
import '@testing-library/jest-dom';
EOF
```

- [ ] **Step 5: Verify the test runner starts**

```bash
cd frontend
npm test -- --reporter=verbose 2>&1 | head -20
```

Expected: output contains `No test files found` or similar — no errors about missing config.

- [ ] **Step 6: Commit**

```bash
cd frontend
git add package.json vite.config.js src/test-setup.js
git commit -m "chore(frontend): add vitest + RTL test infrastructure"
```

---

## Task 2: Write Failing Tests for MTF Toggle Controls

**Files:**
- Create: `frontend/src/pages/__tests__/Backtest.mtf.test.jsx`

### Context

The `Backtest` component makes several API calls on mount (`getBacktestRuns`, `getBacktestRun`, `getScreensList`). We must mock all of these so the test renders without a server. The key things to test:

1. `require_weekly_confirmation` toggle is rendered **checked** (default `true`).
2. `require_monthly_confirmation` toggle is rendered **unchecked** (default `false`).
3. Clicking the weekly toggle switches it to unchecked.
4. Clicking the monthly toggle switches it to checked.
5. After clicking Reset, both toggles return to their defaults.

The `Toggle` component from `../components/ui/Toggle` renders a `div.toggle-wrapper` that fires `onClick`. The test clicks the wrapper element to toggle state.

- [ ] **Step 1: Create the test directory**

```bash
mkdir -p frontend/src/pages/__tests__
```

- [ ] **Step 2: Write the test file**

Create `frontend/src/pages/__tests__/Backtest.mtf.test.jsx`:

```jsx
/**
 * Backtest.mtf.test.jsx
 *
 * Tests that the Weekly and Monthly MTF confirmation toggles:
 *   - render with the correct defaults
 *   - respond to user interaction
 *   - reset to defaults when the Reset button is clicked
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import Backtest from '../Backtest';

// ---------------------------------------------------------------------------
// API Mocks — prevent any real HTTP calls
// ---------------------------------------------------------------------------
vi.mock('../../api/client', () => ({
  getBacktestRuns: vi.fn(() => Promise.resolve({ data: [] })),
  getBacktestRun: vi.fn(() => Promise.resolve({ data: null })),
  getScreensList: vi.fn(() => Promise.resolve({ data: [] })),
  getBacktestTrades: vi.fn(() => Promise.resolve({ data: { trades: [], total: 0 } })),
  runBacktest: vi.fn(() => Promise.resolve({ data: { run_id: 'test-run' } })),
}));

// ---------------------------------------------------------------------------
// Helper: render Backtest with Router context
// ---------------------------------------------------------------------------
const renderBacktest = () =>
  render(
    <BrowserRouter>
      <Backtest />
    </BrowserRouter>
  );

// ---------------------------------------------------------------------------
// Helper: find a toggle wrapper by its label text
// ---------------------------------------------------------------------------
const getToggleByLabel = (labelText) => {
  // Toggle renders: <div class="toggle-wrapper"><span class="toggle-label">labelText</span>...
  const label = screen.getByText(labelText);
  return label.closest('.toggle-wrapper');
};

// ---------------------------------------------------------------------------
// Helper: check if a toggle is currently "on"
// ---------------------------------------------------------------------------
const isToggleChecked = (wrapper) =>
  wrapper.querySelector('.toggle-switch')?.classList.contains('checked') ?? false;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Backtest MTF Confirmation Toggles', () => {
  it('renders Weekly Confirmation toggle in the ON state by default', async () => {
    renderBacktest();
    await waitFor(() => {
      expect(screen.getByText('Weekly Confirmation')).toBeInTheDocument();
    });
    const toggle = getToggleByLabel('Weekly Confirmation');
    expect(isToggleChecked(toggle)).toBe(true);
  });

  it('renders Monthly Confirmation toggle in the OFF state by default', async () => {
    renderBacktest();
    await waitFor(() => {
      expect(screen.getByText('Monthly Confirmation')).toBeInTheDocument();
    });
    const toggle = getToggleByLabel('Monthly Confirmation');
    expect(isToggleChecked(toggle)).toBe(false);
  });

  it('turns Weekly Confirmation OFF when clicked', async () => {
    const user = userEvent.setup();
    renderBacktest();
    await waitFor(() => screen.getByText('Weekly Confirmation'));

    const toggle = getToggleByLabel('Weekly Confirmation');
    expect(isToggleChecked(toggle)).toBe(true);

    await user.click(toggle);
    expect(isToggleChecked(toggle)).toBe(false);
  });

  it('turns Monthly Confirmation ON when clicked', async () => {
    const user = userEvent.setup();
    renderBacktest();
    await waitFor(() => screen.getByText('Monthly Confirmation'));

    const toggle = getToggleByLabel('Monthly Confirmation');
    expect(isToggleChecked(toggle)).toBe(false);

    await user.click(toggle);
    expect(isToggleChecked(toggle)).toBe(true);
  });

  it('resets both toggles to their defaults when Reset is clicked', async () => {
    const user = userEvent.setup();
    renderBacktest();
    await waitFor(() => screen.getByText('Weekly Confirmation'));

    // Invert both
    await user.click(getToggleByLabel('Weekly Confirmation'));   // OFF
    await user.click(getToggleByLabel('Monthly Confirmation'));  // ON

    expect(isToggleChecked(getToggleByLabel('Weekly Confirmation'))).toBe(false);
    expect(isToggleChecked(getToggleByLabel('Monthly Confirmation'))).toBe(true);

    // Click the reset button (title="Reset to defaults")
    const resetBtn = screen.getByTitle('Reset to defaults');
    await user.click(resetBtn);

    expect(isToggleChecked(getToggleByLabel('Weekly Confirmation'))).toBe(true);
    expect(isToggleChecked(getToggleByLabel('Monthly Confirmation'))).toBe(false);
  });
});
```

- [ ] **Step 3: Run the tests — verify they fail**

```bash
cd frontend
npm test -- --reporter=verbose 2>&1 | tail -20
```

Expected output contains failures like:
```
FAIL src/pages/__tests__/Backtest.mtf.test.jsx
  × renders Weekly Confirmation toggle in the ON state by default
    Unable to find an element with the text: Weekly Confirmation
```

- [ ] **Step 4: Commit the failing tests**

```bash
cd frontend
git add src/pages/__tests__/Backtest.mtf.test.jsx
git commit -m "test(backtest): add failing tests for MTF confirmation toggles"
```

---

## Task 3: Update Config State and Reset Handler

**Files:**
- Modify: `frontend/src/pages/Backtest.jsx`

### Context

The `config` state is initialised with `useState(() => ({ ... }))` inside the `Backtest` component. `handleResetConfig` sets the same object. Both must gain two new keys.

The relevant API call is `runBacktest(config)` in `handleRunBacktest` — it already sends the entire `config` object, so no changes are needed there.

- [ ] **Step 1: Add the two fields to the initial state**

In `frontend/src/pages/Backtest.jsx`, find the `useState` call that initialises `config`. It currently starts with:

```js
const [config, setConfig] = useState(() => ({
  screen_slug: 'all',
  score_threshold: 60,
  holding_days: 20,
  stop_loss_pct: 7.0,
  target_pct: 20.0,
  trailing_stop_pct: 0.0,
  use_atr_stops: false,
  atr_multiplier: 2.0,
  risk_reward_ratio: 2.5,
  use_regime_filter: true,
  require_volume_breakout: false,
  starting_capital: 1000000,
  position_size:    10000,
  include_fundamentals: false,
  symbol_limit: 100,
  date_from: new Date(new Date().setFullYear(new Date().getFullYear() - 1))
    .toISOString()
    .split('T')[0],
  date_to: new Date().toISOString().split('T')[0],
}));
```

Replace it with:

```js
const [config, setConfig] = useState(() => ({
  screen_slug: 'all',
  score_threshold: 60,
  holding_days: 20,
  stop_loss_pct: 7.0,
  target_pct: 20.0,
  trailing_stop_pct: 0.0,
  use_atr_stops: false,
  atr_multiplier: 2.0,
  risk_reward_ratio: 2.5,
  use_regime_filter: true,
  require_volume_breakout: false,
  require_weekly_confirmation: true,   // MTF-001 — default ON (eliminates counter-trend entries)
  require_monthly_confirmation: false, // MTF-002 — default OFF (opt-in for longer backtests)
  starting_capital: 1000000,
  position_size:    10000,
  include_fundamentals: false,
  symbol_limit: 100,
  date_from: new Date(new Date().setFullYear(new Date().getFullYear() - 1))
    .toISOString()
    .split('T')[0],
  date_to: new Date().toISOString().split('T')[0],
}));
```

- [ ] **Step 2: Add the two fields to `handleResetConfig`**

Find the `handleResetConfig` callback. It currently sets:

```js
const handleResetConfig = useCallback(() => {
  setConfig({
    screen_slug: 'all',
    score_threshold: 60,
    holding_days: 20,
    stop_loss_pct: 7.0,
    target_pct: 20.0,
    trailing_stop_pct: 0.0,
    use_atr_stops: false,
    atr_multiplier: 2.0,
    risk_reward_ratio: 2.5,
    use_regime_filter: true,
    require_volume_breakout: false,
    include_fundamentals: false,
    symbol_limit: 100,
    date_from: new Date(new Date().setFullYear(new Date().getFullYear() - 1))
      .toISOString()
      .split('T')[0],
    date_to: new Date().toISOString().split('T')[0],
    starting_capital: 1000000,
    position_size: 10000,
  });
}, []);
```

Replace it with:

```js
const handleResetConfig = useCallback(() => {
  setConfig({
    screen_slug: 'all',
    score_threshold: 60,
    holding_days: 20,
    stop_loss_pct: 7.0,
    target_pct: 20.0,
    trailing_stop_pct: 0.0,
    use_atr_stops: false,
    atr_multiplier: 2.0,
    risk_reward_ratio: 2.5,
    use_regime_filter: true,
    require_volume_breakout: false,
    require_weekly_confirmation: true,   // MTF-001 — matches initial state
    require_monthly_confirmation: false, // MTF-002 — matches initial state
    include_fundamentals: false,
    symbol_limit: 100,
    date_from: new Date(new Date().setFullYear(new Date().getFullYear() - 1))
      .toISOString()
      .split('T')[0],
    date_to: new Date().toISOString().split('T')[0],
    starting_capital: 1000000,
    position_size: 10000,
  });
}, []);
```

- [ ] **Step 3: Run the tests — still failing (no UI yet)**

```bash
cd frontend
npm test -- --reporter=verbose 2>&1 | tail -10
```

Expected: tests still fail with `Unable to find an element with the text: Weekly Confirmation` — that's correct, we haven't added the UI elements yet.

- [ ] **Step 4: Commit**

```bash
cd frontend
git add src/pages/Backtest.jsx
git commit -m "feat(backtest): add require_weekly_confirmation and require_monthly_confirmation to config state and reset"
```

---

## Task 4: Add Toggle Controls to Strategy Filters Section

**Files:**
- Modify: `frontend/src/pages/Backtest.jsx`

### Context

The existing "Strategy Filters" section renders a `div.strategy-rules-list` containing three `Toggle` components. The two new toggles go at the bottom of that list, after the existing ones. The `Toggle` component accepts `label`, `checked`, `onChange`, and `icon` props. We will use the `TrendingUp` icon (imported) for Weekly and `BarChart3` for Monthly, both already imported in the file.

Looking at the existing imports in `Backtest.jsx`:
- `TrendingUp` ✓ already imported
- `BarChart3` ✓ already imported

No new imports are needed.

- [ ] **Step 1: Locate the Strategy Filters section**

Find this block in `Backtest.jsx`:

```jsx
<div className="strategy-rules-section">
  <h3 className="section-subtitle">Strategy Filters</h3>
  <div className="strategy-rules-list">
    <Toggle
      label="Market Regime"
      checked={config.use_regime_filter}
      onChange={(val) =>
        handleConfigChange('use_regime_filter', val)
      }
      icon={ShieldCheck}
    />
    <Toggle
      label="Volume Breakout"
      checked={config.require_volume_breakout}
      onChange={(val) =>
        handleConfigChange('require_volume_breakout', val)
      }
      icon={Zap}
    />
    <Toggle
      label="Fundamentals"
      checked={config.include_fundamentals}
      onChange={(val) =>
        handleConfigChange('include_fundamentals', val)
      }
      icon={Briefcase}
    />
  </div>
</div>
```

- [ ] **Step 2: Add the two new toggles**

Replace the block found in Step 1 with:

```jsx
<div className="strategy-rules-section">
  <h3 className="section-subtitle">Strategy Filters</h3>
  <div className="strategy-rules-list">
    <Toggle
      label="Market Regime"
      checked={config.use_regime_filter}
      onChange={(val) =>
        handleConfigChange('use_regime_filter', val)
      }
      icon={ShieldCheck}
    />
    <Toggle
      label="Volume Breakout"
      checked={config.require_volume_breakout}
      onChange={(val) =>
        handleConfigChange('require_volume_breakout', val)
      }
      icon={Zap}
    />
    <Toggle
      label="Fundamentals"
      checked={config.include_fundamentals}
      onChange={(val) =>
        handleConfigChange('include_fundamentals', val)
      }
      icon={Briefcase}
    />
    <Toggle
      label="Weekly Confirmation"
      checked={config.require_weekly_confirmation}
      onChange={(val) =>
        handleConfigChange('require_weekly_confirmation', val)
      }
      icon={TrendingUp}
    />
    <Toggle
      label="Monthly Confirmation"
      checked={config.require_monthly_confirmation}
      onChange={(val) =>
        handleConfigChange('require_monthly_confirmation', val)
      }
      icon={BarChart3}
    />
  </div>
</div>
```

- [ ] **Step 3: Run the tests — they should now pass**

```bash
cd frontend
npm test -- --reporter=verbose 2>&1 | tail -20
```

Expected output:

```
✓ src/pages/__tests__/Backtest.mtf.test.jsx (5)
  ✓ Backtest MTF Confirmation Toggles > renders Weekly Confirmation toggle in the ON state by default
  ✓ Backtest MTF Confirmation Toggles > renders Monthly Confirmation toggle in the OFF state by default
  ✓ Backtest MTF Confirmation Toggles > turns Weekly Confirmation OFF when clicked
  ✓ Backtest MTF Confirmation Toggles > turns Monthly Confirmation ON when clicked
  ✓ Backtest MTF Confirmation Toggles > resets both toggles to their defaults when Reset is clicked

Test Files  1 passed (1)
Tests       5 passed (5)
```

If a test fails with `Cannot find module '../../api/client'`, double-check the relative path: the test is at `src/pages/__tests__/Backtest.mtf.test.jsx` and the mock path `'../../api/client'` resolves to `src/api/client`. Adjust the path one level up if needed (`'../../../api/client'`).

- [ ] **Step 4: Commit**

```bash
cd frontend
git add src/pages/Backtest.jsx
git commit -m "feat(backtest): add Weekly/Monthly confirmation toggles to Strategy Filters UI"
```

---

## Task 5: Update Recent Run Summary Chip

**Files:**
- Modify: `frontend/src/pages/Backtest.jsx`

### Context

The recent run list renders a summary chip per run:

```jsx
<div className="run-config-summary">
  T:{run.config.score_threshold} | H:{run.config.holding_days} | SL:{run.config.stop_loss_pct}%
</div>
```

This hardcodes three fields. We add a small MTF indicator so users can see at a glance whether a historical run used the weekly or monthly gate. The format: `W:✓` (gate on) or `W:✗` (gate off), same for `M`.

- [ ] **Step 1: Find the run config summary line**

Locate this exact JSX in `Backtest.jsx`:

```jsx
<div className="run-config-summary">
  T:{run.config.score_threshold} | H:{run.config.holding_days}{' '}
  | SL:{run.config.stop_loss_pct}%
</div>
```

- [ ] **Step 2: Replace with the extended version**

```jsx
<div className="run-config-summary">
  T:{run.config.score_threshold} | H:{run.config.holding_days}{' '}
  | SL:{run.config.stop_loss_pct}%{' '}
  | W:{run.config.require_weekly_confirmation !== false ? '✓' : '✗'}{' '}
  | M:{run.config.require_monthly_confirmation ? '✓' : '✗'}
</div>
```

Note the `!== false` check for weekly: older runs saved before this feature was deployed will have `undefined` for this key, and the backend default is `true`, so we treat `undefined` as `true`.

- [ ] **Step 3: Run the full test suite**

```bash
cd frontend
npm test -- --reporter=verbose
```

Expected: all 5 tests still pass. No regressions.

- [ ] **Step 4: Commit**

```bash
cd frontend
git add src/pages/Backtest.jsx
git commit -m "feat(backtest): show MTF gate status in recent run summary chip"
```

---

## Task 6: Manual Smoke Test

**Files:** None — manual verification only.

### Steps

- [ ] **Step 1: Start the dev server**

```bash
cd frontend
npm run dev
```

Navigate to `http://localhost:5173/backtest` in the browser.

- [ ] **Step 2: Verify toggle defaults**

In the "Strategy Filters" section, confirm:
- **Weekly Confirmation** toggle is ON (blue/active) — matches `require_weekly_confirmation: true`
- **Monthly Confirmation** toggle is OFF (grey) — matches `require_monthly_confirmation: false`

- [ ] **Step 3: Verify toggle interaction**

Click "Monthly Confirmation" — it should switch to ON.
Click "Weekly Confirmation" — it should switch to OFF.

- [ ] **Step 4: Verify Reset**

Click the ↺ reset button in the config header. Both toggles should return to their defaults (Weekly ON, Monthly OFF).

- [ ] **Step 5: Verify API payload contains the new fields**

Open browser DevTools → Network tab. Click "Run Backtest". Find the POST to `/api/backtest/run`. In the request payload, confirm:

```json
{
  "require_weekly_confirmation": true,
  "require_monthly_confirmation": false,
  ...
}
```

If either field is missing from the payload, confirm the initial state was saved correctly (Task 3).

- [ ] **Step 6: Verify Recent Runs display**

After the backtest completes, check the Recent Runs list. The summary chip should show `W:✓ | M:✗` for a default-config run.

- [ ] **Step 7: Final commit**

```bash
cd frontend
git add .
git commit -m "feat(backtest): frontend MTF entry confirmation complete"
```

---

## Self-Review

### Spec Coverage

| Spec ID | Requirement | Covered by |
|---|---|---|
| MTF-004 | `require_weekly_confirmation` exposed in API with default `True` | Task 3 initial state (`true`), Task 5 run summary (`!== false` for back-compat) |
| MTF-004 | `require_monthly_confirmation` exposed in API with default `False` | Task 3 initial state (`false`) |
| MTF-004 | Field descriptions state default and impact | Toggle labels + spec's field descriptions; no tooltip added (out of scope per spec) |
| MTF-004 | Both fields appear in the serialised `config` JSON | Task 3 — `runBacktest(config)` already sends full config object; both fields are now in state |
| MTF-004 | Historical runs can be inspected and reproduced | Task 5 — run summary chip reads from `run.config.*` which is the stored JSON |

### Placeholder Scan

None found. Every step contains the complete replacement code block.

### Type Consistency

- `require_weekly_confirmation` key is spelled identically in: initial state (Task 3 Step 1), reset handler (Task 3 Step 2), Toggle `onChange` (Task 4 Step 2), run summary (Task 5 Step 2), and test file mock assertion (Task 2 Step 2). ✓
- `require_monthly_confirmation` key is spelled identically in all five places. ✓
- `getToggleByLabel('Weekly Confirmation')` in tests matches the `label="Weekly Confirmation"` prop in the Toggle (Task 4 Step 2). ✓
- `getToggleByLabel('Monthly Confirmation')` matches `label="Monthly Confirmation"`. ✓
- `isToggleChecked` reads `.toggle-switch` → `.checked` class, which matches the Toggle component's rendering: `<div className={`toggle-switch ${checked ? 'checked' : ''}`}>`. ✓