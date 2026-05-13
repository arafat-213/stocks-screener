# Strategy Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement market regime filters, ADX scoring, and trailing stops to improve the backtesting engine's performance.

**Architecture:** We will enhance the backtest engine (`backend/app/backtest/engine.py`). `BacktestConfig` will hold new rule parameters. `score_series` will apply backtest-only hard filters and score weighting. `simulate_trades` will respect the regime dictionary, enforce volume breakouts, and apply a percentage-from-peak trailing stop.

**Tech Stack:** Python, Pandas, pandas-ta

---

### Task 1: Update BacktestConfig and Test

**Files:**
- Modify: `backend/app/backtest/engine.py`
- Create/Modify: `backend/tests/unit/test_backtest_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_backtest_engine.py
from app.backtest.engine import BacktestConfig

def test_backtest_config_new_defaults():
    config = BacktestConfig()
    assert config.trailing_stop_pct == 0.0
    assert config.require_volume_breakout is False
    assert config.use_regime_filter is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_backtest_engine.py::test_backtest_config_new_defaults -v`
Expected: FAIL due to missing attributes.

- [ ] **Step 3: Write minimal implementation**

Modify `backend/app/backtest/engine.py` inside `BacktestConfig`:

```python
@dataclass
class BacktestConfig:
    score_threshold: float = 60.0      # minimum score to trigger a trade
    holding_days: int = 20             # trading days to hold
    stop_loss_pct: float = 7.0         # exit if price drops this % (0 = disabled)
    target_pct: float = 0.0            # exit if price rises this % (0 = disabled)
    trailing_stop_pct: float = 0.0     # NEW: percentage drop from highest price
    require_volume_breakout: bool = False # NEW: require volume > 2x SMA20
    use_regime_filter: bool = True     # NEW: Nifty > 50 EMA filter
    include_fundamentals: bool = False  # use current fundamental data
    timeframe: str = 'D'               # 'D' only for now
    date_from: datetime.date = None    # filter signals after this date
    date_to: datetime.date = None      # filter signals before this date
    symbol_limit: int = None           # limit number of symbols to process
    starting_capital: float = 1000000.0
    position_size: float = 10000.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_backtest_engine.py::test_backtest_config_new_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/backtest/engine.py backend/tests/unit/test_backtest_engine.py
git commit -m "feat: add trailing stop and regime filter fields to BacktestConfig"
```

---

### Task 2: Enhance `score_series` with Hard Filters and ADX

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Write minimal implementation**

Modify `backend/app/backtest/engine.py` inside `score_series`:

Find:
```python
        is_green = price > open_price
```

Add below it:
```python
        # Volume Breakout
        volume_breakout = False
        if pd.notna(volume) and pd.notna(sma20_vol):
            if volume > 2.0 * sma20_vol and is_green:
                volume_breakout = True
```

Find:
```python
        # is_bullish definition
        is_bullish = (
            pd.notna(macd_line) and macd_line > signal_line and macd_line > 0 and 
            pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and 
            ema5 > ema13 > ema26 and price > ema26
        )
```

Replace with:
```python
        # is_bullish definition
        is_bullish = (
            pd.notna(macd_line) and macd_line > signal_line and macd_line > 0 and 
            pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and 
            ema5 > ema13 > ema26 and price > ema26
        )
        
          # Hard Filters (zero out score if violated, skip ADX weighting)
	ema200 = row.get('EMA_200')
	hard_filter_triggered = (
	    (pd.notna(rsi) and rsi > 70) or
	    (pd.notna(ema200) and price < ema200) or
	    (pd.notna(adx) and adx < 20)
	)

	if not hard_filter_triggered:
	    if pd.notna(adx):
        	if adx > 30:
	            score += 10
	        elif adx > 20:
	            score += 5
	    total_score = score + fund_score
	else:
	    total_score = 0.0
```

Find the return dict append:
```python
            "open": float(open_price)
        })
```
Change to:
```python
            "open": float(open_price),
            "volume_breakout": bool(volume_breakout)
        })
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat: add ADX scoring and hard filters to score_series"
```

