# Design Doc: Backtest Metrics and Capital Logic Refactor

## 1. Problem Statement
The current backtest engine has three primary issues:
1.  **Unfair Benchmark Comparison:** The benchmark data is fetched for a fixed 3-year period, but metrics are compared against the full range, even if the strategy only trades within a much narrower `date_from`/`date_to` window.
2.  **Meaningless Capital:** `starting_capital` is dynamically computed based on the total number of trades taken (`n_trades * 10,000`). This makes `total_return_pct` identical to `avg_return_pct` and doesn't reflect real-world portfolio growth.
3.  **Equity Curve Misalignment:** The benchmark equity curve starts from the beginning of the fetched 3-year history rather than being re-anchored to the strategy's start date.

## 2. Proposed Changes

### 2.1 Config Extension (`BacktestConfig`)
Add two new parameters to `BacktestConfig` and the `BacktestRequest` Pydantic model:
- `starting_capital` (float, default: `1,000,000`): The total portfolio value at the start of the backtest.
- `position_size` (float, default: `10,000`): The fixed amount (in currency) allocated to each trade.

### 2.2 Benchmark Filtering and Re-anchoring
In `run_backtest`, slice the `benchmark_df` using `config.date_from` and `config.date_to` *before* passing it to `compute_metrics`.
- If `date_from` is not provided, the slice should start from the `entry_date` of the first trade (i.e., `min(t.entry_date for t in trades)`). If there are no trades, fall back to the earliest available benchmark date.
- If `date_to` is not provided, it defaults to the latest available benchmark date.

### 2.3 Metrics Calculation (`compute_metrics`)
Update the logic in `compute_metrics`:
- **Base Capital:** Use `config.starting_capital` instead of derived capital.
- **Total PnL:** Sum of absolute profit/loss for each trade: `sum((return_pct / 100) * config.position_size)`.
- **Total Return %:** `(Total PnL / config.starting_capital) * 100`.
- **Sharpe Ratio:** Compute on the daily portfolio return series derived from the equity curve: `daily_return_t = (equity_t - equity_{t-1}) / equity_{t-1}`. Annualize as `(mean_daily_return / std_daily_return) * sqrt(252)`.
- **Equity Curve:**
    - Both `equity` and `benchmark_equity` will start at `config.starting_capital`.
    - `benchmark_equity` on day `t` will be `config.starting_capital * (BenchmarkPrice_t / BenchmarkPrice_0)`.

### 2.4 DB Schema Update
Add `starting_capital` (Float) and `position_size` (Float) as dedicated columns on the `BacktestRun` model in addition to being present in the `config` JSON field. 
- Update `_serialize_run` in `backend/app/routers/backtest.py` to read from these columns directly.
- **Action:** Generate an Alembic migration to add these columns to the `backtest_runs` table.

## 3. Data Flow
1.  User starts backtest via API with optional `starting_capital` and `position_size`.
2.  `run_backtest` fetches 3y benchmark data.
3.  `run_backtest` filters benchmark data to match the requested date range.
4.  `compute_metrics` uses the filtered benchmark and new capital config to generate the equity curve.
5.  Results are saved to `backtest_runs` table.

## 4. Testing Strategy
- **Unit Test:** Add a test case to `backend/tests/unit/test_backtest_engine.py` that verifies `total_return_pct` is correctly calculated relative to `starting_capital` (and is different from `avg_return_pct` when n_trades * position_size != starting_capital).
- **Integration Test:** Verify benchmark slicing and re-anchoring in a simulated run.
