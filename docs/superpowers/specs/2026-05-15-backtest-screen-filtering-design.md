# Backtest Screen Filtering Design

**Goal:** Allow users to restrict the backtest universe to stocks that pass a specific fundamental or technical screen.

**Architecture:**
1.  **Frontend:** Update the Backtest configuration sidebar to include a "Starting Universe" dropdown.
2.  **API:** Update `BacktestRequest` and `BacktestConfig` to accept an optional `screen_slug`.
3.  **Engine:** Modify `run_backtest` to fetch symbols from the selected screen instead of the default "all symbols" query when a `screen_slug` is provided.

## Backend Changes

### 1. API Models (`backend/app/routers/backtest.py` and `backend/app/backtest/engine.py`)
-   Add `screen_slug: Optional[str] = None` to `BacktestRequest` (Pydantic).
-   Add `screen_slug: Optional[str] = None` to `BacktestConfig` (Dataclass).

### 2. Backtest Engine (`backend/app/backtest/engine.py`)
Modify the symbol selection logic in `run_backtest`:
```python
if config.screen_slug and config.screen_slug != "all":
    from app.screens.registry import SCREEN_REGISTRY
    if config.screen_slug not in SCREEN_REGISTRY:
        raise ValueError(f"Invalid screen slug: {config.screen_slug}")

    screen_fn = SCREEN_REGISTRY[config.screen_slug]['fn']
    # Execute screen function (returns list of (symbol, score) tuples)
    screen_results = screen_fn(db)
    symbols = [r[0] for r in screen_results]
else:
    # Default: All symbols from signals
    symbol_query = (
        db.query(TechnicalSignal.symbol)
        .group_by(TechnicalSignal.symbol)
        .order_by(func.max(TechnicalSignal.date).desc())
        .all()
    )
    symbols = [row[0] for row in symbol_query]
```

### 3. Router logic (`backend/app/routers/backtest.py`)
Update `start_backtest` to pass the `screen_slug` from the request to the engine config.

## Frontend Changes

### 1. State Management (`frontend/src/pages/Backtest.jsx`)
-   Update default `config` state to include `screen_slug: 'all'`.
-   Fetch the list of available screens using `getScreensList` (already exists in `client.js`).

### 2. UI Components (`frontend/src/pages/Backtest.jsx`)
-   Add a "Starting Universe" section at the top of the sidebar.
-   Include a dropdown (`<select>` or custom component) with:
    -   `All Symbols` (value: 'all')
    -   Options mapped from `getScreensList` response.

## Error Handling
-   If the selected screen returns no symbols, the backtest should record a failure with the message: "Selected screen returned no symbols for backtesting."

## Testing Strategy
-   **Backend Unit Test:** Mock `SCREEN_REGISTRY` in a new test case within `test_backtest_engine.py` to verify symbol filtering.
-   **API Test:** Verify `screen_slug` is correctly accepted in `test_backtest.py`.
-   **Frontend:** Manual verification that the dropdown updates state and the correct payload is sent to `/api/backtest/run`.