---

### Task 3: Apply Filters and Trailing Stop in `simulate_trades`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Write minimal implementation**

Update signature and add filtering in `backend/app/backtest/engine.py` inside `simulate_trades`:

Find:
```python
def simulate_trades(symbol: str, sector: str, df: pd.DataFrame, scored_dates: list[dict], config: BacktestConfig):
```

Replace with:
```python
def simulate_trades(symbol: str, sector: str, df: pd.DataFrame, scored_dates: list[dict], config: BacktestConfig, regime_dict: dict = None):
```

Find:
```python
        # Date Filtering
        if config.date_from and compare_date < config.date_from:
            continue
        if config.date_to and compare_date > config.date_to:
            continue
```

Add below it:
```python
        # Regime Filter
        if config.use_regime_filter and regime_dict is not None:
            if not regime_dict.get(compare_date, False):
                continue
                
        # Volume Breakout Filter
        if config.require_volume_breakout:
            if not signal.get('volume_breakout', False):
                continue
```

Find the inner loop:
```python
            for k in range(entry_idx, final_idx + 1):
                day_low = df.iloc[k]['Low']
                day_high = df.iloc[k]['High']
```

Replace the inner loop logic (up to `if exit_price is None:`) with:
```python
            highest_price_since_entry = entry_price
            
            for k in range(entry_idx, final_idx + 1):
                day_low = df.iloc[k]['Low']
                day_high = df.iloc[k]['High']
                day_open = df.iloc[k]['Open']
                
                highest_price_since_entry = max(highest_price_since_entry, day_high)
                
                # Check Stop Loss first (conservative)
                if day_low <= stop_loss_price:
                    exit_price = stop_loss_price
                    exit_date = df.index[k]
                    exit_reason = 'stop_loss'
                    last_exit_idx = k
                    break
                    
                # Check Trailing Stop
                if config.trailing_stop_pct > 0:
                    trailing_stop_price = highest_price_since_entry * (1 - config.trailing_stop_pct / 100)
                    if day_low <= trailing_stop_price:
                        # If it gapped down below stop, exit at open
                        exit_price = min(trailing_stop_price, day_open)
                        exit_date = df.index[k]
                        exit_reason = 'trailing_stop'
                        last_exit_idx = k
                        break
                
                # Check Profit Target
                if day_high >= target_price:
                    exit_price = target_price
                    exit_date = df.index[k]
                    exit_reason = 'target'
                    last_exit_idx = k
                    break
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat: implement trailing stop and signal filters in simulate_trades"
```

---

### Task 4: Connect Regime Filter in `run_backtest`

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Write minimal implementation**

Find in `run_backtest`:
```python
        # 1. Fetch benchmark data (^NSEI)
        logger.info("Fetching benchmark data (^NSEI)")
        benchmark_df, _ = fetch_stock_data("^NSEI", append_ns=False, period='3y', fetch_info=False)
```

Add below it:
```python
        regime_dict = {}
        if benchmark_df is not None and not benchmark_df.empty:
            benchmark_df['EMA_50'] = benchmark_df['Close'].rolling(50).mean()
            # Map index date to boolean
            valid = benchmark_df[benchmark_df['EMA_50'].notna()]
	    regime_dict = dict(zip(
	    	valid.index.date,
	    	valid['Close'] > valid['EMA_50']
	    ))
```

Find the `simulate_trades` call in `run_backtest`:
```python
                # Run simulation
                sector = stocks_info.get(symbol, "Unknown")
                trades = simulate_trades(symbol, sector, df, scored_dates, config)
```

Replace with:
```python
                # Run simulation
                sector = stocks_info.get(symbol, "Unknown")
                trades = simulate_trades(symbol, sector, df, scored_dates, config, regime_dict=regime_dict)
```

- [ ] **Step 2: Run all tests to ensure no regressions**

Run: `pytest backend/tests -v`
Expected: PASS (or fail for unrelated reasons, but ensure test_backtest_engine.py passes).

- [ ] **Step 3: Commit**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat: pass regime filter dict to simulate_trades in run_backtest"
```
