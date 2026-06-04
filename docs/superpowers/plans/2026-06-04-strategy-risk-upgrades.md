# Strategy Risk Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a "Smart Regime" engine that uses Market Breadth (participation) to filter trades and dynamically adjust position sizing, while enforcing sector concentration.

**Architecture:**
1. Enhance `UnifiedTradingConfig` with new parameters for breadth and ADX floor.
2. Implement an optimized **in-memory** Breadth Map generator using Parquet data (bypassing the database).
3. Inject Breadth logic into the Regime Map builder and Portfolio Simulator.
4. Set new production-safe defaults for sector limits.

**Tech Stack:** Python, Pandas, Pandas-TA.

---

### Task 1: Update Trading Configuration Schema

**Files:**
- Modify: `backend/app/core/trading_config.py`

- [ ] **Step 1: Add new risk parameters and update sector default**
Update `UnifiedTradingConfig` class with `regime_adx_floor`, `min_market_breadth_pct`, and change `max_sector_positions`.

```python
@dataclass
class UnifiedTradingConfig:
    # ... existing fields
    max_sector_positions: int = 3 # Changed from 0
    # ...
    regime_adx_floor: float = 15.0 # New
    min_market_breadth_pct: float = 40.0 # New
```

- [ ] **Step 2: Verify type consistency**
Ensure all new fields have default values and proper types.

- [ ] **Step 3: Commit**
```bash
git add backend/app/core/trading_config.py
git commit -m "feat(config): add breadth and adx floor parameters, set sector limit default to 3"
```

---

### Task 2: Implement On-the-Fly Market Breadth Calculation

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Implement `_calculate_breadth_map`**
Add the helper function to `engine.py` to calculate breadth using pandas vectorization on the loaded dataframes.

```python
def _calculate_breadth_map(all_dfs: dict[str, pd.DataFrame]) -> dict[datetime.date, float]:
    """
    Calculates the percentage of stocks above their 200 EMA per day
    using the already loaded Parquet dataframes.
    """
    if not all_dfs:
        return {}

    # Extract Close and EMA200 for all symbols into dictionaries of series
    close_series = {}
    ema_series = {}

    for sym, df in all_dfs.items():
        if "Close" in df.columns and "EMA_200" in df.columns:
            # Drop timezone information for consistency if present
            idx = df.index
            if hasattr(idx, "tz") and idx.tz is not None:
                idx = idx.tz_localize(None)

            close_series[sym] = pd.Series(df["Close"].values, index=idx)
            ema_series[sym] = pd.Series(df["EMA_200"].values, index=idx)

    if not close_series:
        return {}

    # Create DataFrames
    close_df = pd.DataFrame(close_series)
    ema_df = pd.DataFrame(ema_series)

    # Boolean matrix: True if Close > EMA200
    above_mask = close_df > ema_df

    # Sum True values per row and divide by number of active stocks that day
    active_stocks = close_df.notna().sum(axis=1)

    # Avoid division by zero
    breadth_series = pd.Series(0.0, index=close_df.index)
    valid_mask = active_stocks > 0
    breadth_series[valid_mask] = (above_mask[valid_mask].sum(axis=1) / active_stocks[valid_mask]) * 100

    # Convert to dict with date keys
    return {d.date() if hasattr(d, "date") else d: float(v) for d, v in breadth_series.items()}
```

- [ ] **Step 2: Commit**
```bash
git commit -m "feat(engine): implement on-the-fly vectorized market breadth calculation"
```

---

### Task 3: Upgrade Regime Map with Smart Overrides

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Update `_build_regime_map` signature and logic**
Inject `breadth_map` and apply the new prioritization logic.

```python
def _build_regime_map(
    bench_df: pd.DataFrame,
    config: BacktestConfig,
    breadth_map: dict = None
) -> dict[datetime.date, float]:
    # ...
    for i in range(len(bench_df)):
        # ...
        breadth = (breadth_map or {}).get(date, 50.0) # Default to 50% if unknown

        # SMART OVERRIDES
        if adx < config.regime_adx_floor:
            if breadth > 60.0:
                potential_regime = 2 # Hidden Bull
            elif breadth < config.min_market_breadth_pct:
                potential_regime = 0 # Dangerous Sideways
            else:
                potential_regime = 1 # Normal Neutral
        elif close < ema200 or rsi < config.regime_bear_rsi_threshold:
            potential_regime = 0 # BEAR
        elif rsi > config.regime_bull_rsi_threshold and adx > config.regime_adx_threshold:
            potential_regime = 2 # BULL
        else:
            potential_regime = 1 # NEUTRAL
        # ...
```

- [ ] **Step 2: Commit**
```bash
git commit -m "feat(engine): upgrade regime map with breadth-aware overrides"
```

---

### Task 4: Integrate Breadth Logic into Backtest Flow

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Update `run_backtest` to generate and pass breadth map**
Call `_calculate_breadth_map` *after* the `all_dfs` dictionary is fully populated (after the cache block). Include it in the `_SIGNAL_RUN_CACHE` payload.

- [ ] **Step 2: Update `simulate_portfolio` and `simulate_trades` signatures**
Ensure the `breadth_map` is passed down to the entry gate.

- [ ] **Step 3: Update entry gate in `simulate_trades`**
Add the breadth participation check inside the signal iteration loop.

```python
# Inside simulate_trades loop, right before entry logic
current_breadth = (breadth_map or {}).get(wait_compare, 100.0) # Default allow if missing
if current_breadth < config.min_market_breadth_pct:
    continue # Skip entry due to poor market breadth
```

- [ ] **Step 4: Commit**
```bash
git commit -m "feat(engine): integrate breadth map into portfolio simulation"
```

---

### Task 5: Final Validation & Clean-up

**Files:**
- Test: `backend/tests/test_engine.py`

- [ ] **Step 1: Run comprehensive backtest regression suite**
Run: `pytest backend/tests/test_engine.py -v`
Verify no regressions in existing logic.

- [ ] **Step 2: Final code audit**
Remove any dead code or TBD comments. Ensure type hints are accurate.

- [ ] **Step 3: Commit**
```bash
git commit -m "test: verify strategy risk upgrades with integration tests"
```
