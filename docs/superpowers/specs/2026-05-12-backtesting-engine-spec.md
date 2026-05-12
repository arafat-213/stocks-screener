# Backtesting Engine — Spec

**Version:** 1.2  
**Status:** Approved (Brainstorming Complete)  
**Scope:** Full-stack backtesting engine: async backend runner, DB persistence, REST API, React UI  
**Purpose:** Implementation-ready specification for parameter optimization in the Screener AI tool.

---

## 1. Codebase Anchors

### 1.1 The Scorer Is Already Stateless
`calculate_technical_score(df, timeframe)` in `backend/app/pipeline/scorer.py` is the source of truth for scoring rules. The backtest engine must replicate these rules exactly for row-level processing.

### 1.2 O(n) Approach: Compute Indicators Once, Iterate Rows
To ensure sub-60s performance for ~200 symbols:
1. Call `df.ta.*` once on the full 3y dataset.
2. Iterate over rows from `min_bars` onward.
3. Apply scoring logic using pre-computed scalars.

### 1.3 Symbol Universe & Selection
- **Universe:** Symbols present in `technical_signals`.
- **Selection (when limited):** Order by `date` DESC in `technical_signals` to prioritize stocks with recent activity.

### 1.4 Fundamental Data Handling
- **Status:** `FundamentalCache` stores current data only.
- **Handling:** If `include_fundamentals` is true, current data is applied anachronistically.
- **UI:** A planned disclaimer banner will warn users about this limitation.

---

## 2. Feature Scope
**Goal:** Optimize high-level parameters (Threshold, Holding Days, Stop-Loss, Target %).
- **Outputs:** Per-trade results, aggregate stats (Win Rate, Sharpe), Equity Curve vs Nifty 50.

---

## 3. Database Schema

### 3.1 BacktestRun
Stores run metadata, configuration (JSON), and aggregate results.
- `run_id`: UUID (String)
- `created_at`: DateTime
- `status`: pending | running | complete | failed
- `config`: JSON string of parameters
- `symbols_total`: Integer
- `symbols_done`: Integer
- `error_message`: Text
- `total_trades`: Integer
- `winning_trades`: Integer
- `win_rate`: Float
- `avg_return_pct`: Float
- `median_return_pct`: Float
- `best_trade_pct`: Float
- `worst_trade_pct`: Float
- `max_drawdown_pct`: Float
- `sharpe_ratio`: Float
- `total_return_pct`: Float
- `benchmark_return_pct`: Float
- `equity_curve_json`: Text (JSON array of `{date, equity, benchmark}`)

### 3.2 BacktestTrade
Stores details of every triggered trade.
- `run_id`: FK to BacktestRun
- `symbol`: String
- `sector`: String
- `signal_date`: Date
- `entry_date`: Date
- `exit_date`: Date
- `exit_reason`: holding_period | stop_loss | target
- `signal_score`: Float
- `entry_price`: Float
- `exit_price`: Float
- `return_pct`: Float
- `rsi_at_signal`: Float
- `adx_at_signal`: Float
- `ema_signal`: String

---

## 4. Backend Implementation

### 4.1 Engine (`backend/app/backtest/engine.py`)

#### 4.1.1 `score_series`
Computes all indicators once, then returns a list of daily scoring dicts.
```python
def score_series(df: pd.DataFrame, fund_cache=None, config: BacktestConfig = None) -> list[dict]:
    # 1. df.ta.ema/macd/rsi/atr/adx (append=True)
    # 2. Iterate row i from MIN_BARS to len(df)
    # 3. Apply rules from scorer.py (EMA alignment, MACD, RSI recovery, etc.)
    # 4. Return list of dicts with {date, score, is_bullish, close, open, etc.}
```

#### 4.1.2 `simulate_trades`
Simulates trades based on scored dates.
- Entry: Next-day Open.
- Exit: First of SL hit (using intraday Low), Target hit (using intraday High), or Holding Days elapsed (using Close).

#### 4.1.3 `run_backtest`
Main background runner.
```python
# Symbol Selection Fix (User Feedback):
from sqlalchemy import func
symbol_query = (
    db.query(TechnicalSignal.symbol)
    .group_by(TechnicalSignal.symbol)
    .order_by(func.max(TechnicalSignal.date).desc())
    .all()
)
symbols = [row[0] for row in symbol_query]
if config.symbol_limit:
    symbols = symbols[:config.symbol_limit]
```

### 4.2 Router (`backend/app/routers/backtest.py`)
Standard FastAPI background task pattern with polling endpoints.

---

## 5. Frontend Implementation (`frontend/src/pages/Backtest.jsx`)
- Uses `DataTable` (ui/DataTable.jsx) for trades.
- Uses `Recharts` for the equity curve (Strategy vs ^NSEI).
- Polling mechanism every 3s while status is `running`.

---

## 6. Implementation Order
1. DB Models & Alembic Migrations.
2. Engine Logic & Unit Tests.
3. REST API Router.
4. Frontend API Client & Routing.
5. Backtest Page & Components.

---

## 7. Test Spec (`backend/tests/unit/test_backtest_engine.py`)

#### 7.1 `test_score_series_no_future_leak` (User Feedback)
```python
def test_score_series_no_future_leak():
    """Scores computed on a truncated df must match scores on the full df for the same dates."""
    df = _make_df(300)
    config = BacktestConfig()
    scores_full = score_series(df, config=config)
    scores_trunc = score_series(df.iloc[:200], config=config)
    full_by_date = {r['date']: r['score'] for r in scores_full}
    trunc_by_date = {r['date']: r['score'] for r in scores_trunc}
    common_dates = set(full_by_date.keys()) & set(trunc_by_date.keys())
    assert len(common_dates) > 0
    mismatches = [d for d in common_dates if abs(full_by_date[d] - trunc_by_date[d]) > 0.01]
    assert len(mismatches) == 0
```
