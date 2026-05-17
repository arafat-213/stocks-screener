# MTF Config Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `require_weekly_confirmation` and `require_monthly_confirmation` fields to the backtest configuration and request models.

**Architecture:** Update the `BacktestConfig` dataclass and `BacktestRequest` Pydantic model to include the new fields. Ensure the values are correctly passed from the API request to the backtest engine.

**Tech Stack:** Python, FastAPI, Pydantic, Dataclasses

---

### Task 1: Update `BacktestConfig` in `backend/app/backtest/engine.py`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Update `BacktestConfig` dataclass**

Add the new fields after `use_regime_filter`.

```python
<<<<
    use_regime_filter: bool = True     # NEW: Nifty > 50 EMA filter
====
    use_regime_filter: bool = True     # NEW: Nifty > 50 EMA filter
    require_weekly_confirmation: bool = True
    require_monthly_confirmation: bool = False
>>>>
```

- [ ] **Step 2: Verify `BacktestConfig` updates**

Run: `cd backend && python -c "from app.backtest.engine import BacktestConfig; c = BacktestConfig(); print(c.require_weekly_confirmation, c.require_monthly_confirmation)"`
Expected: `True False`

---

### Task 2: Update `BacktestRequest` in `backend/app/routers/backtest.py`

**Files:**
- Modify: `backend/app/routers/backtest.py`

- [ ] **Step 1: Update `BacktestRequest` Pydantic model**

Add the new fields after `use_regime_filter`.

```python
<<<<
    use_regime_filter: bool = True
====
    use_regime_filter: bool = True
    require_weekly_confirmation: bool = Field(
        default=True,
        description="Requires the Weekly signal to be bullish before entering a Daily signal."
    )
    require_monthly_confirmation: bool = Field(
        default=False,
        description="Additionally requires the Monthly signal to be bullish."
    )
>>>>
```

- [ ] **Step 2: Update `start_backtest` handler**

Ensure the new fields are passed to the `BacktestConfig` constructor.

```python
<<<<
        use_regime_filter=request.use_regime_filter,
        atr_multiplier=request.atr_multiplier,
====
        use_regime_filter=request.use_regime_filter,
        require_weekly_confirmation=request.require_weekly_confirmation,
        require_monthly_confirmation=request.require_monthly_confirmation,
        atr_multiplier=request.atr_multiplier,
>>>>
```

- [ ] **Step 3: Verify `BacktestRequest` and `start_backtest` updates**

Run: `cd backend && python -c "from app.routers.backtest import BacktestRequest; r = BacktestRequest(); print(r.require_weekly_confirmation, r.require_monthly_confirmation)"`
Expected: `True False`

---

### Task 3: Final Verification

- [ ] **Step 1: Run verification commands**

Run:
```bash
cd backend
python -c "from app.backtest.engine import BacktestConfig; c = BacktestConfig(); print(c.require_weekly_confirmation, c.require_monthly_confirmation)"
python -c "from app.routers.backtest import BacktestRequest; r = BacktestRequest(); print(r.require_weekly_confirmation, r.require_monthly_confirmation)"
```
Expected output for both: `True False`
