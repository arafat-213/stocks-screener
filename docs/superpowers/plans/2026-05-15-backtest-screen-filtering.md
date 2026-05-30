# Backtest Screen Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to filter the backtest universe using existing screens from the `SCREEN_REGISTRY`.

**Architecture:**
- Update `BacktestConfig` and `BacktestRequest` to include `screen_slug`.
- Modify `run_backtest` in the engine to use the screen function if a slug is provided.
- Update the React frontend to fetch screens and show a dropdown in the configuration sidebar.

**Tech Stack:** Python (FastAPI, SQLAlchemy), React (Vite).

---

### Task 1: Update Backend Models

**Files:**
- Modify: `backend/app/backtest/engine.py`
- Modify: `backend/app/routers/backtest.py`

- [ ] **Step 1: Update BacktestConfig dataclass**
  Add `screen_slug: Optional[str] = None` to the dataclass in `backend/app/backtest/engine.py`.

```python
# backend/app/backtest/engine.py

@dataclass
class BacktestConfig:
    # ... existing fields
    screen_slug: Optional[str] = None  # New field
    starting_capital: float = 1000000.0
    position_size: float = 10000.0
```

- [ ] **Step 2: Update BacktestRequest Pydantic model**
  Add `screen_slug: Optional[str] = None` to the model in `backend/app/routers/backtest.py`.

```python
# backend/app/routers/backtest.py

class BacktestRequest(BaseModel):
    # ... existing fields
    screen_slug: Optional[str] = Field(default=None, description="Slug of the screen to filter symbols by.")
    starting_capital: float = Field(default=1000000.0, ge=10000)
    position_size: float = Field(default=10000.0, ge=100)
```

- [ ] **Step 3: Update router to pass screen_slug**
  Pass `request.screen_slug` to the `BacktestConfig` in the `start_backtest` route.

```python
# backend/app/routers/backtest.py

@router.post("/run")
def start_backtest(...):
    # ...
    config = BacktestConfig(
        # ... existing fields
        screen_slug=request.screen_slug,
        starting_capital=request.starting_capital,
        position_size=request.position_size
    )
    # ...
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/backtest/engine.py backend/app/routers/backtest.py
git commit -m "feat: add screen_slug to backtest models"
```

---

### Task 2: Implement Engine Filtering Logic

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Update symbol selection logic**
  Modify `run_backtest` to handle `screen_slug`.

```python
# backend/app/backtest/engine.py:380 (approx)

def run_backtest(db: Session, run_id: str, config: BacktestConfig):
    # ...
    try:
        # ... Fetch benchmark

        # 2. Select symbols
        if config.screen_slug and config.screen_slug != "all":
            from app.screens.registry import SCREEN_REGISTRY
            if config.screen_slug not in SCREEN_REGISTRY:
                raise ValueError(f"Invalid screen slug: {config.screen_slug}")

            logger.info(f"Filtering symbols using screen: {config.screen_slug}")
            screen_fn = SCREEN_REGISTRY[config.screen_slug]['fn']
            screen_results = screen_fn(db)
            symbols = [r[0] for r in screen_results]

            if not symbols:
                 raise ValueError(f"Selected screen '{config.screen_slug}' returned no symbols for backtesting.")
        else:
            symbol_query = (
                db.query(TechnicalSignal.symbol)
                .group_by(TechnicalSignal.symbol)
                .order_by(func.max(TechnicalSignal.date).desc())
                .all()
            )
            symbols = [row[0] for row in symbol_query]

        if config.symbol_limit:
            symbols = symbols[:config.symbol_limit]

        run.symbols_total = len(symbols)
        # ...
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat: implement screen filtering in backtest engine"
```

---

### Task 3: Backend Unit Testing

**Files:**
- Create: `backend/tests/unit/test_backtest_screen_filter.py`

- [ ] **Step 1: Write test for screen filtering**
  Verify that when a screen slug is provided, the engine calls the screen function and processes only those symbols.

```python
import pytest
from unittest.mock import MagicMock, patch
from app.backtest.engine import run_backtest, BacktestConfig
from app.db.models import BacktestRun

def test_run_backtest_with_screen_filter(db_session):
    # Setup
    run_id = "test-screen-filter"
    run = BacktestRun(run_id=run_id, status="pending", config="{}")
    db_session.add(run)
    db_session.commit()

    config = BacktestConfig(
        screen_slug="52w-high",
        symbol_limit=10
    )

    # Mock screen function returning only 2 symbols
    mock_screen_fn = MagicMock(return_value=[("RELIANCE.NS", 80), ("TCS.NS", 75)])

    with patch("app.screens.registry.SCREEN_REGISTRY", {
        "52w-high": {"fn": mock_screen_fn}
    }):
        with patch("app.backtest.engine.fetch_stock_data", return_value=(MagicMock(), {})):
             with patch("app.backtest.engine.score_series", return_value=[]):
                  run_backtest(db_session, run_id, config)

    # Verify
    updated_run = db_session.query(BacktestRun).filter_by(run_id=run_id).first()
    assert updated_run.symbols_total == 2
    mock_screen_fn.assert_called_once()
```

- [ ] **Step 2: Run tests**

Run: `pytest backend/tests/unit/test_backtest_screen_filter.py`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_backtest_screen_filter.py
git commit -m "test: add unit test for backtest screen filtering"
```

---

### Task 4: Frontend UI Updates

**Files:**
- Modify: `frontend/src/pages/Backtest.jsx`

- [ ] **Step 1: Update initial state and imports**
  Add `getScreensList` to imports and update `config` initial state.

```javascript
// frontend/src/pages/Backtest.jsx

import {
  runBacktest,
  getBacktestRun,
  getBacktestRuns,
  getBacktestTrades,
  getScreensList // Add this
} from '../api/client';

// ... inside Backtest component
  const [config, setConfig] = useState(() => ({
    screen_slug: 'all', // New field
    score_threshold: 60,
    // ...
```

- [ ] **Step 2: Fetch screens for the dropdown**
  Use `useFetch` to get the list of screens.

```javascript
// frontend/src/pages/Backtest.jsx

  // Fetch Available Screens
  const { data: screens } = useFetch(getScreensList);
```

- [ ] **Step 3: Render the Universe selection dropdown**
  Add the dropdown at the top of the sidebar.

```javascript
// frontend/src/pages/Backtest.jsx

// Inside section className="config-card"
<div className="config-form">
  <div className="form-group">
    <label className="form-label flex items-center gap-2">
      <Layers size={13} /> Starting Universe
    </label>
    <select
      className="input-styled w-full"
      value={config.screen_slug}
      onChange={(e) => handleConfigChange('screen_slug', e.target.value)}
    >
      <option value="all">All Symbols (Default)</option>
      {screens?.map(screen => (
        <option key={screen.slug} value={screen.slug}>
          {screen.label}
        </option>
      ))}
    </select>
  </div>
  {/* ... existing fields */}
```

- [ ] **Step 4: Update handleResetConfig**
  Include `screen_slug: 'all'` in the reset logic.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Backtest.jsx
git commit -m "feat: add universe selection dropdown to backtest UI"
```

---

### Task 5: End-to-End Verification

- [ ] **Step 1: Verify API payload**
  Run the frontend, open DevTools, start a backtest with a screen selected, and verify the POST request payload contains `screen_slug`.

- [ ] **Step 2: Verify backend logs**
  Check backend logs to see if it says "Filtering symbols using screen: ...".

- [ ] **Step 3: Final Commit**

```bash
git commit --allow-empty -m "chore: complete backtest screen filtering feature"
```
