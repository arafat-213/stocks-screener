# Design Doc: Scoring Logic Unification

## 1. Problem Statement

The backtest engine (`engine.py`) contains a `score_series` function that reimplements indicator and scoring logic already present in `calculate_technical_score` (`scorer.py`). This creates two diverged code paths:

- Any scoring improvement made to `scorer.py` must be manually mirrored in `engine.py` or the backtest silently tests a different strategy than what runs live.
- The dashboard, screens, and daily report all reflect `scorer.py` logic. The backtest reflects `score_series` logic. They are not the same.
- There is no single source of truth for what constitutes a "good entry signal."

## 2. Objective

Make `score_series` a thin orchestration wrapper that calls `calculate_technical_score` per bar. All scoring logic lives exclusively in `scorer.py`. The backtest then truthfully simulates what the live pipeline recommends.

---

## 3. Proposed Changes

### 3.1 Scoring Improvements to `calculate_technical_score` (`scorer.py`)

These are the substantive signal quality improvements. They replace late-confirmation logic with early-entry detection.

#### 3.1.1 EMA Component (currently 20 pts)

Replace static alignment check with a tiered system that rewards early crossovers more than extended trends:

**Current:**
```python
if ema5 > ema13 > ema26 and price > ema26:
    score += 20
    ema_signal = "bullish"
elif ema5 < ema13 < ema26:
    ema_signal = "bearish"
```

**Replace with** (requires `prev` row, already available as `df.iloc[-2]`):
```python
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

#### 3.1.2 MACD Component (currently 20 pts)

Replace `MACD > 0` confirmation with fresh crossover detection:

**Current:**
```python
if pd.notna(macd_line) and pd.notna(signal_line):
    if macd_line > signal_line and macd_line > 0:
        score += 20
```

**Replace with:**
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
        score += 12   # recovering, still below zero
    elif macd_line > signal_line and macd_line > 0:
        score += 6    # confirmed trend but late entry
```

#### 3.1.3 RSI Component (currently 15 pts)

Reward oversold recovery more than RSI-50 crossing, which is a later signal:

**Current:**
```python
if recovering:
    score += 15
    rsi_signal = "bullish_recovery"
elif crossing_50:
    score += 15
    rsi_signal = "bullish_crossing"
elif rsi > 50:
    score += 5
    rsi_signal = "bullish_strong"
```

**Replace with:**
```python
if recovering and fresh_ema_cross:
    score += 20     # highest conviction: price recovering + structure turning
    rsi_signal = "bullish_recovery_confirmed"
elif recovering:
    score += 15
    rsi_signal = "bullish_recovery"
elif crossing_50:
    score += 10     # reduce from 15, this is later stage
    rsi_signal = "bullish_crossing"
elif rsi > 50:
    score += 3      # reduce from 5
    rsi_signal = "bullish_strong"
```

Note: `fresh_ema_cross` is computed in 3.1.1 above. Since RSI runs after EMA in the scoring block, `fresh_ema_cross` is already available as a local variable.

#### 3.1.4 Score Maximum Adjustment

The new maximum technical score (Daily timeframe) is:
- EMA: 20 pts
- MACD: 20 pts
- RSI: 20 pts (recovery + EMA cross combo)
- Volume: 15 pts
- **Total: 75 pts**

The `calculate_combined_score` cap of 100 remains valid since fundamentals add max 30 pts but the clip `max(0.0, min(100.0, combined_score))` handles overflow. No change needed there.

#### 3.1.5 `is_bullish` Flag Update

The `is_bullish` flag definition should reflect early entry, not extended confirmation:

**Current:**
```python
is_bullish = (
    pd.notna(macd_line) and macd_line > signal_line and macd_line > 0 and
    pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and
    ema5 > ema13 > ema26 and price > ema26
)
```

**Replace with:**
```python
is_bullish = (
    (fresh_ema_cross or pullback_to_ema20 or
     (pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and ema5 > ema13 > ema26)) and
    pd.notna(macd_line) and pd.notna(signal_line) and macd_line > signal_line and
    pd.notna(rsi) and rsi > 45
)
```

This makes `is_bullish` true for stocks in any bullish EMA state (fresh cross, pullback, or alignment) with MACD agreement and RSI not deeply bearish. The RSI threshold of 45 rather than 50 catches early recoveries.

---

### 3.2 Refactor `score_series` in `engine.py`

Remove all duplicated indicator computation and scoring logic. Replace with a loop that calls `calculate_technical_score` per bar.

**Current structure** (remove entirely):
- All `df.ta.ema(...)`, `df.ta.macd(...)` etc. calls
- All per-bar score computation blocks
- All local variable duplicates of scoring logic

**Replace with:**

