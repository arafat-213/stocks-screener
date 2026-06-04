# Breadth-Aware Smart Regime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the backtest engine's regime classification to use "Universe Breadth" for smarter classification in low-trend environments.

**Architecture:** Update `_build_regime_map` to accept a `breadth_map` and apply prioritized overrides when benchmark ADX is low. Integrate this into the main `run_backtest` loop.

**Tech Stack:** Python, Pandas, SQLAlchemy.

---

### Task 1: Update `_build_regime_map` Logic

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Modify `_build_regime_map` signature and inject breadth overrides**

```python
def _build_regime_map(
    bench_df: pd.DataFrame,
    config: BacktestConfig,
    breadth_map: dict = None
) -> dict[datetime.date, float]:
    """
    Pre-calculates a mapping from date to position scaling (max_position_pct).
    Uses RSI, ADX, Price vs EMA200, and Universe Breadth.
    """
    if bench_df is None or bench_df.empty:
        return {}

    # Ensure required indicators are present
    if "RSI_14" not in bench_df.columns:
        return {}
    if "ADX_14" not in bench_df.columns:
        bench_df.ta.adx(length=14, append=True)
    if "EMA_200" not in bench_df.columns:
        bench_df.ta.ema(length=200, append=True)

    regime_map = {}
    current_regime = 1  # Start Neutral
    confirmation_counter = 0
    target_days = config.regime_confirmation_days

    for i in range(len(bench_df)):
        row = bench_df.iloc[i]
        date = bench_df.index[i].date()

        rsi = row.get("RSI_14", 50.0)
        adx = row.get("ADX_14", 0.0)
        close = row.get("Close", 0.0)
        ema200 = row.get("EMA_200", 0.0)

        breadth = (breadth_map or {}).get(date, 50.0)

        # Determine "Potential" Regime with SMART OVERRIDES
        if adx < config.regime_adx_floor:
            if breadth > 60.0:
                potential_regime = 2  # Hidden Bull
            elif breadth < config.min_market_breadth_pct:
                potential_regime = 0  # Dangerous Sideways
            else:
                potential_regime = 1  # Normal Neutral
        elif close < ema200 or rsi < config.regime_bear_rsi_threshold:
            potential_regime = 0  # BEAR
        elif rsi > config.regime_bull_rsi_threshold and adx > config.regime_adx_threshold:
            potential_regime = 2  # BULL
        else:
            potential_regime = 1  # NEUTRAL

        # Apply Hysteresis/Debounce
        if potential_regime == current_regime:
            confirmation_counter = 0
        else:
            confirmation_counter += 1
            if confirmation_counter >= target_days:
                current_regime = potential_regime
                confirmation_counter = 0

        # Map state to position percentage
        if current_regime == 0:
            val = config.regime_bear_position_pct
        elif current_regime == 2:
            val = config.regime_bull_position_pct
        else:
            val = config.regime_neutral_position_pct

        regime_map[date] = val

    return regime_map
```

### Task 2: Integrate into `run_backtest`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Call breadth calculation and pass to regime builder**

```python
        regime_scaling_map = {}
        if config.use_regime_position_scaling and bench_df is not None:
            # Calculate breadth based on processed stock data
            breadth_map = _calculate_breadth_map(all_dfs)
            regime_scaling_map = _build_regime_map(bench_df, config, breadth_map=breadth_map)
```

- [ ] **Step 2: Commit changes**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat(engine): upgrade regime map with breadth-aware smart overrides"
```

### Task 3: Verification with Unit Test

**Files:**
- Create: `backend/tests/backtest/test_breadth_regime.py`

- [ ] **Step 1: Write verification test**

```python
import pytest
import pandas as pd
import datetime
from app.backtest.engine import _build_regime_map
from app.core.trading_config import UnifiedTradingConfig

def test_regime_map_breadth_overrides():
    # Mock benchmark data: Low ADX (10), RSI Neutral (50), Price > EMA200
    dates = pd.date_range("2023-01-01", periods=10)
    bench_df = pd.DataFrame({
        "Close": [100.0] * 10,
        "RSI_14": [50.0] * 10,
        "ADX_14": [10.0] * 10,
        "EMA_200": [90.0] * 10
    }, index=dates)

    config = UnifiedTradingConfig(
        regime_adx_floor=15.0,
        min_market_breadth_pct=40.0,
        regime_bull_position_pct=12.0,
        regime_neutral_position_pct=7.0,
        regime_bear_position_pct=0.0,
        regime_confirmation_days=1 # Set to 1 for immediate switch in test
    )

    # Case 1: Low ADX + High Breadth (70) -> BULL (12%)
    breadth_map = {d.date(): 70.0 for d in dates}
    rmap = _build_regime_map(bench_df, config, breadth_map=breadth_map)
    assert rmap[dates[1].date()] == 12.0

    # Case 2: Low ADX + Low Breadth (30) -> BEAR (0%)
    breadth_map = {d.date(): 30.0 for d in dates}
    rmap = _build_regime_map(bench_df, config, breadth_map=breadth_map)
    assert rmap[dates[1].date()] == 0.0

    # Case 3: Low ADX + Mid Breadth (50) -> NEUTRAL (7%)
    breadth_map = {d.date(): 50.0 for d in dates}
    rmap = _build_regime_map(bench_df, config, breadth_map=breadth_map)
    assert rmap[dates[1].date()] == 7.0

if __name__ == "__main__":
    pytest.main([__file__])
```

- [ ] **Step 2: Run verification test**

Run: `pytest backend/tests/backtest/test_breadth_regime.py`
Expected: PASS

- [ ] **Step 3: Final Commit**

```bash
git add backend/tests/backtest/test_breadth_regime.py
git commit -m "test(backtest): add unit tests for breadth-aware regime overrides"
```
