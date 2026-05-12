# Backtest Router Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align `backend/app/routers/backtest.py` with the exact structure defined in `docs/superpowers/specs/2026-05-12-backtesting-engine.md`.

**Architecture:** Update FastAPI router models, serialization helpers, and endpoint logic to match the specified JSON structure and query parameters.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Pydantic.

---

### Task 1: Update BacktestRequest Validation

**Files:**
- Modify: `backend/app/routers/backtest.py`

- [ ] **Step 1: Update `target_pct` max and `holding_days` max**
Update `target_pct` Field to `le=200` and `holding_days` to `le=252`.

```python
class BacktestRequest(BaseModel):
    score_threshold: float = Field(default=60.0, ge=0, le=100,
        description="Minimum score to trigger a trade. Use 0–70 range when include_fundamentals=false.")
    holding_days: int = Field(default=20, ge=1, le=252)
    stop_loss_pct: float = Field(default=7.0, ge=0, le=50,
        description="0 disables stop-loss.")
    target_pct: float = Field(default=0.0, ge=0, le=200,
        description="0 disables profit target.")
    include_fundamentals: bool = False
    symbol_limit: Optional[int] = Field(default=None, ge=1, le=500)
    date_from: Optional[str] = None   # "YYYY-MM-DD"
    date_to: Optional[str] = None     # "YYYY-MM-DD"
```

- [ ] **Step 2: Update `start_backtest` to handle string dates**
The spec uses `Optional[str]` for dates in `BacktestRequest`, so `start_backtest` needs to parse them.

---

### Task 2: Refactor _serialize_run

**Files:**
- Modify: `backend/app/routers/backtest.py`

- [ ] **Step 1: Update `_serialize_run` signature and logic**
Add `include_curve: bool` parameter. Implement `progress` dict, conditional `metrics`, and conditional `equity_curve`.

```python
def _serialize_run(run: models.BacktestRun, include_curve: bool) -> dict:
    config = json.loads(run.config) if run.config else {}
    result = {
        "run_id": run.run_id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "status": run.status,
        "config": config,
        "progress": {
            "symbols_done": run.symbols_done or 0,
            "symbols_total": run.symbols_total or 0,
            "pct": round((run.symbols_done or 0) / max(run.symbols_total or 1, 1) * 100, 1)
        },
        "error_message": run.error_message,
        "metrics": None
    }
    if run.status == 'complete':
        result["metrics"] = {
            "total_trades": run.total_trades,
            "winning_trades": run.winning_trades,
            "win_rate": run.win_rate,
            "avg_return_pct": run.avg_return_pct,
            "median_return_pct": run.median_return_pct,
            "best_trade_pct": run.best_trade_pct,
            "worst_trade_pct": run.worst_trade_pct,
            "max_drawdown_pct": run.max_drawdown_pct,
            "sharpe_ratio": run.sharpe_ratio,
            "total_return_pct": run.total_return_pct,
            "benchmark_return_pct": run.benchmark_return_pct,
        }
        if include_curve and run.equity_curve_json:
            result["equity_curve"] = json.loads(run.equity_curve_json)
    return result
```

---

### Task 3: Align Endpoints and Docstrings

**Files:**
- Modify: `backend/app/routers/backtest.py`

- [ ] **Step 1: Update `list_backtest_runs`**
Ensure it uses `_serialize_run(r, include_curve=False)`. Update docstring.

- [ ] **Step 2: Update `get_backtest_run` (currently `get_backtest_details`)**
Rename to `get_backtest_run` and ensure it uses `_serialize_run(run, include_curve=True)`. Update docstring.

- [ ] **Step 3: Update `get_backtest_trades`**
Add `sort_by` and `sort_dir` parameters. Implement sorting. Update docstring.

```python
@router.get("/{run_id}/trades")
def get_backtest_trades(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    sort_by: str = Query(default='exit_date'),
    sort_dir: str = Query(default='desc'),
    exit_reason: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """
    Paginated trade list for a backtest run.
    Supports filtering by exit_reason ('holding_period', 'stop_loss', 'target').
    """
    # ... logic ...
```

---

### Task 4: Verification

**Files:**
- Run: `pytest backend/tests/api/test_backtest.py`

- [ ] **Step 1: Run existing API tests**
Verify no regressions and that the output structure matches expectations.
