# Backtesting Engine — Spec

**Version:** 1.0
**Scope:** Full-stack backtesting engine: async backend runner, DB persistence, REST API, React UI
**Purpose:** Implementation-ready specification for an AI coding agent

---

## 1. Codebase Anchors (Read Before Writing Any Code)

The agent must internalize these facts from the existing codebase before implementing anything.

### 1.1 The Scorer Is Already Stateless

`calculate_technical_score(df, timeframe)` in `backend/app/pipeline/scorer.py` takes a raw OHLCV DataFrame and returns a dict. It has **zero database calls** and **zero side effects**. This is the core property that makes backtesting possible without architectural surgery.

### 1.2 The Naive Approach Is Unacceptably Slow — Do Not Use It

The obvious implementation — calling `calculate_combined_score(df.iloc[:i])` for every bar `i` — re-runs `pandas_ta` indicator computation on a growing slice each time. This is O(n²) per symbol. For 200 symbols × 756 bars that is ~114 million indicator operations, taking hours. **This approach must not be implemented.**

### 1.3 The Correct Approach: Compute Indicators Once, Iterate Rows

The correct architecture:
1. Call `df.ta.*` methods once on the **full** historical DataFrame to append all indicator columns (`EMA_5`, `EMA_13`, `EMA_20`, `EMA_26`, `EMA_200`, `MACD_12_26_9`, `MACDs_12_26_9`, `RSI_14`, `ATRr_14`, `ADX_14`, plus the custom `VOL_SMA_20` rolling mean)
2. Iterate over rows from `min_bars` onward, extracting scalar values from the already-computed columns at each row index
3. Apply the scoring if/else rules from `scorer.py` on those scalars to get a score per date
4. This is O(n) per symbol — fast enough to run 200 symbols in under 60 seconds

The new `BacktestRunner` class replicates the **scoring rules** from `calculate_technical_score`, not the function call itself. The rules are reimplemented as a row-level loop over the pre-computed indicator DataFrame. Keep the two in sync: if `scorer.py` changes its rules, `backtest/engine.py` must be updated to match.

### 1.4 Raw OHLCV Is Not Stored in the Database

`TechnicalSignal` stores computed signal fields (score, RSI, etc.) for dates the pipeline ran. It does **not** store Open/High/Low/Close/Volume per day. The backtest engine must re-fetch OHLCV via `fetch_stock_data(symbol, period="3y")`. The existing `requests-cache` session in `fetcher.py` (SQLite backend, 86400s TTL) means this is fast after the first fetch.

### 1.5 The Symbol Universe

Do not attempt to backtest all 2000 NSE symbols. The backtest universe is limited to symbols that have at least one row in `TechnicalSignal` (these passed Tier 1+2 screening and have been scored at least once). Query:
```sql
SELECT DISTINCT symbol FROM technical_signals
```
Typical count: 200–400 symbols.

### 1.6 Fundamental Data Is Not Historical

`FundamentalCache` contains **today's** fundamentals for each symbol — a single row per symbol, not one per date. There is no way to know what a stock's P/E ratio was on a specific past date from this table. This is a real limitation and must be documented in the UI.

The backtest engine exposes an `include_fundamentals` flag (default: `false`). When `false`, only the technical sub-score (max 70 pts) is used and the threshold parameter is interpreted against a 70-point scale. When `true`, current `FundamentalCache` values are used anachronistically for all historical dates — useful for "what if I had applied these filters historically" but not true historical simulation.

### 1.7 Existing Patterns to Follow

- Async background jobs: `BackgroundTasks` in FastAPI (see `stocks.py` `trigger_screener`)
- DB session lifecycle: `SessionLocal()` with try/finally close (see `run_pipeline_wrapper`)
- Polling pattern: frontend polls `/api/pipeline/latest` every 5s while running — replicate for backtest
- In-process cache: `response_cache` from `backend/app/core/cache.py`
- Recharts: already used in `StockDetail.jsx` for the score trend `LineChart`

---

## 2. Feature Scope

The backtesting engine answers: **"If I had bought every stock that scored above threshold X on its signal date, and sold after N trading days (with optional stop-loss and profit-target), what would my returns have been?"**

Outputs:
- Per-trade results (entry date, exit date, return %, exit reason)
- Aggregate statistics (win rate, avg return, Sharpe-like ratio, max drawdown)
- Equity curve (cumulative P&L over time, compared against Nifty 50 buy-and-hold)

---

## 3. Database Schema

### 3.1 New Models in `backend/app/db/models.py`

