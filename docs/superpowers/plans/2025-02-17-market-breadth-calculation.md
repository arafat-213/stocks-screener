# Implement On-the-Fly Market Breadth Calculation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement vectorized market breadth calculation in the backtest engine to support "Smart Regime" logic.

**Architecture:** Use pandas vectorization across multiple dataframes to calculate the percentage of stocks above their EMA200 for every date present in the data.

**Tech Stack:** Python, Pandas, Numpy

---

### Task 1: Create failing test for `_calculate_breadth_map`

**Files:**
- Create: `backend/tests/unit/test_backtest_breadth.py`

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd
import datetime
import pytest
from app.backtest.engine import _calculate_breadth_map

def test_calculate_breadth_map():
    dates = pd.date_range("2023-01-01", periods=5)

    # Stock 1: Always above EMA200
    df1 = pd.DataFrame({
        "Close": [110, 115, 120, 125, 130],
        "EMA_200": [100, 100, 100, 100, 100]
    }, index=dates)

    # Stock 2: Below EMA200 then above
    df2 = pd.DataFrame({
        "Close": [90, 95, 105, 110, 115],
        "EMA_200": [100, 100, 100, 100, 100]
    }, index=dates)

    all_dfs = {"SYM1": df1, "SYM2": df2}

    breadth = _calculate_breadth_map(all_dfs)

    # Expected breadth:
    # 2023-01-01: SYM1 (Above), SYM2 (Below) -> 50%
    # 2023-01-02: SYM1 (Above), SYM2 (Below) -> 50%
    # 2023-01-03: SYM1 (Above), SYM2 (Above) -> 100%
    # 2023-01-04: SYM1 (Above), SYM2 (Above) -> 100%
    # 2023-01-05: SYM1 (Above), SYM2 (Above) -> 100%

    assert breadth[datetime.date(2023, 1, 1)] == 50.0
    assert breadth[datetime.date(2023, 1, 2)] == 50.0
    assert breadth[datetime.date(2023, 1, 3)] == 100.0
    assert breadth[datetime.date(2023, 1, 4)] == 100.0
    assert breadth[datetime.date(2023, 1, 5)] == 100.0

def test_calculate_breadth_map_empty():
    assert _calculate_breadth_map({}) == {}

def test_calculate_breadth_map_no_indicators():
    dates = pd.date_range("2023-01-01", periods=5)
    df1 = pd.DataFrame({"Close": [110, 115, 120, 125, 130]}, index=dates)
    assert _calculate_breadth_map({"SYM1": df1}) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_backtest_breadth.py`
Expected: FAIL (AttributeError: module 'app.backtest.engine' has no attribute '_calculate_breadth_map')

### Task 2: Implement `_calculate_breadth_map`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Write minimal implementation**

Add the function to `backend/app/backtest/engine.py`.

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

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_backtest_breadth.py`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/backtest/engine.py backend/tests/unit/test_backtest_breadth.py
git commit -m "feat(engine): implement on-the-fly vectorized market breadth calculation"
```
