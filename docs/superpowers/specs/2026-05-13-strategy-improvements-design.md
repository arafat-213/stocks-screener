# Strategy Improvements Design

## 1. Objective
Improve the backtesting strategy's performance by reducing false positive entries during bearish regimes and extended breakouts, and protecting profits on winning trades.

## 2. Key Components
1. **Backtest Config**: Add parameters for trailing stop, regime filtering, and volume breakout enforcement.
2. **Hard Filters & Scoring**: Apply strict filters (RSI, EMA200, ADX) and ADX weighting only in the backtesting environment (`score_series`), keeping the live pipeline (`calculate_technical_score`) unaffected.
3. **Market Regime Filter**: Use the Nifty 50 (^NSEI) 50-day EMA to determine market regime and block long entries during bearish periods.
4. **Trailing Stop**: Implement a percentage-from-peak trailing stop to secure gains before the fixed holding period ends.

## 3. Detailed Design

### 3.1 BacktestConfig Updates (`backend/app/backtest/engine.py`)
Add the following fields:
- `trailing_stop_pct: float = 0.0`
- `require_volume_breakout: bool = False`
- `use_regime_filter: bool = True`

### 3.2 Hard Filters and Scoring Weighting (`score_series` in `backend/app/backtest/engine.py`)
- # Pre-fetch block (before loop):
ema200_col = 'EMA_200'

# Inside loop, alongside other row.get() calls:
ema200 = row.get(ema200_col)

- **Volume Breakout Calculation**:
  - `volume_breakout = volume > 2.0 * sma20_vol and is_green`
  - Add `"volume_breakout": volume_breakout` to the returned signal dictionary.
- **Hard Filters** (Skip signal or set score=0 if):
# Hard filter:
if pd.notna(ema200) and price < ema200:
    continue
  - `rsi > 70` (Overbought)
  - `price < ema200` (Not in a long-term uptrend)
  - `adx < 20` (No meaningful trend)
- **Score Weighting**:
  - If `adx > 30`, `score += 10`
  - Else if `adx > 20`, `score += 5`

### 3.3 Market Regime Filter
- **Pre-computation (`run_backtest`)**:
  - Compute `benchmark_df['EMA_50'] = benchmark_df['Close'].rolling(50).mean()`.
  - Create `regime_dict = {
	    ts.date(): (row['Close'] > row['EMA_50'])
	    for ts, row in benchmark_df.iterrows()
	}`.
  - Pass `regime_dict` to `simulate_trades`.
- **Enforcement (`simulate_trades`)**:
  - Update signature: `def simulate_trades(symbol, sector, df, scored_dates, config, regime_dict=None):`
  - If `config.use_regime_filter` is True, verify `regime_dict.get(signal_date, False)` is True. If False, skip the trade.

### 3.4 Trailing Stop & Volume Enforcement (`simulate_trades`)
- **Volume Filter**:
  - If `config.require_volume_breakout` is True, skip trade if `signal['volume_breakout']` is False.
- **Trailing Stop**:
  - Initialize `highest_price_since_entry = entry_price` at the start of the trade.
  - Iterate through the holding period days. On each day, update `highest_price_since_entry = max(highest_price_since_entry, day_high)`.
  - Calculate `trailing_stop_level = highest_price_since_entry * (1 - config.trailing_stop_pct / 100)` (only if `config.trailing_stop_pct > 0`).
  - Check exit: If `day_low <= trailing_stop_level`, exit the trade at `trailing_stop_level` (or `day_open` if `day_open < trailing_stop_level` to be conservative). Set reason to `trailing_stop`.

## 4. Scope Check
This scope is strictly limited to improving the backtest engine (`backend/app/backtest/engine.py`) and introducing the necessary properties to achieve the stated objective. It does not affect the existing dashboard, live pipeline, or database schema (since the BacktestTrade model doesn't explicitly store trailing vs hard stop, the reason string covers it).

## 5. Ambiguity Check
- Trailing stop execution: Is it intra-day? The simulation assumes `day_low` can trigger the stop. If `day_open` is below the stop level, we use `day_open` as the exit price to avoid unrealistic fills.
- Regime dictionary date format: Ensures `benchmark_df.index` format matches `signal_date` (both should be aligned to `datetime.date`).