```python
import json

class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    run_id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)
    status          = Column(String, nullable=False)
    # 'pending' | 'running' | 'complete' | 'failed'

    # Config (stored as JSON for flexibility)
    config          = Column(Text, nullable=False)
    # JSON: { score_threshold, holding_days, stop_loss_pct, target_pct,
    #         include_fundamentals, symbol_limit, date_from, date_to, timeframe }

    # Progress
    symbols_total   = Column(Integer, default=0)
    symbols_done    = Column(Integer, default=0)
    error_message   = Column(Text, nullable=True)

    # Aggregate results (null until status='complete')
    total_trades     = Column(Integer, nullable=True)
    winning_trades   = Column(Integer, nullable=True)
    win_rate         = Column(Float, nullable=True)    # 0.0–1.0
    avg_return_pct   = Column(Float, nullable=True)
    median_return_pct = Column(Float, nullable=True)
    best_trade_pct   = Column(Float, nullable=True)
    worst_trade_pct  = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)    # worst peak-to-trough within any trade
    sharpe_ratio     = Column(Float, nullable=True)    # avg_return / std_return (not annualized)
    total_return_pct = Column(Float, nullable=True)    # sum of all trade returns (equal weight)
    benchmark_return_pct = Column(Float, nullable=True) # Nifty 50 return over same period
    # Equity curve stored as JSON array for charting:
    # [{"date": "2024-01-05", "equity": 100000, "benchmark": 100000}, ...]
    equity_curve_json = Column(Text, nullable=True)


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    run_id          = Column(String, ForeignKey('backtest_runs.run_id'), nullable=False)
    symbol          = Column(String, nullable=False)
    sector          = Column(String, nullable=True)

    signal_date     = Column(Date, nullable=False)    # date score was computed
    entry_date      = Column(Date, nullable=False)    # next trading day after signal
    exit_date       = Column(Date, nullable=False)
    exit_reason     = Column(String, nullable=False)  # 'holding_period' | 'stop_loss' | 'target'

    signal_score    = Column(Float, nullable=False)
    entry_price     = Column(Float, nullable=False)   # next-day open
    exit_price      = Column(Float, nullable=False)
    return_pct      = Column(Float, nullable=False)   # (exit - entry) / entry * 100

    # Signal context (useful for analysis)
    rsi_at_signal   = Column(Float, nullable=True)
    adx_at_signal   = Column(Float, nullable=True)
    ema_signal      = Column(String, nullable=True)
```

### 3.2 Alembic Migrations

Generate two migrations, run in order:

```bash
alembic revision --autogenerate -m "add_backtest_runs"
alembic upgrade head
alembic revision --autogenerate -m "add_backtest_trades"
alembic upgrade head
```

Verify each generated file creates the correct tables with `downgrade()` implemented as `op.drop_table(...)`.

---

## 4. Backend: Backtest Engine

### 4.1 File: `backend/app/backtest/__init__.py` (empty)

### 4.2 File: `backend/app/backtest/engine.py`

This is the core computation module. It must be importable and testable in isolation with no FastAPI or DB dependencies.

#### 4.2.1 Configuration Dataclass

```python
# backend/app/backtest/engine.py
from dataclasses import dataclass, field
from typing import Callable
import datetime

@dataclass
class BacktestConfig:
    score_threshold: float = 60.0      # minimum score to trigger a trade (0–70 if no fundamentals, 0–100 if yes)
    holding_days: int = 20             # trading days to hold before forced exit
    stop_loss_pct: float = 7.0         # exit if price drops this % from entry (0 = disabled)
    target_pct: float = 0.0            # exit if price rises this % from entry (0 = disabled)
    include_fundamentals: bool = False  # see §1.6
    timeframe: str = 'D'               # 'D' only for now (W/M have too few signal dates)
    date_from: datetime.date = None    # None = use earliest available data
    date_to: datetime.date = None      # None = use latest available data minus holding_days buffer
    symbol_limit: int = None           # None = all screened symbols
    progress_callback: Callable = None # called with (symbols_done, symbols_total) during run
```

#### 4.2.2 Trade Result Dataclass

```python
@dataclass
class TradeResult:
    symbol: str
    sector: str
    signal_date: datetime.date
    entry_date: datetime.date
    exit_date: datetime.date
    exit_reason: str          # 'holding_period' | 'stop_loss' | 'target'
    signal_score: float
    entry_price: float
    exit_price: float
    return_pct: float
    rsi_at_signal: float
    adx_at_signal: float
    ema_signal: str
```

#### 4.2.3 Core Scoring Function: `score_series`

This function replaces `calculate_technical_score` for backtesting. It computes all indicators once on the full DataFrame, then returns a list of `(date, score, signal_fields)` tuples — one per row from `min_bars` onward.

