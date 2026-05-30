# Backtest Engine Merge Conflict Resolution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all merge conflicts in `backend/app/backtest/engine.py` while merging Model B support with improved technical metrics and exit logic.

**Architecture:** Hybrid approach merging `HEAD`'s Model B (Screen-driven) orchestration with `feat/improve-backtest-engine`'s advanced exit logic (ATR trail, breakeven) and weighted metrics.

**Tech Stack:** Python, pandas, pandas-ta, SQLAlchemy.

---

### Task 1: Resolve Top-level Imports and Constants

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Clean up imports and caches**
Ensure imports are clean and all three caches (`_TA_CACHE`, `_TA_METADATA`, `_OHLCV_CACHE`) are preserved at the top of the file.

- [ ] **Step 2: Commit**
```bash
git add backend/app/backtest/engine.py
git commit -m "refactor: clean up imports and preserve caches in backtest engine"
```

### Task 2: Resolve `_build_screen_driven_signals` and `score_series`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Keep `_build_screen_driven_signals` from HEAD**
This function is critical for Model B and only exists in `HEAD`.

- [ ] **Step 2: Resolve `score_series`**
Use `HEAD` version which includes the `symbol` parameter and pre-computed consolidation series.

```python
def score_series(
    df: pd.DataFrame, symbol: str = None, fund_cache=None, config: BacktestConfig = None
):
    if df is None or len(df) < 210:
        return []

    fund_score = 0.0
    if config and config.include_fundamentals and fund_cache:
        from app.pipeline.scorer import calculate_fundamental_score
        fund_score = calculate_fundamental_score(None, fund_cache=fund_cache)

    df_ind = _compute_all_indicators(df, symbol=symbol)

    lookback = config.consolidation_bars if config else 15
    max_range = config.consolidation_max_range_pct if config else 12.0
    rolling_high = df_ind["High"].rolling(lookback).max().shift(1)
    rolling_low = df_ind["Low"].rolling(lookback).min().shift(1)
    range_pct = (rolling_high - rolling_low) / rolling_low * 100
    is_consolidating_series = range_pct <= max_range

    results = []
    MIN_BARS = 260

    for i in range(MIN_BARS, len(df_ind)):
        try:
            bar_data = _score_bar_from_precomputed(df_ind, i)
        except Exception as e:
            logger.error("score_series bar %d error: %s", i, e)
            continue

        total_score = bar_data["score"] + fund_score

        if bar_data.get("above_200ema") is not True:
            total_score = 0.0

        if bar_data.get("rsi", 0) > 80:
            total_score = 0.0

        is_consolidating = bool(is_consolidating_series.iloc[i])

        results.append(
            {
                "date": df_ind.index[i],
                "score": float(total_score),
                "is_bullish": bar_data["is_bullish"],
                "rsi": bar_data["rsi"],
                "adx": bar_data["adx"],
                "ema_signal": bar_data["ema_signal"],
                "volume_signal": bar_data["volume_signal"],
                "rsi_signal": bar_data["rsi_signal"],
                "close": float(df_ind["Close"].iloc[i]),
                "open": float(df_ind["Open"].iloc[i]),
                "volume_breakout": bar_data["volume_breakout"],
                "atr": bar_data["atr"],
                "above_200ema": bar_data["above_200ema"],
                "momentum_12m": bar_data.get("momentum_12m"),
                "momentum_3m": bar_data.get("momentum_3m"),
                "ema20": bar_data.get("ema20"),
                "is_consolidating": is_consolidating,
            }
        )

    return results
```

- [ ] **Step 3: Commit**
```bash
git add backend/app/backtest/engine.py
git commit -m "feat: resolve score_series with pre-computed consolidation and Model B support"
```

### Task 3: Resolve `_lookup_mtf_state` and `_compute_signal_tier`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Use HEAD versions**
Use the `HEAD` versions for these helpers as they have better comments and formatting.

- [ ] **Step 2: Commit**
```bash
git add backend/app/backtest/engine.py
git commit -m "style: resolve minor helpers in backtest engine"
```

### Task 4: Resolve `simulate_trades` (The Core Loop)

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Merge entry logic**
Include `HEAD`'s Screen membership gate (Model A), re-entry gap (Model B), and RS (Relative Strength) gate. Use the `feat` branch's pullback entry logic.

- [ ] **Step 2: Merge exit logic**
Include `feat`'s ATR-based trailing stop, breakeven logic, and partial exits. Ensure it respects `HEAD`'s `is_screen_driven` checks for structural stops.

- [ ] **Step 3: Commit**
```bash
git add backend/app/backtest/engine.py
git commit -m "feat: merged advanced exit logic with Model B guards in simulate_trades"
```

### Task 5: Resolve `compute_metrics`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Use weighted metrics from feat branch**
Implement the capital-weighted win rate and return logic.

- [ ] **Step 2: Commit**
```bash
git add backend/app/backtest/engine.py
git commit -m "feat: implement weighted performance metrics in backtest engine"
```

### Task 6: Resolve `run_backtest` Orchestrator

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Use HEAD's symbol selection and regime filter**
Preserve the Golden Cross regime filter (50/200 EMA) and the historical screen result fetching from the database (Model B).

- [ ] **Step 2: Preserve feat's logging and status updates**
Ensure status is updated to 'running' and logging is properly initialized.

- [ ] **Step 3: Commit**
```bash
git add backend/app/backtest/engine.py
git commit -m "feat: resolve run_backtest with Golden Cross regime and historical screen data"
```

### Task 7: Final Verification

**Files:**
- Verify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Search for conflict markers**
Run: `grep -E "<<<<<<<|=======|>>>>>>>" backend/app/backtest/engine.py`
Expected: No matches.

- [ ] **Step 2: Run syntax check**
Run: `python3 -m py_compile backend/app/backtest/engine.py`
Expected: Success.

- [ ] **Step 3: Commit final changes**
```bash
git add backend/app/backtest/engine.py
git commit -m "chore: final cleanup and syntax verification of backtest engine"
```
