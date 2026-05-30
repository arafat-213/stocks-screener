# Scoring Logic Unification & Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify scoring logic by making `scorer.py` the single source of truth and improve signal quality by detecting crossovers and pullbacks.

**Architecture:** Refactor `score_series` in `engine.py` to call `calculate_technical_score` from `scorer.py` on bar slices. Update `scorer.py` with tiered scoring for EMA, MACD, and RSI.

**Tech Stack:** Python, FastAPI, pandas, pandas-ta, SQLAlchemy.

---

### Task 1: Update Scorer with Tiered EMA Logic

**Files:**
- Modify: `backend/app/pipeline/scorer.py`
- Test: `backend/tests/unit/test_scorer.py` (update existing or add new)

- [x] **Step 1: Update `calculate_technical_score` for tiered EMA**
Update the EMA scoring block to handle fresh crossovers and pullbacks.

```python
# In calculate_technical_score
prev_ema5 = prev.get('EMA_5')
prev_ema13 = prev.get('EMA_13')

fresh_ema_cross = (
    pd.notna(ema5) and pd.notna(ema13) and
    pd.notna(prev_ema5) and pd.notna(prev_ema13) and
    ema5 > ema13 and prev_ema5 <= prev_ema13
)

pullback_to_ema20 = (
    pd.notna(ema20) and pd.notna(price) and
    pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and
    ema5 > ema13 > ema26 and
    abs(price - ema20) / ema20 < 0.02
)

if fresh_ema_cross:
    score += 20
    ema_signal = "bullish_cross"
elif pullback_to_ema20:
    score += 15
    ema_signal = "bullish_pullback"
elif pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and ema5 > ema13 > ema26 and price > ema26:
    score += 8
    ema_signal = "bullish"
elif pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and ema5 < ema13 < ema26:
    ema_signal = "bearish"
```

- [x] **Step 2: Run tests**
Run: `pytest backend/tests/unit/test_scorer.py`

### Task 2: Update Scorer with Tiered MACD Logic

**Files:**
- Modify: `backend/app/pipeline/scorer.py`

- [x] **Step 1: Update MACD scoring block**
```python
prev_macd = prev.get('MACD_12_26_9')
prev_signal_line = prev.get('MACDs_12_26_9')

if pd.notna(macd_line) and pd.notna(signal_line):
    fresh_macd_cross = (
        pd.notna(prev_macd) and pd.notna(prev_signal_line) and
        macd_line > signal_line and prev_macd <= prev_signal_line
    )
    if fresh_macd_cross:
        score += 20
    elif macd_line > signal_line and macd_line < 0:
        score += 12
    elif macd_line > signal_line and macd_line > 0:
        score += 6
```

### Task 3: Update Scorer with Tiered RSI Logic & is_bullish Flag

#### Dependency: fresh_ema_cross and pullback_to_ema20 must already be defined earlier in the same if timeframe == 'D': block as computed in Task 1.Do not implement Task 3 before Task 1.

**Files:**
- Modify: `backend/app/pipeline/scorer.py`

- [x] **Step 1: Update RSI scoring block**
```python
if recovering and fresh_ema_cross:
    score += 20
    rsi_signal = "bullish_recovery_confirmed"
elif recovering:
    score += 15
    rsi_signal = "bullish_recovery"
elif crossing_50:
    score += 10
    rsi_signal = "bullish_crossing"
elif rsi > 50:
    score += 3
    rsi_signal = "bullish_strong"
```

- [x] **Step 2: Update `is_bullish` definition**
```python
is_bullish = (
    (fresh_ema_cross or pullback_to_ema20 or
     (pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and ema5 > ema13 > ema26)) and
    pd.notna(macd_line) and pd.notna(signal_line) and macd_line > signal_line and
    pd.notna(rsi) and rsi > 45
)
```

### Task 4: Refactor `score_series` in `engine.py`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [x] **Step 1: Rewrite `score_series`**
Remove old O(n) implementation and replace with O(n^2) slice-based calls to `calculate_technical_score`.

```python
def score_series(df: pd.DataFrame, fund_cache=None, config: BacktestConfig = None):
    if df is None or len(df) < 60:
        return []

    fund_score = 0.0
    if config and config.include_fundamentals and fund_cache:
        fund_score = calculate_fundamental_score(None, fund_cache=fund_cache)

    results = []
    MIN_BARS = 60

    for i in range(MIN_BARS, len(df)):
        bar_df = df.iloc[:i+1]
        ta_data = calculate_technical_score(bar_df, timeframe='D')

        price = float(bar_df['Close'].iloc[-1])
        open_price = float(bar_df['Open'].iloc[-1])
        total_score = ta_data['score'] + fund_score

        # above_200ema is already computed inside calculate_technical_score
        if ta_data.get('above_200ema') == False:  # explicitly False, not None
            total_score = 0.0

        results.append({
            "date": df.index[i],
            "score": float(total_score),
            "is_bullish": bool(ta_data['is_bullish']),
            "rsi": float(ta_data['rsi']) if ta_data['rsi'] else 0.0,
            "adx": float(ta_data.get('adx', 0.0)),
            "ema_signal": ta_data['ema_signal'],
            "volume_signal": ta_data['volume_signal'],
            "rsi_signal": ta_data['rsi_signal'],
            "close": price,
            "open": open_price,
            "volume_breakout": bool(ta_data.get('volume_breakout', False))
        })
    return results
```

- [x] **Step 2: Cleanup unused imports and variables in `engine.py`**

### Task 5: Update Defaults and Recalibrate Thresholds

**Files:**
- Modify: `backend/app/backtest/engine.py`
- Modify: `backend/app/routers/backtest.py`

- [x] **Step 1: Update `BacktestConfig` default**
Change `score_threshold` to `45.0`.

- [x] **Step 2: Update `BacktestRequest` schema**
Change `score_threshold` default to `45.0` and update description.

### Task 6: Final Verification

- [x] **Step 1: Run all backend tests**
Run: `pytest backend/tests`
- [x] **Step 2: Manual Smoke Test**
Trigger a backtest via API and verify it completes without error.
