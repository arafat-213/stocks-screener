# Phase 4: Strategic Tuning & Alpha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor RSI overbought logic into a "State Engine", transition the 200 EMA filter into a scoring factor, and update the parameter sweep for weight optimization.

**Architecture:**
- Centralize signal state management in `TechnicalStrategy`.
- Decouple "Exit Signals" from "Entry Scores" to allow high-alpha parabolic moves.
- Transition from binary "kill" filters to weighted evidence-based scoring.

**Tech Stack:** Python, Pandas, Pandas-TA, Pytest

---

### Task 1: Update Trading Configuration

**Files:**
- Modify: `backend/app/core/trading_config.py`

- [ ] **Step 1: Add new configuration parameters**

```python
# In backend/app/core/trading_config.py
@dataclass
class UnifiedTradingConfig:
    # ... existing ...
    # Add these fields
    ema200_weight: float = 7.0
    rsi_overbought_threshold: float = 80.0
    use_state_based_exits: bool = True
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/trading_config.py
git commit -m "feat: add ema200_weight and rsi_overbought_threshold to config"
```

---

### Task 2: Refactor Strategy Logic (RSI & EMA)

**Files:**
- Modify: `backend/app/core/strategy.py`
- Test: `backend/tests/test_scorer_fixes.py`

- [ ] **Step 1: Update `evaluate` method for 200 EMA scoring and RSI overbought state**

In `backend/app/core/strategy.py`:
- Update weight extraction to include `w_ema200 = self.config.ema200_weight`.
- Change `above_200ema` logic: award `w_ema200` points if `True`.
- Change RSI > 80 logic: set `is_overextended = True` instead of zeroing the score.
- Update return dictionary to include `is_overextended`.

- [ ] **Step 2: Update existing tests in `backend/tests/test_scorer_fixes.py`**

Update `test_rsi_component_never_exceeds_weighted_max` to assert `result["is_overextended"]` instead of `score == 0`.

- [ ] **Step 3: Run tests and verify**

Run: `pytest backend/tests/test_scorer_fixes.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/strategy.py backend/tests/test_scorer_fixes.py
git commit -m "refactor: transition 200 EMA to weighted factor and RSI to state-based logic"
```

---

### Task 3: Implement Overextended State Handling in Backtest Engine

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Implement tighter exit for overextended stocks**

In the trade simulation loop of `backend/app/backtest/engine.py`:
- Calculate `is_overextended` state per bar.
- If `is_overextended` and `Price < Previous Day Low`, trigger `overextended_exit`.

- [ ] **Step 2: Run a backtest to verify no regressions**

Run: `pytest backend/tests/test_engine.py -v`

- [ ] **Step 3: Commit**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat: implement overextended state exit logic in backtest engine"
```

---

### Task 4: Update Parameter Sweep Grid

**Files:**
- Modify: `backend/parameter_sweep.py`

- [ ] **Step 1: Add weights to optimization grid**

```python
GRID = {
    "score_threshold": [55.0, 65.0],
    "ema_weight": [25.0, 30.0],
    "macd_weight": [15.0, 25.0],
    "rsi_weight": [15.0, 25.0],
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/parameter_sweep.py
git commit -m "feat: include strategy weights in parameter sweep grid"
```

---

### Task 5: Documentation Update

**Files:**
- Modify: `docs/user-generated-content/IMPROVEMENTS.md`
- Modify: `docs/user-generated-content/CLEANUP_IMPROVEMENTS_ROADMAP.md`

- [ ] **Step 1: Mark Phase 4 items as RESOLVED**

- [ ] **Step 2: Commit**

```bash
git add docs/user-generated-content/
git commit -m "docs: mark Phase 4 as completed"
```