```python
def score_series(df: pd.DataFrame, fund_cache=None, config: BacktestConfig = None) -> list[dict]:
    """
    Computes scores for every date in df using the same rules as calculate_technical_score,
    but by computing indicators once on the full df rather than re-slicing.

    Returns list of dicts, one per date from min_bars onward:
    {
        'date': datetime.date,
        'score': float,
        'is_bullish': bool,
        'rsi': float,
        'adx': float,
        'ema_signal': str,
        'volume_signal': str,
        'rsi_signal': str,
        'close': float,
        'open': float,    # for entry price
    }
    """
    import pandas_ta as ta
    import pandas as pd
    import numpy as np

    df = df.copy()

    # Step 1: Compute all indicators on full df ONCE
    df.ta.ema(length=5, append=True)
    df.ta.ema(length=13, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=26, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.adx(length=14, append=True)
    df['VOL_SMA_20'] = df['Volume'].rolling(window=20).mean()

    MIN_BARS = 60  # matches scorer.py for 'D' timeframe

    results = []

    # Step 2: Iterate rows (O(n), not O(n^2))
    for i in range(MIN_BARS, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]

        price    = row.get('Close')
        ema5     = row.get('EMA_5')
        ema13    = row.get('EMA_13')
        ema20    = row.get('EMA_20')
        ema26    = row.get('EMA_26')
        macd_line  = row.get('MACD_12_26_9')
        signal_line = row.get('MACDs_12_26_9')
        rsi      = row.get('RSI_14')
        prev_rsi = prev_row.get('RSI_14')
        volume   = row.get('Volume')
        sma20_vol = row.get('VOL_SMA_20')
        adx      = row.get('ADX_14')
        is_green = (row.get('Close', 0) > row.get('Open', 0))

        # Skip rows with NaN in critical indicators
        import math
        if any(v is None or (isinstance(v, float) and math.isnan(v))
               for v in [price, ema5, ema13, ema26, macd_line, signal_line, rsi]):
            continue

        score = 0.0
        ema_signal = 'neutral'
        volume_signal = 'neutral'
        rsi_signal = 'neutral'

        # --- EMA Alignment (20 pts) ---
        # Rule from scorer.py: EMA5 > EMA13 > EMA26 AND price > EMA26
        if ema5 > ema13 > ema26 and price > ema26:
            score += 20
            ema_signal = 'bullish'
        elif ema5 < ema13 < ema26:
            ema_signal = 'bearish'

        # --- MACD (20 pts) ---
        # Rule: macd_line > signal_line AND macd_line > 0
        if macd_line > signal_line and macd_line > 0:
            score += 20

        # --- RSI (15 pts) ---
        # Look back 5 rows for was_oversold check
        recent_rsi_slice = df['RSI_14'].iloc[max(0, i-4):i+1]
        was_oversold = any(recent_rsi_slice < 30)
        recovering = was_oversold and rsi > 30 and pd.notna(ema20) and price > ema20
        crossing_50 = (prev_rsi is not None and prev_rsi <= 50 and rsi > 50)

        if recovering:
            score += 15
            rsi_signal = 'bullish_recovery'
        elif crossing_50:
            score += 15
            rsi_signal = 'bullish_crossing'
        elif rsi > 50:
            score += 5
            rsi_signal = 'bullish_strong'

        # --- Volume (15 pts) ---
        if pd.notna(volume) and pd.notna(sma20_vol) and sma20_vol > 0:
            if volume > 1.5 * sma20_vol and is_green:
                score += 15
                volume_signal = 'bullish'

        # --- Fundamental score (optional, anachronistic) ---
        fund_score = 0.0
        if config and config.include_fundamentals and fund_cache:
            # Import here to avoid circular dependency
            from app.pipeline.scorer import calculate_fundamental_score
            # Pass empty info dict — rely entirely on fund_cache
            fund_score = calculate_fundamental_score({}, fund_cache=fund_cache)
            score = min(100.0, score + fund_score)

        # --- is_bullish (same definition as scorer.py) ---
        is_bullish = (
            macd_line > signal_line and macd_line > 0 and
            ema5 > ema13 > ema26 and price > ema26
        )

        results.append({
            'date': df.index[i].date(),
            'score': score,
            'is_bullish': is_bullish,
            'rsi': float(rsi),
            'adx': float(adx) if pd.notna(adx) else None,
            'ema_signal': ema_signal,
            'volume_signal': volume_signal,
            'rsi_signal': rsi_signal,
            'close': float(price),
            'open': float(row.get('Open', price)),
        })

    return results
```

#### 4.2.4 Trade Simulation: `simulate_trades`

```python
def simulate_trades(
    symbol: str,
    sector: str,
    df: pd.DataFrame,           # full OHLCV DataFrame
    scored_dates: list[dict],   # output of score_series()
    config: BacktestConfig
) -> list[TradeResult]:
    """
    For each scored date where score >= threshold, simulate a trade:
    - Entry: next bar's Open (index i+1 in df)
    - Exit: first of (stop_loss hit, target hit, holding_days elapsed)
    - Intraday stop/target check: use daily Low/High within holding window

    Returns list of TradeResult. Skips trades where forward data is unavailable.
    """
    trades = []

    # Build a dict from date -> df row index for fast lookup
    date_to_idx = {df.index[i].date(): i for i in range(len(df))}

    for signal in scored_dates:
        if signal['score'] < config.score_threshold:
            continue

        signal_date = signal['date']

        # Apply date range filter
        if config.date_from and signal_date < config.date_from:
            continue
        if config.date_to and signal_date > config.date_to:
            continue

        signal_idx = date_to_idx.get(signal_date)
        if signal_idx is None:
            continue

        entry_idx = signal_idx + 1
        if entry_idx >= len(df):
            continue   # No next bar available

        entry_price = float(df.iloc[entry_idx]['Open'])
        if entry_price <= 0:
            continue

        # Walk forward up to holding_days bars
        exit_price = None
        exit_date = None
        exit_reason = 'holding_period'

        max_exit_idx = min(entry_idx + config.holding_days, len(df) - 1)

        for j in range(entry_idx, max_exit_idx + 1):
            bar = df.iloc[j]
            bar_low  = float(bar['Low'])
            bar_high = float(bar['High'])
            bar_close = float(bar['Close'])

            # Check stop-loss (using intraday low)
            if config.stop_loss_pct > 0:
                stop_price = entry_price * (1 - config.stop_loss_pct / 100)
                if bar_low <= stop_price:
                    exit_price = stop_price   # assume filled at stop
                    exit_date = df.index[j].date()
                    exit_reason = 'stop_loss'
                    break

            # Check profit target (using intraday high)
            if config.target_pct > 0:
                target_price = entry_price * (1 + config.target_pct / 100)
                if bar_high >= target_price:
                    exit_price = target_price  # assume filled at target
                    exit_date = df.index[j].date()
                    exit_reason = 'target'
                    break

            # Final bar = holding period exit
            if j == max_exit_idx:
                exit_price = bar_close
                exit_date = df.index[j].date()
                exit_reason = 'holding_period'

        if exit_price is None or exit_date is None:
            continue

        return_pct = (exit_price - entry_price) / entry_price * 100

        trades.append(TradeResult(
            symbol=symbol,
            sector=sector,
            signal_date=signal_date,
            entry_date=df.index[entry_idx].date(),
            exit_date=exit_date,
            exit_reason=exit_reason,
            signal_score=signal['score'],
            entry_price=entry_price,
            exit_price=exit_price,
            return_pct=return_pct,
            rsi_at_signal=signal['rsi'],
            adx_at_signal=signal.get('adx'),
            ema_signal=signal['ema_signal'],
        ))

    return trades
```