```python
def score_series(df: pd.DataFrame, fund_cache=None, config: BacktestConfig = None):
    """
    Computes scores for each bar by calling calculate_technical_score on the
    history up to that bar. Single source of truth: scorer.py.
    """
    if df is None or len(df) < 60:
        return []

    # Fundamental score computed once (static — we only have current fundamentals)
    fund_score = 0.0
    if config and config.include_fundamentals and fund_cache:
        fund_score = calculate_fundamental_score(None, fund_cache=fund_cache)

    results = []
    MIN_BARS = 60

    for i in range(MIN_BARS, len(df)):
        bar_df = df.iloc[:i+1]  # history up to and including current bar

        ta_data = calculate_technical_score(bar_df, timeframe='D')

        price = float(bar_df['Close'].iloc[-1])
        open_price = float(bar_df['Open'].iloc[-1])

        total_score = ta_data['score'] + fund_score

        # EMA200 hard filter: zero out score if price below long-term trend
        ema200 = bar_df['EMA_200'].iloc[-1] if 'EMA_200' in bar_df.columns else None
        if pd.notna(ema200) and price < ema200:
            total_score = 0.0

        results.append({
            "date": df.index[i],
            "score": float(total_score),
            "is_bullish": bool(ta_data['is_bullish']),
            "rsi": float(ta_data['rsi']) if ta_data['rsi'] else 0.0,
            "adx": float(ta_data['adx']) if ta_data.get('adx') else 0.0,
            "ema_signal": ta_data['ema_signal'],
            "volume_signal": ta_data['volume_signal'],
            "rsi_signal": ta_data['rsi_signal'],
            "close": price,
            "open": open_price,
            "volume_breakout": bool(ta_data.get('volume_breakout', False))
        })

    return results
```

Note: `calculate_technical_score` already calls `df.ta.ema(...)` etc. internally on the sliced DataFrame. This recomputes indicators on each bar slice — an O(n²) operation. See section 4 for the performance note.

---

### 3.3 Remove `calculate_fundamental_score` Import Duplication

`score_series` currently imports and calls `calculate_fundamental_score` directly. After refactor it still needs to call it for the `fund_score`. This is acceptable since `calculate_combined_score` bundles both together and the backtest needs to apply `fund_score` once per symbol (not per bar). The import remains. No change needed.

---

### 3.4 Cleanup: Remove Dead Code from `engine.py`

After the refactor, the following are no longer needed in `engine.py` and should be deleted:

- The `import pandas_ta as ta` line at the top (pandas_ta is now only used in `scorer.py`)
- All pre-loop column name variables (`ema5_col`, `ema13_col`, etc.) inside the old `score_series`
- The entire old per-bar scoring loop body

---

### 3.5 Score Threshold Recalibration Note

The new scoring maximums differ from the old ones. The old max tech score was 70 pts. The new max is 75 pts (with the combined RSI+EMA bonus). More importantly, the **score distribution** changes — fewer stocks will score 60+ because `ema5 > ema13 > ema26` alone now only gives 8 pts instead of 20 pts.

This means **existing score thresholds in BacktestConfig defaults need recalibration**. After the changes:
- `score_threshold = 60` in config will admit fewer signals than before
- The equivalent of the old 60 threshold is approximately 45 in the new system

Update default in `BacktestConfig`:
```python
score_threshold: float = 45.0   # recalibrated from 60.0
```

And update the API field description in `BacktestRequest`:
```python
score_threshold: float = Field(
    default=45.0, ge=0, le=100,
    description="Minimum score. Range 0-75 for tech-only, 0-100 with fundamentals. "
                "Crossover signals score ~45-55. Extended trend signals score ~20-35."
)
```

---

## 4. Performance Note

Calling `calculate_technical_score` with `bar_df = df.iloc[:i+1]` inside a loop means pandas-ta recomputes all indicators on an increasingly large slice on every iteration. For a 3-year daily DataFrame (~750 bars) this is ~700 calls, each computing EMA/MACD/RSI etc. on up to 750 rows.

This is acceptable for backtesting (correctness over speed). Estimated slowdown: 5–10x vs the current O(n) implementation. A full backtest over 200 symbols will take longer.

If this becomes a bottleneck, the future optimization is: precompute all indicators once on the full DataFrame, then in the loop extract the indicator values at row `i` directly. But this is a separate task and should not block the correctness fix.

---

## 5. Scope

Changes are limited to:
- `backend/app/pipeline/scorer.py` — scoring logic improvements
- `backend/app/backtest/engine.py` — `score_series` refactor and cleanup

No DB schema changes. No API changes. No router changes. No screen changes — screens will automatically benefit from improved scores at the next pipeline run.

---

## 6. Validation

After implementation, re-run **Test 2** (regime OFF, full date range, 200 symbols, score threshold 45) as the primary validation. Compare against the previous Test 2 result:

| Metric | Previous Test 2 | Target |
|--------|----------------|--------|
| Win Rate | 31.8% | ≥ 38% |
| Avg Return | -0.08% | > 0% |
| Median Return | -7.0% | > -3% |
| Total Trades | 1300 | 600–1000 (fewer but better) |

The median return moving above -3% is the single most important indicator that signal quality has improved. If median return is still equal to the stop-loss value, the signals are still arriving too late.
