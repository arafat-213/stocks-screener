# Update Trading Configuration Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `BacktestRequest` and `start_backtest` in `backend/app/routers/backtest.py` to match the new `UnifiedTradingConfig` schema, ensuring consistency between API requests and the backtest engine.

**Architecture:** Update Pydantic model `BacktestRequest` with new fields and default values, and update the router function to pass these fields to the configuration object.

**Tech Stack:** FastAPI, Pydantic, Python

---

### Task 1: Update BacktestRequest Model

**Files:**
- Modify: `backend/app/routers/backtest.py`

- [ ] **Step 1: Update `max_sector_positions` default to 3**

```python
    max_sector_positions: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum open positions in a single sector. 0 = unlimited.",
    )
```

- [ ] **Step 2: Add `regime_adx_floor` and `min_market_breadth_pct`**

Add after `regime_adx_threshold`:

```python
    regime_adx_floor: float = Field(default=15.0, ge=0.0, le=100.0)
    min_market_breadth_pct: float = Field(default=40.0, ge=0.0, le=100.0)
```

- [ ] **Step 3: Update `regime_neutral_position_pct` default to 7.0 (to match UnifiedTradingConfig)**

```python
    regime_neutral_position_pct: float = Field(default=7.0, ge=0.0, le=100.0)
```

### Task 2: Update start_backtest function

**Files:**
- Modify: `backend/app/routers/backtest.py`

- [ ] **Step 1: Pass new fields to BacktestConfig constructor**

```python
        regime_adx_floor=request.regime_adx_floor,
        min_market_breadth_pct=request.min_market_breadth_pct,
```

### Task 3: Verification

- [ ] **Step 1: Check syntax and logical consistency**

Run: `python3 -m py_compile backend/app/routers/backtest.py`
Expected: No errors.

- [ ] **Step 2: Commit changes**

```bash
git add backend/app/routers/backtest.py
git commit -m "feat: update BacktestRequest and start_backtest to match UnifiedTradingConfig schema"
```