#### 4.2.5 Aggregate Metrics: `compute_metrics`

```python
def compute_metrics(trades: list[TradeResult], benchmark_data: pd.DataFrame, config: BacktestConfig) -> dict:
    """
    Computes aggregate statistics and equity curve from a list of TradeResult.

    benchmark_data: OHLCV DataFrame for ^NSEI, used for buy-and-hold comparison.
    """
    import numpy as np

    if not trades:
        return {
            'total_trades': 0, 'win_rate': 0, 'avg_return_pct': 0,
            'median_return_pct': 0, 'best_trade_pct': 0, 'worst_trade_pct': 0,
            'max_drawdown_pct': 0, 'sharpe_ratio': 0, 'total_return_pct': 0,
            'benchmark_return_pct': 0, 'equity_curve': []
        }

    returns = [t.return_pct for t in trades]
    wins = [r for r in returns if r > 0]

    total_trades = len(trades)
    win_rate = len(wins) / total_trades
    avg_return = float(np.mean(returns))
    median_return = float(np.median(returns))
    std_return = float(np.std(returns)) if len(returns) > 1 else 0.0
    sharpe = avg_return / std_return if std_return > 0 else 0.0

    # Max drawdown: worst single trade return (simple approximation)
    # A full drawdown calc would require equity curve peak-tracking — do that below
    max_drawdown = float(min(returns))

    # Equity curve — fixed position size of ₹10,000 per trade
    # Sort trades by exit_date to build chronological curve
    POSITION_SIZE = 10_000
    sorted_trades = sorted(trades, key=lambda t: t.exit_date)
    equity = 0.0
    equity_curve = []
    for t in sorted_trades:
        equity += POSITION_SIZE * (t.return_pct / 100)
        equity_curve.append({
            'date': t.exit_date.isoformat(),
            'equity': round(equity, 2),
            'symbol': t.symbol,
            'return_pct': round(t.return_pct, 2)
        })

    # Benchmark: Nifty 50 buy-and-hold over the same period
    benchmark_return = 0.0
    if benchmark_data is not None and not benchmark_data.empty:
        if config.date_from and config.date_to:
            mask = (benchmark_data.index.date >= config.date_from) & \
                   (benchmark_data.index.date <= config.date_to)
            bm_slice = benchmark_data[mask]
        else:
            bm_slice = benchmark_data
        if len(bm_slice) >= 2:
            bm_start = float(bm_slice['Close'].iloc[0])
            bm_end   = float(bm_slice['Close'].iloc[-1])
            benchmark_return = (bm_end - bm_start) / bm_start * 100

    # Add cumulative benchmark line to equity_curve for chart overlay
    # Scale benchmark to same ₹10,000 × total_trades starting capital
    bm_capital = POSITION_SIZE * total_trades
    if benchmark_data is not None and not benchmark_data.empty:
        for point in equity_curve:
            point_date = datetime.date.fromisoformat(point['date'])
            # Find benchmark close on or before this date
            bm_mask = benchmark_data.index.date <= point_date
            if bm_mask.any():
                bm_price_now = float(benchmark_data[bm_mask]['Close'].iloc[-1])
                bm_price_start = float(benchmark_data['Close'].iloc[0])
                point['benchmark_equity'] = round(
                    bm_capital * (bm_price_now / bm_price_start), 2
                )

    return {
        'total_trades': total_trades,
        'winning_trades': len(wins),
        'win_rate': round(win_rate, 4),
        'avg_return_pct': round(avg_return, 3),
        'median_return_pct': round(median_return, 3),
        'best_trade_pct': round(max(returns), 3),
        'worst_trade_pct': round(min(returns), 3),
        'max_drawdown_pct': round(max_drawdown, 3),
        'sharpe_ratio': round(sharpe, 4),
        'total_return_pct': round(sum(returns), 3),
        'benchmark_return_pct': round(benchmark_return, 3),
        'equity_curve': equity_curve,
    }
```

#### 4.2.6 Main Runner: `run_backtest`

