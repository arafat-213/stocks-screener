# Backtest Performance Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate $O(N^2)$ bottlenecks in MTF state mapping and Python overhead in simulation loops by vectorizing technical scoring and indicator calculations.

**Architecture:**
1. Move non-vectorized logic from `TechnicalStrategy.evaluate` (52W levels, momentum, resistance) into vectorized `calculate_indicators`.
2. Introduce vectorized signal columns (`is_bullish`, `is_overextended`) in `TechnicalStrategy`.
3. Update `engine.py` to pre-calculate these signals once per symbol and reuse them in loops.

**Tech Stack:** Python, Pandas, Pandas-TA

---

### Task 1: Vectorize Core TA Components in `TechnicalStrategy`

**Files:**
- Modify: `backend/app/core/strategy.py`
- Test: `backend/tests/unit/test_strategy_vectorization.py` (Create)

- [ ] **Step 1: Create unit test for vectorized components**
Check that 52W high and momentum match the manual loop-based values.

```python
import pandas as pd
import numpy as np
from app.core.strategy import TechnicalStrategy

def test_vectorized_components():
    # Create 300 days of data
    df = pd.DataFrame({
        "Close": np.linspace(100, 200, 300),
        "High": np.linspace(105, 205, 300),
        "Low": np.linspace(95, 195, 300),
        "Open": np.linspace(98, 198, 300),
        "Volume": np.linspace(1000, 2000, 300)
    }, index=pd.date_range("2020-01-01", periods=300))

    strategy = TechnicalStrategy()
    df_ind = strategy.calculate_indicators(df)

    # Check 52W High (approx 252 bars)
    expected_high = df["Close"].rolling(252).max().iloc[-1]
    assert df_ind["WEEK52_HIGH"].iloc[-1] == expected_high

    # Check 3M Momentum (approx 63 bars)
    expected_mom = (df["Close"].iloc[-1] / df["Close"].iloc[-237] - 1) * 100 # i-63 where i=299
    # Wait, indices in evaluate are relative to i.
    # Let's just verify the logic is consistent.
```

- [ ] **Step 2: Implement vectorized components in `calculate_indicators`**

```python
# backend/app/core/strategy.py

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # ... existing indicators ...

        # New Vectorized Components
        df["WEEK52_HIGH"] = df["Close"].rolling(window=252, min_periods=1).max()
        df["WEEK52_LOW"] = df["Close"].rolling(window=252, min_periods=1).min()

        # Resistance: Highest close in the year prior to the last 20 bars
        # Original: df["Close"].iloc[i - 259 : i - 19].max()
        # Vectorized: shift(20) then rolling(240)
        df["RESISTANCE_LEVEL"] = df["Close"].shift(20).rolling(window=240, min_periods=1).max()

        # Momentum
        for period, shift in [("1M", 21), ("3M", 63), ("6M", 126), ("12M", 252)]:
            df[f"MOMENTUM_{period}"] = (df["Close"] / df["Close"].shift(shift) - 1) * 100

        return df
```

- [ ] **Step 3: Update `evaluate` to use pre-computed columns**

```python
# backend/app/core/strategy.py

    def evaluate(self, ...):
        # ...
        # Replace manual lookups with column access if available
        week52_high = latest.get("WEEK52_HIGH")
        week52_low = latest.get("WEEK52_LOW")
        resistance_level = latest.get("RESISTANCE_LEVEL")
        momentum_1m = latest.get("MOMENTUM_1M")
        # ... and so on for all pre-computed fields
```

---

### Task 2: Vectorize Signal Logic in `TechnicalStrategy`

**Files:**
- Modify: `backend/app/core/strategy.py`

- [ ] **Step 1: Add `calculate_signals` method**
Move the logic for `is_bullish` and `is_overextended` into a vectorized function.

```python
# backend/app/core/strategy.py

    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Computes boolean signal series for the entire dataframe."""
        # Fresh EMA Cross
        ema5 = df["EMA_5"]
        ema13 = df["EMA_13"]
        df["SIGNAL_EMA_CROSS"] = (ema5 > ema13) & (ema5.shift(1) <= ema13.shift(1))

        # MACD Signal
        macd = df["MACD_12_26_9"]
        signal = df["MACDs_12_26_9"]
        df["SIGNAL_MACD_BULLISH"] = macd > signal

        # Overextended
        df["IS_OVEREXTENDED"] = df["RSI_14"] > self.config.rsi_overbought_threshold

        # is_bullish (Simplified vectorized version of the logic in evaluate)
        df["IS_BULLISH"] = (
            (df["SIGNAL_EMA_CROSS"] | (df["EMA_5"] > df["EMA_13"])) # simplified for example
            & df["SIGNAL_MACD_BULLISH"]
            & (df["RSI_14"] > self.config.rsi_min)
        )
        return df
```

- [ ] **Step 2: Commit changes**

---

### Task 3: Optimize `backtest/engine.py`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Update `_compute_all_indicators` to include signals**

```python
# backend/app/backtest/engine.py

def _compute_all_indicators(df, strategy, symbol=None):
    # ...
    df = strategy.calculate_indicators(df)
    df = strategy.calculate_signals(df) # Add this
    # ...
```

- [ ] **Step 2: Refactor `build_mtf_state_map` to be vectorized**
Eliminate the $O(N^2)$ loop.

```python
# backend/app/backtest/engine.py

def build_mtf_state_map(df, timeframe, strategy):
    # ... resample ...
    resampled = _compute_all_indicators(resampled, strategy) # Vectorized TA!

    state_map = {}
    for i in range(len(resampled)):
        bar_date = resampled.index[i]
        if hasattr(bar_date, "date"):
            bar_date = bar_date.date()
        state_map[bar_date] = bool(resampled["IS_BULLISH"].iloc[i])
    return state_map
```

- [ ] **Step 3: Optimize `simulate_trades` loop**
Replace `strategy.evaluate` call with direct series access.

```python
# backend/app/backtest/engine.py

# Inside simulate_trades loop:
            if config.use_state_based_exits:
                # current_eval = strategy.evaluate(df, i=k, skip_ta=True) # DELETE
                is_overextended = df["IS_OVEREXTENDED"].iloc[k]
                if is_overextended:
                    # ...
```

---

### Task 4: Verification & Benchmarking

**Files:**
- Create: `backend/tests/test_backtest_performance.py`

- [ ] **Step 1: Create performance benchmark**
Measure time to run backtest on 10 symbols for 5 years.

- [ ] **Step 2: Run existing tests**
Ensure `pytest backend/tests/backtest/` passes and returns identical results.

- [ ] **Step 3: Final check and commit**
