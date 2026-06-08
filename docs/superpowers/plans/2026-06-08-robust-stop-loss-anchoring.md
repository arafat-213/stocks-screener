# Robust Stop-Loss Anchoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix "Zombie Stops" and high-volatility entry failures by anchoring stops to the actual entry price and adding pre-entry validation gates.

**Architecture:**
1.  **Refactor Stop Calculation:** Move stop-loss logic from signal detection to entry execution in `simulate_trades`.
2.  **Hybrid Anchoring:** Implement a three-way stop: Tighter of (Structural consolidation low, Entry-relative ATR, Hard percentage floor).
3.  **Gatekeeping:** Add two conditional checks to skip entries: `signal_bar_volatility` (pre-entry) and `entry_day_violation` (at entry).

**Tech Stack:** Python, Pandas, SQLAlchemy.

---

### Task 1: Update Configuration Schema

**Files:**
- Modify: `backend/app/core/trading_config.py`
- Modify: `backend/app/backtest/engine.py` (mapping logic)

- [ ] **Step 1: Add `initial_stop_atr_multiplier` to `UnifiedTradingConfig`**
```python
# backend/app/core/trading_config.py
# Add initial_stop_atr_multiplier: float = 2.0 to the dataclass
```

- [ ] **Step 2: Update `simulate_trades` local config mapping**
Ensure the new field is passed through and accessible in the trade loop.

- [ ] **Step 3: Commit**
```bash
git add backend/app/core/trading_config.py backend/app/backtest/engine.py
git commit -m "feat: add initial_stop_atr_multiplier to config"
```

---

### Task 2: Implement Signal Volatility Filter

**Files:**
- Modify: `backend/app/backtest/engine.py`
- Test: `backend/tests/test_engine_fixes.py`

- [ ] **Step 1: Write failing test for Signal Volatility**
Create a test where signal bar range is 20% and stop distance is 5%. Verify signal is skipped.

- [ ] **Step 2: Implement filter in `simulate_trades`**
Calculate `signal_bar_range_pct` and `intended_stop_pct` (proxied by signal close). Skip if range > 1.5x stop.

- [ ] **Step 3: Verify and Commit**
```bash
pytest backend/tests/test_engine_fixes.py
git commit -m "feat: add signal volatility filter"
```

---

### Task 3: Refactor Stop Anchoring & Falling Knife Filter

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Move stop calculation inside entry block**
Remove the signal-time `stop_price` calculation. Move it after `entry_price` is confirmed.

- [ ] **Step 2: Implement Hybrid Anchoring logic**
`stop_price = max(struct_stop, vol_stop, hard_cap_stop)`
`stop_price = min(stop_price, entry_price * 0.99)`

- [ ] **Step 3: Implement Falling Knife filter**
`if entry_day_low <= stop_price: continue`

- [ ] **Step 4: Run regression tests and Commit**
```bash
pytest backend/tests/test_engine.py
git commit -m "refactor: anchor stop-loss to entry price and add falling knife filter"
```

---

### Task 4: Final Validation

- [ ] **Step 1: Create regression test for "Zombie Stop"**
Verify a 7% stop results in a 7% loss even if entry is far from signal.

- [ ] **Step 2: Run benchmark and confirm metrics**
Verify `avg_loss_pct` is now healthy and -31% outliers are gone.