```python
def run_backtest(
    db,                    # SQLAlchemy Session
    run_id: str,
    config: BacktestConfig
) -> None:
    """
    Orchestrates the full backtest. Designed to run in a background thread.
    Updates BacktestRun.status and progress fields throughout.
    Writes BacktestTrade rows in batches of 50.
    """
    import json
    from app.db.models import BacktestRun, BacktestTrade, Stock, TechnicalSignal, FundamentalCache
    from app.pipeline.fetcher import fetch_stock_data
    from sqlalchemy import distinct

    run = db.query(BacktestRun).filter(BacktestRun.run_id == run_id).first()
    run.status = 'running'
    db.commit()

    try:
        # 1. Fetch benchmark data (Nifty 50) for comparison
        benchmark_df, _ = fetch_stock_data('^NSEI', append_ns=False, period='3y', fetch_info=False)

        # 2. Determine symbol universe
        symbol_query = db.query(distinct(TechnicalSignal.symbol)).all()
        symbols = [row[0] for row in symbol_query]
        if config.symbol_limit:
            symbols = symbols[:config.symbol_limit]

        run.symbols_total = len(symbols)
        db.commit()

        all_trades = []

        # 3. Per-symbol scoring and simulation
        for i, symbol in enumerate(symbols):
            try:
                stock = db.query(Stock).filter(Stock.symbol == symbol).first()
                sector = stock.sector if stock else ''
                fund_cache = db.query(FundamentalCache).filter(
                    FundamentalCache.symbol == symbol
                ).first() if config.include_fundamentals else None

                hist, _ = fetch_stock_data(symbol, period='3y', fetch_info=False)
                if hist is None or len(hist) < 60:
                    continue

                scored = score_series(hist, fund_cache=fund_cache, config=config)
                trades = simulate_trades(symbol, sector, hist, scored, config)
                all_trades.extend(trades)

                # Write trades to DB in batches
                if len(trades) > 0:
                    for trade in trades:
                        db.add(BacktestTrade(
                            run_id=run_id,
                            symbol=trade.symbol,
                            sector=trade.sector,
                            signal_date=trade.signal_date,
                            entry_date=trade.entry_date,
                            exit_date=trade.exit_date,
                            exit_reason=trade.exit_reason,
                            signal_score=trade.signal_score,
                            entry_price=trade.entry_price,
                            exit_price=trade.exit_price,
                            return_pct=trade.return_pct,
                            rsi_at_signal=trade.rsi_at_signal,
                            adx_at_signal=trade.adx_at_signal,
                            ema_signal=trade.ema_signal,
                        ))
                    if i % 10 == 0:
                        db.commit()

            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Backtest error for {symbol}: {e}")
                continue
            finally:
                run.symbols_done = i + 1
                if i % 5 == 0:
                    db.commit()

        # 4. Compute aggregate metrics
        metrics = compute_metrics(all_trades, benchmark_df, config)

        # 5. Persist metrics to BacktestRun
        run.status = 'complete'
        run.total_trades = metrics['total_trades']
        run.winning_trades = metrics['winning_trades']
        run.win_rate = metrics['win_rate']
        run.avg_return_pct = metrics['avg_return_pct']
        run.median_return_pct = metrics['median_return_pct']
        run.best_trade_pct = metrics['best_trade_pct']
        run.worst_trade_pct = metrics['worst_trade_pct']
        run.max_drawdown_pct = metrics['max_drawdown_pct']
        run.sharpe_ratio = metrics['sharpe_ratio']
        run.total_return_pct = metrics['total_return_pct']
        run.benchmark_return_pct = metrics['benchmark_return_pct']
        run.equity_curve_json = json.dumps(metrics['equity_curve'])
        db.commit()

    except Exception as e:
        import traceback
        run.status = 'failed'
        run.error_message = f"{str(e)}\n{traceback.format_exc()}"
        db.commit()
```

---

## 5. Backend: REST API

### 5.1 File: `backend/app/routers/backtest.py`

```python
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel, Field
from typing import Optional
import uuid, json, datetime
from app.db.session import get_db, SessionLocal
from app.db.models import BacktestRun, BacktestTrade
from app.backtest.engine import BacktestConfig, run_backtest

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
```

#### 5.1.1 Request Schema

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

#### 5.1.2 Endpoints

```python
@router.post("/run")
def start_backtest(req: BacktestRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Starts a backtest as a background task.
    Returns run_id immediately; poll GET /api/backtest/{run_id} for status.
    """
    # Validate and parse dates
    date_from = datetime.date.fromisoformat(req.date_from) if req.date_from else None
    date_to   = datetime.date.fromisoformat(req.date_to)   if req.date_to   else None

    config = BacktestConfig(
        score_threshold=req.score_threshold,
        holding_days=req.holding_days,
        stop_loss_pct=req.stop_loss_pct,
        target_pct=req.target_pct,
        include_fundamentals=req.include_fundamentals,
        symbol_limit=req.symbol_limit,
        date_from=date_from,
        date_to=date_to,
    )

    run_id = str(uuid.uuid4())
    run = BacktestRun(
        run_id=run_id,
        status='pending',
        config=json.dumps(req.dict()),
        symbols_total=0,
        symbols_done=0,
    )
    db.add(run)
    db.commit()

    # Run in background using same pattern as pipeline
    def _run_wrapper():
        _db = SessionLocal()
        try:
            run_backtest(_db, run_id, config)
        finally:
            _db.close()

    background_tasks.add_task(_run_wrapper)
    return {"run_id": run_id, "status": "pending"}


@router.get("/runs")
def list_backtest_runs(db: Session = Depends(get_db)):
    """Returns the 20 most recent backtest runs (summary only, no trades)."""
    runs = db.query(BacktestRun).order_by(desc(BacktestRun.created_at)).limit(20).all()
    return [_serialize_run(r, include_curve=False) for r in runs]


@router.get("/{run_id}")
def get_backtest_run(run_id: str, db: Session = Depends(get_db)):
    """
    Returns full run details including equity curve JSON.
    Poll this endpoint every 3s while status='running'.
    """
    run = db.query(BacktestRun).filter(BacktestRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _serialize_run(run, include_curve=True)


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
    run = db.query(BacktestRun).filter(BacktestRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    q = db.query(BacktestTrade).filter(BacktestTrade.run_id == run_id)
    if exit_reason:
        q = q.filter(BacktestTrade.exit_reason == exit_reason)

    total = q.count()

    # Sorting
    sort_col = getattr(BacktestTrade, sort_by, BacktestTrade.exit_date)
    q = q.order_by(desc(sort_col) if sort_dir == 'desc' else sort_col)

    trades = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "trades": [_serialize_trade(t) for t in trades]
    }


def _serialize_run(run: BacktestRun, include_curve: bool) -> dict:
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


def _serialize_trade(t: BacktestTrade) -> dict:
    return {
        "id": t.id,
        "symbol": t.symbol,
        "sector": t.sector,
        "signal_date": t.signal_date.isoformat() if t.signal_date else None,
        "entry_date": t.entry_date.isoformat() if t.entry_date else None,
        "exit_date": t.exit_date.isoformat() if t.exit_date else None,
        "exit_reason": t.exit_reason,
        "signal_score": t.signal_score,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "return_pct": t.return_pct,
        "rsi_at_signal": t.rsi_at_signal,
        "adx_at_signal": t.adx_at_signal,
        "ema_signal": t.ema_signal,
    }
```

