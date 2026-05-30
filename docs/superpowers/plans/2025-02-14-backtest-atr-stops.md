# Backtest Engine ATR Stops Logic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement dynamic ATR-based stops and targets in the backtest engine to match the pipeline logic.

**Architecture:**
1. Update `score_series` to include ATR in the technical signals list.
2. Update `simulate_trades` to use ATR-based stop loss and profit target calculations if `use_atr_stops` is enabled in the configuration.

**Tech Stack:** Python, pandas, pandas-ta, pytest

---

### Task 1: Failing Test for ATR Stops

**Files:**
- Modify: `backend/tests/unit/test_backtest_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_simulate_trades_uses_atr_stops():
    df = create_dummy_df(100)
    # Force a signal at index 60 with ATR info
    atr_value = 5.0
    scored_dates = [{
        "date": df.index[60],
        "score": 100.0,
        "rsi": 50.0,
        "adx": 20.0,
        "ema_signal": "bullish",
        "atr": atr_value
    }]

    # config: multiplier 2.0, RR 2.0
    # Stop Loss = entry_price - (2.0 * 5.0) = entry_price - 10.0
    # Target = entry_price + (2.0 * 2.0 * 5.0) = entry_price + 20.0
    config = BacktestConfig(
        score_threshold=80.0,
        use_atr_stops=True,
        atr_multiplier=2.0,
        risk_reward_ratio=2.0,
        holding_days=10
    )

    # Mock price movement to trigger ATR target
    entry_price = float(df.iloc[61]['Open'])
    target_price = entry_price + 20.0
    df.iloc[62, df.columns.get_loc('High')] = target_price + 1.0

    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == 'target'
    # Use approx for float comparison
    assert trade.exit_price == pytest.approx(target_price)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend backend/venv/bin/pytest backend/tests/unit/test_backtest_engine.py::test_simulate_trades_uses_atr_stops -v`
Expected: FAIL (logic not implemented)

### Task 2: Implement ATR inclusion in `score_series`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Update `score_series` to include `atr`**

```python
        results.append({
            "date": df.index[i],
            "score": float(total_score),
            "is_bullish": bool(ta_data['is_bullish']),
            "rsi": float(ta_data['rsi']) if ta_data['rsi'] else 0.0,
            "adx": float(ta_data['adx']) if ta_data.get('adx') is not None else 0.0,
            "ema_signal": ta_data['ema_signal'],
            "volume_signal": ta_data['volume_signal'],
            "rsi_signal": ta_data['rsi_signal'],
            "close": price,
            "open": open_price,
            "volume_breakout": bool(ta_data.get('volume_breakout', False)),
            "atr": ta_data.get('atr')  # Add this line
        })
```

- [ ] **Step 2: Commit changes**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat: include ATR in backtest scored results"
```

### Task 3: Implement ATR-based stops logic in `simulate_trades`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Update `simulate_trades` to use ATR logic**

Update the stop loss and target price calculations to check for `config.use_atr_stops` and the presence of `atr` in the signal.

- [ ] **Step 2: Run test to verify it passes**

Run: `PYTHONPATH=backend backend/venv/bin/pytest backend/tests/unit/test_backtest_engine.py::test_simulate_trades_uses_atr_stops -v`
Expected: PASS

- [ ] **Step 3: Run all backtest engine tests**

Run: `PYTHONPATH=backend backend/venv/bin/pytest backend/tests/unit/test_backtest_engine.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit changes**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat: implement dynamic ATR-based stops and targets in backtest engine"
```