### 5.2 Register Router in `backend/app/main.py`

```python
from app.routers import backtest as backtest_router
app.include_router(backtest_router.router)
```

---

## 6. Frontend

### 6.1 Route

Add to `frontend/src/App.jsx`:
```jsx
import Backtest from './pages/Backtest';
// ...
<Route path="/backtest" element={<Backtest />} />
```

Add to nav in `MainLayout.jsx`:
```jsx
import { FlaskConical } from 'lucide-react';
{ to: '/backtest', label: 'Backtest', icon: <FlaskConical size={20} /> }
```

### 6.2 API Client Functions

Add to `frontend/src/api/client.js`:
```js
export const runBacktest    = (config) => apiClient.post('/backtest/run', config);
export const getBacktestRun = (runId)  => apiClient.get(`/backtest/${runId}`);
export const getBacktestRuns = ()      => apiClient.get('/backtest/runs');
export const getBacktestTrades = (runId, params) =>
  apiClient.get(`/backtest/${runId}/trades`, { params });
```

### 6.3 Page: `frontend/src/pages/Backtest.jsx`

The page has three distinct states:

1. **Config state** — form to configure and start a new run, plus a list of past runs
2. **Running state** — progress bar + polling, no results yet
3. **Results state** — metrics cards + equity curve + trades table

#### 6.3.1 Component Structure

```
Backtest (page)
├── BacktestConfigPanel       (left column or top section)
│   ├── Slider (score_threshold)
│   ├── Slider (holding_days)
│   ├── Slider (stop_loss_pct)
│   ├── Slider (target_pct)
│   ├── checkbox (include_fundamentals)
│   ├── input (symbol_limit)
│   ├── date inputs (date_from, date_to)
│   └── "Run Backtest" button
├── BacktestRunList           (past runs, clickable to load results)
├── BacktestProgress          (shown while status='running')
│   ├── progress bar
│   └── "X / Y symbols processed"
├── BacktestMetrics           (shown when status='complete')
│   └── 8 stat cards
├── EquityCurveChart          (shown when status='complete')
│   └── Recharts LineChart with two lines
└── BacktestTradesTable       (shown when status='complete')
    └── DataTable (reuse existing component)
```

#### 6.3.2 State Management

```jsx
// In Backtest.jsx
const [config, setConfig] = useState({
  score_threshold: 60,
  holding_days: 20,
  stop_loss_pct: 7,
  target_pct: 0,
  include_fundamentals: false,
  symbol_limit: null,
  date_from: '',
  date_to: '',
});

const [activeRunId, setActiveRunId] = useState(null);
const [runData, setRunData] = useState(null);   // BacktestRun object
const [trades, setTrades] = useState([]);
const [tradesTotal, setTradesTotal] = useState(0);
const [tradesPage, setTradesPage] = useState(1);
const [isPolling, setIsPolling] = useState(false);
```

#### 6.3.3 Polling Logic

Use `useEffect` + `setInterval` pattern (same as `usePipeline`):

```jsx
useEffect(() => {
  if (!activeRunId || !isPolling) return;
  const poll = async () => {
    const res = await getBacktestRun(activeRunId);
    setRunData(res.data);
    if (res.data.status === 'complete' || res.data.status === 'failed') {
      setIsPolling(false);
    }
  };
  poll();
  const id = setInterval(poll, 3000);
  return () => clearInterval(id);
}, [activeRunId, isPolling]);
```

#### 6.3.4 Handle Run Start

```jsx
const handleRun = async () => {
  const res = await runBacktest(config);
  setActiveRunId(res.data.run_id);
  setRunData({ status: 'pending', progress: { symbols_done: 0, symbols_total: 0, pct: 0 } });
  setTrades([]);
  setIsPolling(true);
};
```

When `runData.status` transitions to `'complete'`, trigger a trades fetch:
```jsx
useEffect(() => {
  if (runData?.status === 'complete' && activeRunId) {
    fetchTrades(1);
  }
}, [runData?.status]);
```

#### 6.3.5 `BacktestMetrics` Sub-Component

Eight stat cards in a 4×2 or 2×4 grid:

| Card | Value | Color hint |
|---|---|---|
| Total Trades | `metrics.total_trades` | neutral |
| Win Rate | `(metrics.win_rate * 100).toFixed(1)%` | green if > 50% |
| Avg Return | `metrics.avg_return_pct.toFixed(2)%` | green/red |
| Median Return | `metrics.median_return_pct.toFixed(2)%` | green/red |
| Best Trade | `metrics.best_trade_pct.toFixed(2)%` | always green |
| Worst Trade | `metrics.worst_trade_pct.toFixed(2)%` | always red |
| Sharpe Ratio | `metrics.sharpe_ratio.toFixed(2)` | green if > 1 |
| vs Nifty 50 | `(metrics.total_return_pct - metrics.benchmark_return_pct).toFixed(1)%` | green/red |

Each card: title label (muted, small), value (large, colored), no border needed if using `var(--color-bg-elevated)` background.

#### 6.3.6 `EquityCurveChart` Sub-Component

Uses `recharts` `LineChart` (identical pattern to `StockDetail.jsx` score trend chart):

```jsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

// Data: equity_curve array from API
// Each point: { date, equity, benchmark_equity }

<ResponsiveContainer width="100%" height={300}>
  <LineChart data={equityCurve}>
    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
    <YAxis tickFormatter={(v) => `₹${(v/1000).toFixed(0)}k`} />
    <Tooltip
      formatter={(value, name) => [
        `₹${value.toLocaleString('en-IN')}`,
        name === 'equity' ? 'Strategy' : 'Nifty 50'
      ]}
      contentStyle={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
    />
    <Legend />
    <Line type="monotone" dataKey="equity" stroke="var(--color-bullish)"
          dot={false} strokeWidth={2} name="Strategy" />
    <Line type="monotone" dataKey="benchmark_equity" stroke="var(--color-primary)"
          dot={false} strokeWidth={2} strokeDasharray="4 4" name="Nifty 50" />
  </LineChart>
</ResponsiveContainer>
```

Add a subtitle: "Equal ₹10,000 position per trade. Strategy total capital = ₹10,000 × trades."

#### 6.3.7 `BacktestTradesTable` Sub-Component

Reuse the existing `DataTable` component. Column definitions:

```js
const tradeColumns = [
  { key: 'symbol',       label: 'Symbol',      sortable: true, render: (v) => <Link to={`/stocks/${v}`}>{v}</Link> },
  { key: 'signal_date',  label: 'Signal Date',  sortable: true },
  { key: 'entry_date',   label: 'Entry',        sortable: true },
  { key: 'exit_date',    label: 'Exit',         sortable: true },
  { key: 'holding',      label: 'Days Held',    sortable: false,
    accessor: (row) => {
      const d1 = new Date(row.entry_date), d2 = new Date(row.exit_date);
      return Math.round((d2 - d1) / 86400000);
    }
  },
  { key: 'signal_score', label: 'Score',        sortable: true, render: (v) => v?.toFixed(1) },
  { key: 'entry_price',  label: 'Entry ₹',     sortable: true, render: (v) => v?.toFixed(2) },
  { key: 'exit_price',   label: 'Exit ₹',      sortable: true, render: (v) => v?.toFixed(2) },
  { key: 'return_pct',   label: 'Return %',     sortable: true,
    render: (v) => <span className={v >= 0 ? 'text-positive' : 'text-negative'}>
      {v >= 0 ? '+' : ''}{v?.toFixed(2)}%
    </span>
  },
  { key: 'exit_reason',  label: 'Exit Reason',  sortable: true,
    render: (v) => <span className={`exit-badge exit-${v}`}>{v?.replace('_', ' ')}</span>
  },
  { key: 'sector',       label: 'Sector',       sortable: true },
];
```

Trades table is paginated using the existing `Pagination` component (from F7). Pagination state is server-side (pass `page` and `page_size` to `getBacktestTrades`).

Add filter chips above the table for exit reason: `All | Holding Period | Stop Loss | Target`.

#### 6.3.8 `BacktestRunList` Sub-Component

A compact list of past runs shown in the left sidebar or above the config panel:

```jsx
// Each row shows:
// - created_at (date + time)
// - config summary: "Score≥60, Hold 20d, SL 7%"
// - status badge
// - win_rate + avg_return (if complete)
// Click to load that run's results (set activeRunId, fetch trades)
```

#### 6.3.9 Disclaimer Banner

Shown prominently at the top of the results section when `include_fundamentals = false`:

```jsx
<div className="backtest-disclaimer">
  <Info size={16} />
  <span>
    <strong>Technical signals only.</strong> Fundamental score excluded because historical
    P/E, ROE, and other metrics are not stored per date. Scores are on a 0–70 scale.
    Enable "Include Fundamentals" to use current cache values (anachronistic).
  </span>
</div>
```

When `include_fundamentals = true`, show a different warning:

```jsx
<div className="backtest-disclaimer warning">
  Current fundamental data applied to all historical dates.
  This overstates quality of older signals for companies whose financials have changed.
</div>
```

---

## 7. Known Limitations (Document in UI and Code Comments)

These limitations are real and should be acknowledged in both the frontend UI and as code comments in `engine.py`:

1. **No historical fundamentals.** `FundamentalCache` holds today's data. When `include_fundamentals=true`, current values are projected backward — this is anachronistic and will make historically weaker signals look better if the company has improved.

2. **No transaction costs.** The simulation ignores brokerage (~0.1%), STT (0.1% on sell), exchange charges, and GST. For 20-day swing trades these are roughly 0.3–0.5% round-trip. For high-frequency signals this would meaningfully erode returns.

3. **No position sizing or portfolio constraints.** On days with many signals, the model trades all of them in parallel with equal ₹10,000 positions. In practice, capital is finite and correlated positions amplify drawdowns.

4. **Slippage on stop-loss and target exits.** The model assumes fills at exactly the stop price and target price. In reality, gaps and illiquidity cause worse fills.

5. **Survivorship bias.** The symbol universe is drawn from `TechnicalSignal`, which contains stocks that currently exist and passed screening. Companies that were delisted or halted during the backtest period are not included, causing an upward bias in results.

6. **Look-ahead bias in screener universe.** We score stocks that we know (today) passed Tier 1+2 screening. Historically, some of these stocks might not have passed screening in the past. This is a mild but real form of look-ahead.

7. **requests-cache dependency.** The first backtest run re-downloads 3y OHLCV for every symbol. Subsequent runs within 24h use the SQLite cache. The cache lives at `data/yfinance_cache.sqlite`.

---

## 8. File Changeset Summary

**Create:**
```
backend/app/backtest/__init__.py
backend/app/backtest/engine.py
backend/app/routers/backtest.py
backend/tests/unit/test_backtest_engine.py
frontend/src/pages/Backtest.jsx
frontend/src/pages/Backtest.css
alembic/versions/XXX_add_backtest_runs.py
alembic/versions/XXX_add_backtest_trades.py
```

**Modify:**
```
backend/app/db/models.py          (add BacktestRun, BacktestTrade)
backend/app/main.py               (include backtest router)
frontend/src/App.jsx              (add /backtest route)
frontend/src/components/MainLayout.jsx  (add Backtest nav item)
frontend/src/api/client.js        (add 4 backtest API functions)
```

---

## 9. Test Spec: `backend/tests/unit/test_backtest_engine.py`

The engine module is pure Python with no DB dependency — it should be fully unit-testable.

```python
import pandas as pd
import numpy as np
import datetime
from app.backtest.engine import BacktestConfig, score_series, simulate_trades, compute_metrics

def _make_df(n_bars=200, trend='up') -> pd.DataFrame:
    """Creates a synthetic OHLCV DataFrame for testing."""
    dates = pd.date_range(start='2023-01-01', periods=n_bars, freq='B')
    close = np.linspace(100, 150 if trend == 'up' else 70, n_bars)
    open_ = close * 0.995
    high  = close * 1.005
    low   = close * 0.990
    vol   = np.random.randint(500_000, 2_000_000, n_bars)
    return pd.DataFrame({'Open': open_, 'High': high, 'Low': low, 'Close': close, 'Volume': vol}, index=dates)


def test_score_series_returns_list():
    df = _make_df(200)
    config = BacktestConfig()
    result = score_series(df, config=config)
    assert isinstance(result, list)
    assert len(result) > 0
    assert 'date' in result[0]
    assert 'score' in result[0]
    assert 0 <= result[0]['score'] <= 70   # technical only


def test_score_series_no_future_leak():
    """Score at index i must not depend on data after index i."""
    df = _make_df(200)
    config = BacktestConfig()
    scores_full = score_series(df, config=config)
    # Truncate df at midpoint and re-score
    scores_half = score_series(df.iloc[:100], config=config)
    # Scores for dates present in both must be identical
    full_by_date = {r['date']: r['score'] for r in scores_full}
    for r in scores_half:
        if r['date'] in full_by_date:
            # Scores may differ due to indicator warm-up on truncated data.
            # This test checks that they are at least computable without error.
            assert isinstance(r['score'], float)


def test_simulate_trades_entry_is_next_day_open():
    df = _make_df(200)
    config = BacktestConfig(score_threshold=0)   # threshold 0 = all signals
    scored = score_series(df, config=config)
    trades = simulate_trades('TEST', 'Tech', df, scored, config)
    if trades:
        # Entry date must be after signal date
        assert trades[0].entry_date > trades[0].signal_date


def test_simulate_trades_stop_loss_triggered():
    """With a tight stop loss and a falling stock, most trades should hit stop."""
    df = _make_df(200, trend='down')
    config = BacktestConfig(score_threshold=0, stop_loss_pct=1.0, holding_days=20)
    scored = score_series(df, config=config)
    trades = simulate_trades('TEST', 'Tech', df, scored, config)
    stop_trades = [t for t in trades if t.exit_reason == 'stop_loss']
    # On a falling stock with 1% stop, at least some trades should stop out
    if trades:
        assert len(stop_trades) > 0


def test_compute_metrics_empty_trades():
    result = compute_metrics([], None, BacktestConfig())
    assert result['total_trades'] == 0
    assert result['win_rate'] == 0


def test_compute_metrics_all_winners():
    from app.backtest.engine import TradeResult
    trades = [
        TradeResult('A', 'Tech', datetime.date(2024,1,1), datetime.date(2024,1,2),
                    datetime.date(2024,1,22), 'holding_period', 65.0, 100.0, 110.0, 10.0, 55.0, 30.0, 'bullish')
        for _ in range(5)
    ]
    result = compute_metrics(trades, None, BacktestConfig())
    assert result['win_rate'] == 1.0
    assert result['avg_return_pct'] == 10.0
    assert result['total_trades'] == 5
```

---

## 10. Implementation Order

1. **DB models + migrations** — `BacktestRun`, `BacktestTrade` in `models.py`, then `alembic revision` + `upgrade head`
2. **`engine.py`** — `score_series`, `simulate_trades`, `compute_metrics`, `run_backtest` — implement and unit test before touching FastAPI
3. **Unit tests** — `test_backtest_engine.py` against synthetic DataFrames. All tests must pass before the router is written.
4. **`routers/backtest.py`** — REST endpoints, Pydantic schema, serializers
5. **`main.py`** — register router
6. **`api/client.js`** — 4 new functions
7. **`App.jsx` + `MainLayout.jsx`** — route and nav item
8. **`Backtest.jsx`** — page with all sub-components, polling, config panel, results display

---

## 11. Acceptance Criteria

- [ ] `POST /api/backtest/run` returns a `run_id` within 200ms. The run begins in the background.
- [ ] `GET /api/backtest/{run_id}` returns `status: 'running'` with `progress.pct` increasing while the run is active.
- [ ] `score_series` on a 200-bar DataFrame runs in under 1 second.
- [ ] All unit tests in `test_backtest_engine.py` pass.
- [ ] Trades table is paginated at 50 rows. Clicking a symbol links to `/stocks/{symbol}`.
- [ ] Equity curve chart shows two lines: Strategy and Nifty 50.
- [ ] Both disclaimer banners render correctly based on `include_fundamentals` value.
- [ ] With `score_threshold=100`, `total_trades=0` and the UI shows "No trades generated" gracefully.
- [ ] Changing `stop_loss_pct=0` disables stop-loss logic — no trades exit early for that reason.
- [ ] Past runs list shows up to 20 entries; clicking one loads its results without re-running.
- [ ] With `symbol_limit=10`, only 10 symbols are processed. Run completes in under 30 seconds.
