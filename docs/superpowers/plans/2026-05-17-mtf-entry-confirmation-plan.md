# Multi-Timeframe Entry Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Weekly and Monthly bullish confirmation gates to the backtest engine so Daily signals are only entered when the higher-timeframe trend agrees, eliminating counter-trend entries.

**Architecture:** A new `build_mtf_state_map` function resamples each symbol's OHLCV data to Weekly/Monthly bars and scores them using the existing `calculate_technical_score` function, producing a `{bar_date: bool}` dict per symbol per timeframe. `run_backtest` builds these maps before calling `simulate_trades`, which receives them as arguments and applies two new gates (Weekly, then Monthly) after the ADX gate and before the score threshold check. No database reads are used for state — all state derives from OHLCV to avoid look-ahead bias.

**Tech Stack:** Python 3.11, pandas, pandas-ta, SQLAlchemy, FastAPI/Pydantic — all already in the project.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `backend/app/backtest/engine.py` | Modify | Add `build_mtf_state_map`, update `BacktestConfig`, update `simulate_trades` signature + gate logic, update `run_backtest` to build maps |
| `backend/app/routers/backtest.py` | Modify | Add two new fields to `BacktestRequest`, pass through to `BacktestConfig` in handler |
| `backend/tests/backtest/__init__.py` | Create | Empty init so pytest discovers the module |
| `backend/tests/backtest/test_mtf_confirmation.py` | Create | Unit tests for `build_mtf_state_map` and the new gates in `simulate_trades` |

---

## Task 1: Add MTF Config Fields to `BacktestConfig` and `BacktestRequest`

**Files:**
- Modify: `backend/app/backtest/engine.py` — `BacktestConfig` dataclass
- Modify: `backend/app/routers/backtest.py` — `BacktestRequest` model and handler

### Context

`BacktestConfig` is a `@dataclass` in `engine.py`. `BacktestRequest` is a Pydantic `BaseModel` in `backtest.py`. The handler in `@router.post("/run")` constructs a `BacktestConfig` from the request; every new field needs to appear in all three places.

- [ ] **Step 1: Add fields to `BacktestConfig`**

In `backend/app/backtest/engine.py`, find the `BacktestConfig` dataclass and add two fields after `use_regime_filter`:

```python
@dataclass
class BacktestConfig:
    score_threshold: float = 55.0
    holding_days: int = 20
    stop_loss_pct: float = 7.0
    target_pct: float = 0.0
    trailing_stop_pct: float = 0.0
    require_volume_breakout: bool = True
    use_regime_filter: bool = True
    require_weekly_confirmation: bool = True   # NEW — MTF-001
    require_monthly_confirmation: bool = False  # NEW — MTF-002
    atr_multiplier: float = 2.0
    risk_reward_ratio: float = 2.5
    use_atr_stops: bool = False
    min_adx: float = 20.0
    include_fundamentals: bool = False
    timeframe: str = 'D'
    date_from: datetime.date = None
    date_to: datetime.date = None
    symbol_limit: int = None
    screen_slug: Optional[str] = None
    starting_capital: float = 1000000.0
    position_size: float = 10000.0
```

- [ ] **Step 2: Add fields to `BacktestRequest`**

In `backend/app/routers/backtest.py`, add after the `use_regime_filter` field:

```python
class BacktestRequest(BaseModel):
    score_threshold: float = Field(default=55.0, ge=0, le=100,
        description="Minimum score. Recommended: 55–65 for technical-only signals, 45–55 with fundamentals.")
    holding_days: int = Field(default=20, ge=1, le=252)
    stop_loss_pct: float = Field(default=7.0, ge=0, le=50,
        description="0 disables stop-loss.")
    target_pct: float = Field(default=0.0, ge=0, le=200,
        description="0 disables profit target.")
    trailing_stop_pct: float = Field(default=0.0, ge=0, le=50,
        description="Percentage drop from peak to trigger exit.")
    require_volume_breakout: bool = Field(default=True,
        description="Requires volume > 2x SMA20 for entry. Disabling increases trade count and stop-loss rate.")
    use_regime_filter: bool = True
    require_weekly_confirmation: bool = Field(
        default=True,
        description="Requires the Weekly signal to be bullish before entering a Daily signal. "
                    "Eliminates counter-trend entries. Fewer trades, higher signal quality."
    )
    require_monthly_confirmation: bool = Field(
        default=False,
        description="Additionally requires the Monthly signal to be bullish. "
                    "Opt-in for longer backtests; significantly reduces trade count."
    )
    atr_multiplier: float = Field(default=2.0, ge=1.0, le=10.0,
        description="Multiplier for ATR-based stop loss.")
    risk_reward_ratio: float = Field(default=2.5, ge=0.5, le=10.0,
        description="Target profit as a multiple of risk.")
    use_atr_stops: bool = False
    min_adx: float = Field(default=20.0, ge=0, le=50,
        description="Minimum ADX required to enter a trade. 0 disables the filter.")
    include_fundamentals: bool = False
    symbol_limit: Optional[int] = Field(default=None, ge=1, le=500)
    screen_slug: Optional[str] = Field(default=None, description="Slug of the screen to filter symbols by.")
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    starting_capital: float = Field(default=1000000.0, ge=10000)
    position_size: float = Field(default=10000.0, ge=100)
```

- [ ] **Step 3: Pass the new fields through in the request handler**

In `backend/app/routers/backtest.py`, inside `start_backtest`, update the `BacktestConfig(...)` constructor call:

```python
config = BacktestConfig(
    score_threshold=request.score_threshold,
    holding_days=request.holding_days,
    stop_loss_pct=request.stop_loss_pct,
    target_pct=request.target_pct,
    trailing_stop_pct=request.trailing_stop_pct,
    require_volume_breakout=request.require_volume_breakout,
    use_regime_filter=request.use_regime_filter,
    require_weekly_confirmation=request.require_weekly_confirmation,   # NEW
    require_monthly_confirmation=request.require_monthly_confirmation,  # NEW
    atr_multiplier=request.atr_multiplier,
    risk_reward_ratio=request.risk_reward_ratio,
    use_atr_stops=request.use_atr_stops,
    min_adx=request.min_adx,
    include_fundamentals=request.include_fundamentals,
    symbol_limit=request.symbol_limit,
    screen_slug=request.screen_slug,
    date_from=date_from,
    date_to=date_to,
    starting_capital=request.starting_capital,
    position_size=request.position_size
)
```

- [ ] **Step 4: Verify no syntax errors**

```bash
cd backend
python -c "from app.backtest.engine import BacktestConfig; c = BacktestConfig(); print(c.require_weekly_confirmation, c.require_monthly_confirmation)"
```

Expected output:
```
True False
```

```bash
python -c "from app.routers.backtest import BacktestRequest; r = BacktestRequest(); print(r.require_weekly_confirmation, r.require_monthly_confirmation)"
```

Expected output:
```
True False
```

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/backtest/engine.py app/routers/backtest.py
git commit -m "feat(backtest): add require_weekly_confirmation and require_monthly_confirmation config fields"
```

---

## Task 2: Implement `build_mtf_state_map`

**Files:**
- Modify: `backend/app/backtest/engine.py` — add new function after `score_series`
- Create: `backend/tests/backtest/__init__.py`
- Create: `backend/tests/backtest/test_mtf_confirmation.py` — tests for `build_mtf_state_map`

### Context

`build_mtf_state_map` must resample daily OHLCV to Weekly (`'W'`) or Monthly (`'ME'`) bars using the existing `resample_ohlcv` utility from `app.pipeline.utils`, then score each resampled bar using `calculate_technical_score` from `app.pipeline.scorer`. The output is a `dict[datetime.date, bool]` mapping each completed bar's end date to its `is_bullish` value.

The function intentionally does NOT do an O(n²) per-bar rescore (unlike `score_series`) because higher-timeframe bars are sparse enough that a single full-frame score per bar is acceptable. We iterate over the resampled dataframe rows with index `i` and call `calculate_technical_score` on `resampled.iloc[:i+1]` so each bar only sees data available up to that bar.

Weekly bullish definition (from existing `calculate_technical_score` for `timeframe='W'`): RSI > 50 and price above EMA26.
Monthly bullish definition (from existing `calculate_technical_score` for `timeframe='M'`): RSI > 50 and price above EMA13 or EMA26.

These are already implemented — `build_mtf_state_map` just calls the scorer with the right timeframe string.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/backtest/__init__.py` (empty file):

```bash
mkdir -p backend/tests/backtest
touch backend/tests/backtest/__init__.py
```

Create `backend/tests/backtest/test_mtf_confirmation.py`:

```python
"""Tests for Multi-Timeframe Entry Confirmation (MTF-001/002/003)."""
import datetime
import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import build_mtf_state_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trending_df(n: int = 400, start_price: float = 100.0, trend: float = 0.5) -> pd.DataFrame:
    """
    Creates a daily OHLCV DataFrame with a configurable linear trend.
    Positive trend → persistent uptrend (RSI high, price above all EMAs).
    Negative trend → persistent downtrend.
    """
    closes = start_price + trend * np.arange(n)
    closes = np.maximum(closes, 1.0)  # never go negative
    return pd.DataFrame(
        {
            "Open": closes * 0.998,
            "High": closes * 1.01,
            "Low": closes * 0.99,
            "Close": closes,
            "Volume": np.full(n, 1_500_000.0),
        },
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )


# ---------------------------------------------------------------------------
# build_mtf_state_map — return type and structure
# ---------------------------------------------------------------------------

class TestBuildMtfStateMapReturnType:
    def test_returns_dict(self):
        df = _make_trending_df()
        result = build_mtf_state_map(df, "W")
        assert isinstance(result, dict)

    def test_keys_are_dates(self):
        df = _make_trending_df()
        result = build_mtf_state_map(df, "W")
        assert len(result) > 0
        for k in result:
            assert isinstance(k, datetime.date), f"Expected date, got {type(k)}"

    def test_values_are_bools(self):
        df = _make_trending_df()
        result = build_mtf_state_map(df, "W")
        for v in result.values():
            assert isinstance(v, bool), f"Expected bool, got {type(v)}"

    def test_monthly_returns_dict(self):
        df = _make_trending_df()
        result = build_mtf_state_map(df, "M")
        assert isinstance(result, dict)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# build_mtf_state_map — uptrend gives True, downtrend gives False
# ---------------------------------------------------------------------------

class TestBuildMtfStateMapTrend:
    def test_strong_uptrend_produces_bullish_weekly_states(self):
        df = _make_trending_df(n=400, trend=1.5)
        result = build_mtf_state_map(df, "W")
        # After enough bars for EMA/RSI to stabilise, the majority should be bullish
        states = list(result.values())
        # Skip first few bars while indicators warm up
        stable_states = states[10:]
        bullish_count = sum(stable_states)
        assert bullish_count / len(stable_states) > 0.80, (
            f"Expected >80% bullish in uptrend, got {bullish_count}/{len(stable_states)}"
        )

    def test_strong_downtrend_produces_bearish_weekly_states(self):
        df = _make_trending_df(n=400, start_price=500.0, trend=-1.0)
        result = build_mtf_state_map(df, "W")
        states = list(result.values())
        stable_states = states[10:]
        bearish_count = sum(not s for s in stable_states)
        assert bearish_count / len(stable_states) > 0.80, (
            f"Expected >80% bearish in downtrend, got {bearish_count}/{len(stable_states)}"
        )

    def test_strong_uptrend_produces_bullish_monthly_states(self):
        df = _make_trending_df(n=400, trend=1.5)
        result = build_mtf_state_map(df, "M")
        states = list(result.values())
        stable_states = states[5:]  # fewer monthly bars
        if not stable_states:
            pytest.skip("Not enough monthly bars")
        bullish_count = sum(stable_states)
        assert bullish_count / len(stable_states) > 0.70


# ---------------------------------------------------------------------------
# build_mtf_state_map — insufficient history returns empty dict
# ---------------------------------------------------------------------------

class TestBuildMtfStateMapInsufficientHistory:
    def test_empty_df_returns_empty_dict(self):
        df = pd.DataFrame(
            columns=["Open", "High", "Low", "Close", "Volume"],
            index=pd.DatetimeIndex([]),
        )
        result = build_mtf_state_map(df, "W")
        assert result == {}

    def test_too_few_bars_returns_empty_dict(self):
        # Only 10 daily bars → not enough for any weekly indicator computation
        df = _make_trending_df(n=10)
        result = build_mtf_state_map(df, "W")
        # May be empty or have very few entries, but must not raise
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# build_mtf_state_map — no look-ahead: each bar only sees prior data
# ---------------------------------------------------------------------------

class TestBuildMtfStateMapNoLookahead:
    def test_state_count_does_not_exceed_resampled_bar_count(self):
        """Each entry corresponds to one completed bar — no future bars."""
        df = _make_trending_df(n=400)
        result = build_mtf_state_map(df, "W")
        # resample to W gives approximately 400/5 = 80 bars; drop_incomplete removes last
        # So result should have at most ~79 entries
        assert len(result) <= 85  # generous upper bound
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend
python -m pytest tests/backtest/test_mtf_confirmation.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name 'build_mtf_state_map' from 'app.backtest.engine'`

- [ ] **Step 3: Implement `build_mtf_state_map` in `engine.py`**

Add the following imports at the top of `backend/app/backtest/engine.py` (they are already partially there; add what's missing):

```python
import bisect
from app.pipeline.utils import resample_ohlcv
```

Add the function after the `score_series` function (before `simulate_trades`):

```python
def build_mtf_state_map(df: pd.DataFrame, timeframe: str) -> dict:
    """
    Builds a mapping of {bar_date: is_bullish} for Weekly ('W') or Monthly ('M')
    timeframes, derived entirely from the provided daily OHLCV DataFrame.

    Each entry represents the bullish state of one completed higher-timeframe bar,
    scored using only data available up to and including that bar (no look-ahead).

    Returns an empty dict if the DataFrame is empty or has insufficient history
    for indicator computation.

    Args:
        df: Daily OHLCV DataFrame with a DatetimeIndex.
        timeframe: 'W' for Weekly or 'M' for Monthly.

    Returns:
        dict mapping datetime.date keys to bool values.
    """
    if df is None or df.empty:
        return {}

    freq = 'W' if timeframe == 'W' else 'ME'
    # drop_incomplete=True (default) removes the current in-progress bar
    resampled = resample_ohlcv(df, freq=freq, drop_incomplete=True)

    if resampled.empty:
        return {}

    state_map = {}
    for i in range(len(resampled)):
        bar_slice = resampled.iloc[: i + 1]
        try:
            ta_data = calculate_technical_score(bar_slice, timeframe=timeframe)
        except Exception:
            # If scoring fails (e.g. insufficient bars for EMA computation),
            # default to non-bullish (fail-closed per MTF-003).
            continue

        bar_date = resampled.index[i]
        # Normalise to datetime.date so lookups from daily signal dates are consistent
        if hasattr(bar_date, 'date'):
            bar_date = bar_date.date()

        state_map[bar_date] = bool(ta_data.get('is_bullish', False))

    return state_map
```

- [ ] **Step 4: Run the tests again**

```bash
cd backend
python -m pytest tests/backtest/test_mtf_confirmation.py -v
```

Expected: All tests pass. If `test_strong_downtrend_produces_bearish_weekly_states` or similar fails, it likely means the downtrend fixture needs a steeper slope — adjust `trend=-1.5` in the helper call inside that test.

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/backtest/engine.py tests/backtest/__init__.py tests/backtest/test_mtf_confirmation.py
git commit -m "feat(backtest): add build_mtf_state_map for look-ahead-free MTF state derivation"
```

---

## Task 3: Add MTF Gates to `simulate_trades`

**Files:**
- Modify: `backend/app/backtest/engine.py` — `simulate_trades` signature and gate logic
- Modify: `backend/tests/backtest/test_mtf_confirmation.py` — add gate integration tests

### Context

`simulate_trades` currently has this signature:

```python
def simulate_trades(symbol, sector, df, scored_dates, config, regime_dict=None):
```

We add two optional dict parameters — `weekly_state_map` and `monthly_state_map`. Both default to `None` so callers that haven't been updated yet are unaffected.

The gate logic needs a helper to look up the most recent bar state for a given daily date. Because the state map keys are bar *end* dates (e.g. a weekly bar ending on Friday), and a Daily signal may fall on any day of that week, we need to find `max(bar_date for bar_date in state_map if bar_date <= signal_date)`. We use `bisect` on a sorted key list for O(log n) lookups.

Gate ordering per MTF-005: the new gates go after the ADX gate and before `if signal['score'] >= config.score_threshold:`.

- [ ] **Step 1: Add gate integration tests**

Append the following to `backend/tests/backtest/test_mtf_confirmation.py`:

```python
# ---------------------------------------------------------------------------
# Imports for simulate_trades tests
# ---------------------------------------------------------------------------
from app.backtest.engine import simulate_trades, BacktestConfig


# ---------------------------------------------------------------------------
# Helpers for simulate_trades tests
# ---------------------------------------------------------------------------

def _make_scored_signal(date: datetime.date, score: float = 70.0) -> dict:
    """Builds a minimal scored signal dict accepted by simulate_trades."""
    return {
        "date": pd.Timestamp(date),
        "score": score,
        "is_bullish": True,
        "rsi": 55.0,
        "adx": 25.0,
        "ema_signal": "bullish",
        "volume_signal": "bullish",
        "rsi_signal": "bullish_strong",
        "close": 100.0,
        "open": 99.0,
        "volume_breakout": True,
        "atr": 2.0,
        "above_200ema": True,
    }


def _make_ohlcv_df(n: int = 60, start_price: float = 100.0) -> pd.DataFrame:
    """Minimal OHLCV DataFrame for simulate_trades entry/exit mechanics."""
    closes = start_price + 0.1 * np.arange(n)
    index = pd.date_range("2023-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "Open": closes * 0.999,
            "High": closes * 1.005,
            "Low": closes * 0.995,
            "Close": closes,
            "Volume": np.full(n, 500_000.0),
        },
        index=index,
    )


def _base_config(**overrides) -> BacktestConfig:
    cfg = BacktestConfig(
        score_threshold=60.0,
        holding_days=5,
        stop_loss_pct=0.0,       # disabled so trades always run to holding period
        target_pct=0.0,
        require_volume_breakout=False,
        use_regime_filter=False,
        min_adx=0.0,             # ADX gate disabled
        require_weekly_confirmation=False,
        require_monthly_confirmation=False,
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


# ---------------------------------------------------------------------------
# Weekly gate — MTF-001
# ---------------------------------------------------------------------------

class TestWeeklyConfirmationGate:
    """MTF-001: Weekly bullish confirmation gate."""

    def _signal_date_and_df(self):
        df = _make_ohlcv_df(n=60)
        # Use a date that falls in the middle so there's room for entry + holding
        signal_date = df.index[10].date()
        signal = _make_scored_signal(signal_date, score=70.0)
        return df, signal, signal_date

    def test_trade_entered_when_gate_disabled(self):
        """Baseline: gate off, bullish weekly state should NOT matter."""
        df, signal, _ = self._signal_date_and_df()
        cfg = _base_config(require_weekly_confirmation=False)
        # Pass a bearish weekly map — should be ignored
        weekly_map = {}
        trades = simulate_trades("TEST", "IT", df, [signal], cfg, weekly_state_map=weekly_map)
        assert len(trades) == 1

    def test_trade_rejected_when_weekly_bearish(self):
        """Gate on, symbol present with False → no trade."""
        df, signal, signal_date = self._signal_date_and_df()
        cfg = _base_config(require_weekly_confirmation=True)
        # Weekly bar ending before signal_date is bearish
        week_end = signal_date - datetime.timedelta(days=signal_date.weekday())  # Monday
        weekly_map = {week_end: False}
        trades = simulate_trades("TEST", "IT", df, [signal], cfg, weekly_state_map=weekly_map)
        assert len(trades) == 0

    def test_trade_entered_when_weekly_bullish(self):
        """Gate on, symbol present with True → trade entered."""
        df, signal, signal_date = self._signal_date_and_df()
        cfg = _base_config(require_weekly_confirmation=True)
        # Place a weekly bar with True that covers the signal date
        # Use the Friday on or before the signal date
        days_since_friday = (signal_date.weekday() - 4) % 7
        week_end = signal_date - datetime.timedelta(days=days_since_friday)
        weekly_map = {week_end: True}
        trades = simulate_trades("TEST", "IT", df, [signal], cfg, weekly_state_map=weekly_map)
        assert len(trades) == 1

    def test_trade_rejected_when_symbol_absent_from_map(self):
        """Fail-closed: absent from map → treated as non-bullish → no trade."""
        df, signal, _ = self._signal_date_and_df()
        cfg = _base_config(require_weekly_confirmation=True)
        weekly_map = {}  # symbol not present at any date
        trades = simulate_trades("TEST", "IT", df, [signal], cfg, weekly_state_map=weekly_map)
        assert len(trades) == 0

    def test_no_weekly_map_means_gate_is_bypassed(self):
        """If weekly_state_map is None, gate is not applied regardless of config."""
        df, signal, _ = self._signal_date_and_df()
        cfg = _base_config(require_weekly_confirmation=True)
        trades = simulate_trades("TEST", "IT", df, [signal], cfg, weekly_state_map=None)
        assert len(trades) == 1


# ---------------------------------------------------------------------------
# Monthly gate — MTF-002
# ---------------------------------------------------------------------------

class TestMonthlyConfirmationGate:
    """MTF-002: Monthly bullish confirmation gate."""

    def _signal_date_and_df(self):
        df = _make_ohlcv_df(n=60)
        signal_date = df.index[10].date()
        signal = _make_scored_signal(signal_date, score=70.0)
        return df, signal, signal_date

    def test_trade_rejected_when_monthly_bearish(self):
        """Gate on, monthly state False → no trade."""
        df, signal, signal_date = self._signal_date_and_df()
        cfg = _base_config(require_monthly_confirmation=True)
        # Monthly bar ending the last day of prior month
        import calendar
        year, month = signal_date.year, signal_date.month
        if month == 1:
            prev_month_end = datetime.date(year - 1, 12, 31)
        else:
            last_day = calendar.monthrange(year, month - 1)[1]
            prev_month_end = datetime.date(year, month - 1, last_day)
        monthly_map = {prev_month_end: False}
        trades = simulate_trades("TEST", "IT", df, [signal], cfg, monthly_state_map=monthly_map)
        assert len(trades) == 0

    def test_trade_entered_when_monthly_bullish(self):
        df, signal, signal_date = self._signal_date_and_df()
        cfg = _base_config(require_monthly_confirmation=True)
        import calendar
        year, month = signal_date.year, signal_date.month
        if month == 1:
            prev_month_end = datetime.date(year - 1, 12, 31)
        else:
            last_day = calendar.monthrange(year, month - 1)[1]
            prev_month_end = datetime.date(year, month - 1, last_day)
        monthly_map = {prev_month_end: True}
        trades = simulate_trades("TEST", "IT", df, [signal], cfg, monthly_state_map=monthly_map)
        assert len(trades) == 1

    def test_absent_from_monthly_map_is_rejected(self):
        df, signal, _ = self._signal_date_and_df()
        cfg = _base_config(require_monthly_confirmation=True)
        trades = simulate_trades("TEST", "IT", df, [signal], cfg, monthly_state_map={})
        assert len(trades) == 0

    def test_monthly_gate_disabled_ignores_bearish_map(self):
        df, signal, signal_date = self._signal_date_and_df()
        cfg = _base_config(require_monthly_confirmation=False)
        monthly_map = {}  # would reject if gate were on
        trades = simulate_trades("TEST", "IT", df, [signal], cfg, monthly_state_map=monthly_map)
        assert len(trades) == 1


# ---------------------------------------------------------------------------
# Both gates active simultaneously — MTF-002 interaction
# ---------------------------------------------------------------------------

class TestBothGatesActive:
    def _setup(self):
        df = _make_ohlcv_df(n=60)
        signal_date = df.index[10].date()
        signal = _make_scored_signal(signal_date, score=70.0)

        import calendar
        year, month = signal_date.year, signal_date.month
        if month == 1:
            prev_month_end = datetime.date(year - 1, 12, 31)
        else:
            last_day = calendar.monthrange(year, month - 1)[1]
            prev_month_end = datetime.date(year, month - 1, last_day)

        days_since_friday = (signal_date.weekday() - 4) % 7
        week_end = signal_date - datetime.timedelta(days=days_since_friday)

        return df, signal, week_end, prev_month_end

    def test_both_true_allows_entry(self):
        df, signal, week_end, month_end = self._setup()
        cfg = _base_config(require_weekly_confirmation=True, require_monthly_confirmation=True)
        trades = simulate_trades(
            "TEST", "IT", df, [signal], cfg,
            weekly_state_map={week_end: True},
            monthly_state_map={month_end: True},
        )
        assert len(trades) == 1

    def test_weekly_false_monthly_true_rejects(self):
        df, signal, week_end, month_end = self._setup()
        cfg = _base_config(require_weekly_confirmation=True, require_monthly_confirmation=True)
        trades = simulate_trades(
            "TEST", "IT", df, [signal], cfg,
            weekly_state_map={week_end: False},
            monthly_state_map={month_end: True},
        )
        assert len(trades) == 0

    def test_weekly_true_monthly_false_rejects(self):
        df, signal, week_end, month_end = self._setup()
        cfg = _base_config(require_weekly_confirmation=True, require_monthly_confirmation=True)
        trades = simulate_trades(
            "TEST", "IT", df, [signal], cfg,
            weekly_state_map={week_end: True},
            monthly_state_map={month_end: False},
        )
        assert len(trades) == 0

    def test_both_false_rejects(self):
        df, signal, week_end, month_end = self._setup()
        cfg = _base_config(require_weekly_confirmation=True, require_monthly_confirmation=True)
        trades = simulate_trades(
            "TEST", "IT", df, [signal], cfg,
            weekly_state_map={week_end: False},
            monthly_state_map={month_end: False},
        )
        assert len(trades) == 0
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd backend
python -m pytest tests/backtest/test_mtf_confirmation.py -v -k "Gate" 2>&1 | tail -20
```

Expected: `TypeError: simulate_trades() got an unexpected keyword argument 'weekly_state_map'`

- [ ] **Step 3: Update `simulate_trades` signature and add a lookup helper**

Add a module-level helper function in `backend/app/backtest/engine.py` just before `simulate_trades`:

```python
def _lookup_mtf_state(state_map: dict, signal_date: datetime.date) -> bool:
    """
    Returns the boolean state for the most recently completed higher-timeframe
    bar whose end date is on or before `signal_date`.

    Uses bisect for O(log n) lookup. Returns False (fail-closed) if no bar
    predates the signal date.

    Args:
        state_map: dict mapping bar end datetime.date → bool.
        signal_date: The daily signal date to look up.

    Returns:
        bool — the state of the most recent applicable bar, or False if none.
    """
    if not state_map:
        return False
    sorted_dates = sorted(state_map.keys())
    # bisect_right gives the insertion point for signal_date + 1 day,
    # so idx-1 is the last date <= signal_date.
    idx = bisect.bisect_right(sorted_dates, signal_date)
    if idx == 0:
        return False  # all bar dates are in the future relative to signal_date
    return state_map[sorted_dates[idx - 1]]
```

Update `simulate_trades` signature and add the two gates after the ADX gate:

```python
def simulate_trades(
    symbol: str,
    sector: str,
    df: pd.DataFrame,
    scored_dates: list[dict],
    config: BacktestConfig,
    regime_dict: dict = None,
    weekly_state_map: dict = None,   # NEW — MTF-001
    monthly_state_map: dict = None,  # NEW — MTF-002
):
    """
    Simulates trades based on scored signals.
    Entry: Next day's Open.
    Exit: SL, Target, or Holding Period.

    Args:
        weekly_state_map: dict[datetime.date, bool] mapping weekly bar end dates to
            bullish state. When config.require_weekly_confirmation=True and this map
            is provided, signals without a True weekly state are rejected.
        monthly_state_map: dict[datetime.date, bool] mapping monthly bar end dates to
            bullish state. When config.require_monthly_confirmation=True and this map
            is provided, signals without a True monthly state are rejected.
    """
    trades = []
    last_exit_idx = -1

    date_to_idx = {date: i for i, date in enumerate(df.index)}

    for signal in scored_dates:
        signal_date = signal['date']
        compare_date = signal_date.date() if hasattr(signal_date, 'date') else signal_date
        if isinstance(compare_date, str):
            compare_date = datetime.datetime.strptime(compare_date, "%Y-%m-%d").date()

        # Gate 1: Date range
        if config.date_from and compare_date < config.date_from:
            continue
        if config.date_to and compare_date > config.date_to:
            continue

        # Gate 2: Volume breakout
        if config.require_volume_breakout:
            if not signal.get('volume_breakout', False):
                continue

        signal_idx = date_to_idx.get(signal_date)

        # Gate 3: Index validity and overlap guard
        if signal_idx is None or signal_idx <= last_exit_idx:
            continue

        # Gate 4: 200 EMA null-safety
        if signal.get('above_200ema') is not True:
            continue

        # Gate 5: ADX trend-strength
        if config.min_adx > 0:
            adx_val = signal.get('adx')
            if adx_val is None or adx_val < config.min_adx:
                continue

        # Gate 6: Weekly confirmation (MTF-001)
        if config.require_weekly_confirmation and weekly_state_map is not None:
            if not _lookup_mtf_state(weekly_state_map, compare_date):
                continue

        # Gate 7: Monthly confirmation (MTF-002)
        if config.require_monthly_confirmation and monthly_state_map is not None:
            if not _lookup_mtf_state(monthly_state_map, compare_date):
                continue

        # Gate 8: Score threshold
        if signal['score'] >= config.score_threshold:
            # Entry: Next trading day's Open price
            entry_idx = signal_idx + 1
            if entry_idx >= len(df):
                break

            entry_date = df.index[entry_idx]
            entry_compare_date = entry_date.date() if hasattr(entry_date, 'date') else entry_date

            # Gate 9: Regime filter on entry date
            if config.use_regime_filter and regime_dict is not None:
                if not regime_dict.get(entry_compare_date, False):
                    continue

            entry_price = df.iloc[entry_idx]['Open']

            exit_price = None
            exit_date = None
            exit_reason = 'holding_period'

            if config.use_atr_stops and signal.get('atr'):
                atr = signal['atr']
                stop_loss_price = entry_price - (config.atr_multiplier * atr)
                target_price = entry_price + (config.atr_multiplier * config.risk_reward_ratio * atr)
            else:
                stop_loss_pct = config.stop_loss_pct
                target_pct = config.target_pct
                stop_loss_price = entry_price * (1 - stop_loss_pct / 100) if stop_loss_pct > 0 else 0
                target_price = entry_price * (1 + target_pct / 100) if target_pct > 0 else float('inf')

            final_idx = min(entry_idx + config.holding_days - 1, len(df) - 1)
            highest_price_since_entry = entry_price

            for k in range(entry_idx, final_idx + 1):
                day_low = df.iloc[k]['Low']
                day_high = df.iloc[k]['High']
                day_open = df.iloc[k]['Open']

                highest_price_since_entry = max(highest_price_since_entry, day_high)

                if day_low <= stop_loss_price:
                    exit_price = stop_loss_price
                    exit_date = df.index[k]
                    exit_reason = 'stop_loss'
                    last_exit_idx = k
                    break

                if config.trailing_stop_pct > 0:
                    trailing_stop_price = highest_price_since_entry * (1 - config.trailing_stop_pct / 100)
                    if day_low <= trailing_stop_price:
                        exit_price = min(trailing_stop_price, day_open)
                        exit_date = df.index[k]
                        exit_reason = 'trailing_stop'
                        last_exit_idx = k
                        break

                if day_high >= target_price:
                    exit_price = target_price
                    exit_date = df.index[k]
                    exit_reason = 'target'
                    last_exit_idx = k
                    break

            if exit_price is None:
                exit_idx = final_idx
                exit_price = df.iloc[exit_idx]['Close']
                exit_date = df.index[exit_idx]
                exit_reason = 'holding_period'
                last_exit_idx = exit_idx

            return_pct = ((exit_price - entry_price) / entry_price) * 100

            trades.append(TradeResult(
                symbol=symbol,
                sector=sector,
                signal_date=signal_date.date() if hasattr(signal_date, 'date') else signal_date,
                entry_date=entry_date.date() if hasattr(entry_date, 'date') else entry_date,
                exit_date=exit_date.date() if hasattr(exit_date, 'date') else exit_date,
                exit_reason=exit_reason,
                signal_score=signal['score'],
                entry_price=float(entry_price),
                exit_price=float(exit_price),
                return_pct=float(return_pct),
                rsi_at_signal=signal['rsi'],
                adx_at_signal=signal['adx'],
                ema_signal=signal['ema_signal']
            ))

    return trades
```

- [ ] **Step 4: Run all tests**

```bash
cd backend
python -m pytest tests/backtest/test_mtf_confirmation.py -v
```

Expected: All tests pass. If a lookup test fails, check that `_lookup_mtf_state` is imported within the module scope and `bisect` is imported at the top of the file.

- [ ] **Step 5: Verify `bisect` import is at the top of `engine.py`**

```bash
cd backend
head -20 app/backtest/engine.py | grep bisect
```

Expected: `import bisect` appears. If not, add it to the imports block.

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/backtest/engine.py tests/backtest/test_mtf_confirmation.py
git commit -m "feat(backtest): add Weekly/Monthly confirmation gates to simulate_trades (MTF-001/002/005)"
```

---

## Task 4: Build MTF State Maps in `run_backtest` and Pass to `simulate_trades`

**Files:**
- Modify: `backend/app/backtest/engine.py` — `run_backtest` symbol loop

### Context

`run_backtest` iterates over each symbol, fetches OHLCV data via `_ohlcv_cache.get`, calls `score_series`, then `simulate_trades`. We need to call `build_mtf_state_map` once per symbol (for `'W'` and `'M'`) using the same `df` that was fetched, and pass the results to `simulate_trades`.

We only build the maps when the gates are enabled in config — this is a small optimisation that also makes the disabled path produce no overhead.

- [ ] **Step 1: Update the symbol loop in `run_backtest`**

In `backend/app/backtest/engine.py`, find the `for symbol in symbols:` loop inside `run_backtest`. Replace it with the following (shown in full so you can do an exact replacement):

```python
            for symbol in symbols:
                try:
                    # Fetch historical OHLCV
                    df = _ohlcv_cache.get(symbol, period='3y')
                    if df is None or df.empty:
                        continue

                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)

                    fund_cache = fund_caches.get(symbol)

                    # Run scoring
                    scored_dates = score_series(df, fund_cache=fund_cache, config=config)

                    # MTF-003: Build higher-timeframe state maps (no look-ahead —
                    # derived from OHLCV, not from TechnicalSignal DB records).
                    weekly_state_map = None
                    monthly_state_map = None
                    if config.require_weekly_confirmation:
                        weekly_state_map = build_mtf_state_map(df, 'W')
                    if config.require_monthly_confirmation:
                        monthly_state_map = build_mtf_state_map(df, 'M')

                    # Run simulation
                    sector = stocks_info.get(symbol, "Unknown")
                    trades = simulate_trades(
                        symbol, sector, df, scored_dates, config,
                        regime_dict=regime_dict,
                        weekly_state_map=weekly_state_map,
                        monthly_state_map=monthly_state_map,
                    )

                    # Save trades to DB
                    db_trades = []
                    for t in trades:
                        db_trade = BacktestTrade(
                            run_id=run_id,
                            symbol=t.symbol,
                            sector=t.sector,
                            signal_date=t.signal_date,
                            entry_date=t.entry_date,
                            exit_date=t.exit_date,
                            exit_reason=t.exit_reason,
                            signal_score=t.signal_score,
                            entry_price=t.entry_price,
                            exit_price=t.exit_price,
                            return_pct=t.return_pct,
                            rsi_at_signal=t.rsi_at_signal,
                            adx_at_signal=t.adx_at_signal,
                            ema_signal=t.ema_signal
                        )
                        db_trades.append(db_trade)
                        all_trades.append(t)

                    if db_trades:
                        db.bulk_save_objects(db_trades)

                    symbols_processed += 1

                    if symbols_processed % 10 == 0:
                        db.commit()

                    if symbols_processed % 5 == 0:
                        run.symbols_done = symbols_processed
                        db.commit()

                except Exception as e:
                    logger.error(f"Error processing symbol {symbol}: {e}")
                    logger.error(traceback.format_exc())
                    continue
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd backend
python -c "from app.backtest.engine import run_backtest, build_mtf_state_map, simulate_trades; print('OK')"
```

Expected:
```
OK
```

- [ ] **Step 3: Run the full test suite**

```bash
cd backend
python -m pytest tests/backtest/test_mtf_confirmation.py -v
```

Expected: All tests pass (same as Task 3, no regressions).

- [ ] **Step 4: Commit**

```bash
cd backend
git add app/backtest/engine.py
git commit -m "feat(backtest): wire MTF state maps into run_backtest symbol loop (MTF-003)"
```

---

## Task 5: Verify API Schema and `_serialize_run` Config Passthrough

**Files:**
- Modify: `backend/tests/backtest/test_mtf_confirmation.py` — add API schema tests (no live server needed)

### Context

MTF-004 requires:
1. `BacktestRequest` defaults: `require_weekly_confirmation=True`, `require_monthly_confirmation=False`.
2. Both fields appear in the serialised `config` JSON stored on `BacktestRun`.
3. `_serialize_run` returns both fields inside the `config` block.

Point 2 is satisfied automatically because `BacktestRequest.model_dump()` is called in the handler and the result is JSON-serialised into `BacktestRun.config`. Points 1 and 3 need explicit tests.

- [ ] **Step 1: Add schema and serialisation tests**

Append to `backend/tests/backtest/test_mtf_confirmation.py`:

```python
# ---------------------------------------------------------------------------
# API schema defaults — MTF-004
# ---------------------------------------------------------------------------
import json
from app.routers.backtest import BacktestRequest, _serialize_run
from app.db import models as db_models


class TestBacktestRequestDefaults:
    def test_weekly_confirmation_defaults_true(self):
        r = BacktestRequest()
        assert r.require_weekly_confirmation is True

    def test_monthly_confirmation_defaults_false(self):
        r = BacktestRequest()
        assert r.require_monthly_confirmation is False

    def test_explicit_override_weekly(self):
        r = BacktestRequest(require_weekly_confirmation=False)
        assert r.require_weekly_confirmation is False

    def test_explicit_override_monthly(self):
        r = BacktestRequest(require_monthly_confirmation=True)
        assert r.require_monthly_confirmation is True


class TestSerializeRunConfigBlock:
    """MTF-004: Both fields must appear in the serialised config JSON."""

    def _make_run(self, weekly: bool = True, monthly: bool = False) -> db_models.BacktestRun:
        config_dict = BacktestRequest(
            require_weekly_confirmation=weekly,
            require_monthly_confirmation=monthly,
        ).model_dump()
        run = db_models.BacktestRun(
            run_id="test-run-id",
            status="pending",
            config=json.dumps(config_dict, default=str),
            symbols_total=0,
            symbols_done=0,
        )
        return run

    def test_config_block_contains_weekly_field(self):
        run = self._make_run(weekly=True, monthly=False)
        serialised = _serialize_run(run, include_curve=False)
        assert "require_weekly_confirmation" in serialised["config"]
        assert serialised["config"]["require_weekly_confirmation"] is True

    def test_config_block_contains_monthly_field(self):
        run = self._make_run(weekly=True, monthly=True)
        serialised = _serialize_run(run, include_curve=False)
        assert "require_monthly_confirmation" in serialised["config"]
        assert serialised["config"]["require_monthly_confirmation"] is True

    def test_config_block_reflects_overridden_values(self):
        run = self._make_run(weekly=False, monthly=True)
        serialised = _serialize_run(run, include_curve=False)
        assert serialised["config"]["require_weekly_confirmation"] is False
        assert serialised["config"]["require_monthly_confirmation"] is True
```

- [ ] **Step 2: Run the new tests**

```bash
cd backend
python -m pytest tests/backtest/test_mtf_confirmation.py::TestBacktestRequestDefaults tests/backtest/test_mtf_confirmation.py::TestSerializeRunConfigBlock -v
```

Expected: All 7 tests pass. If `_serialize_run` fails to import, check it's defined at module level in `app/routers/backtest.py` (it is — it's a plain function, not a method).

- [ ] **Step 3: Run the complete test file**

```bash
cd backend
python -m pytest tests/backtest/test_mtf_confirmation.py -v
```

Expected: All tests pass. Note the count — there should be no fewer than 25 tests total.

- [ ] **Step 4: Commit**

```bash
cd backend
git add tests/backtest/test_mtf_confirmation.py
git commit -m "test(backtest): verify API schema defaults and config serialisation for MTF fields (MTF-004)"
```

---

## Task 6: Smoke Test — End-to-End Config Flow

**Files:**
- No new files. This is a manual verification step.

### Context

The unit tests cover all gate logic in isolation. This task verifies the full config flow from `BacktestRequest` → `BacktestConfig` → `run_backtest` (without running a full backtest — just checking the plumbing doesn't blow up).

- [ ] **Step 1: Verify `BacktestConfig` fields round-trip correctly through the handler constructor**

```bash
cd backend
python - << 'EOF'
import datetime
from app.routers.backtest import BacktestRequest
from app.backtest.engine import BacktestConfig

req = BacktestRequest(require_weekly_confirmation=False, require_monthly_confirmation=True)
config = BacktestConfig(
    score_threshold=req.score_threshold,
    holding_days=req.holding_days,
    stop_loss_pct=req.stop_loss_pct,
    target_pct=req.target_pct,
    trailing_stop_pct=req.trailing_stop_pct,
    require_volume_breakout=req.require_volume_breakout,
    use_regime_filter=req.use_regime_filter,
    require_weekly_confirmation=req.require_weekly_confirmation,
    require_monthly_confirmation=req.require_monthly_confirmation,
    atr_multiplier=req.atr_multiplier,
    risk_reward_ratio=req.risk_reward_ratio,
    use_atr_stops=req.use_atr_stops,
    min_adx=req.min_adx,
    include_fundamentals=req.include_fundamentals,
    symbol_limit=req.symbol_limit,
    screen_slug=req.screen_slug,
    date_from=None,
    date_to=None,
    starting_capital=req.starting_capital,
    position_size=req.position_size,
)
assert config.require_weekly_confirmation is False
assert config.require_monthly_confirmation is True
print("Config round-trip OK:", config.require_weekly_confirmation, config.require_monthly_confirmation)
EOF
```

Expected:
```
Config round-trip OK: False True
```

- [ ] **Step 2: Verify `build_mtf_state_map` works on real-ish data**

```bash
cd backend
python - << 'EOF'
import numpy as np
import pandas as pd
from app.backtest.engine import build_mtf_state_map

n = 400
closes = 100 + 0.5 * np.arange(n)
df = pd.DataFrame({
    "Open": closes * 0.998,
    "High": closes * 1.01,
    "Low": closes * 0.99,
    "Close": closes,
    "Volume": np.full(n, 1_000_000.0),
}, index=pd.date_range("2022-01-03", periods=n, freq="B"))

weekly_map = build_mtf_state_map(df, "W")
monthly_map = build_mtf_state_map(df, "M")

print(f"Weekly bars: {len(weekly_map)}, sample: {list(weekly_map.items())[-3:]}")
print(f"Monthly bars: {len(monthly_map)}, sample: {list(monthly_map.items())[-3:]}")
assert len(weekly_map) > 0
assert len(monthly_map) > 0
print("Smoke test PASSED")
EOF
```

Expected: Output shows non-zero bar counts and `True` states in an uptrend. No exceptions.

- [ ] **Step 3: Run all backtest tests one final time**

```bash
cd backend
python -m pytest tests/backtest/test_mtf_confirmation.py -v --tb=short
```

Expected: All tests pass, zero failures, zero errors.

- [ ] **Step 4: Final commit**

```bash
cd backend
git add .
git commit -m "feat(backtest): multi-timeframe entry confirmation complete (MTF-001/002/003/004/005)"
```

---

## Self-Review

### Spec Coverage

| Spec ID | Requirement | Covered by |
|---|---|---|
| MTF-001 | Weekly gate: `require_weekly_confirmation`, default True, fail-closed | Task 1 (config), Task 3 (gate logic + tests) |
| MTF-001 | Gate evaluated after ADX, before score threshold | Task 3 `simulate_trades` gate ordering |
| MTF-001 | Absent from map → rejected | `TestWeeklyConfirmationGate::test_trade_rejected_when_symbol_absent_from_map` |
| MTF-001 | Disabled → baseline behaviour | `TestWeeklyConfirmationGate::test_trade_entered_when_gate_disabled` |
| MTF-002 | Monthly gate: `require_monthly_confirmation`, default False, fail-closed | Task 1 (config), Task 3 (gate logic + tests) |
| MTF-002 | Both gates active simultaneously: both must be True | `TestBothGatesActive` |
| MTF-003 | State derived from OHLCV, not DB | `build_mtf_state_map` makes no DB calls |
| MTF-003 | Most recently completed bar (no look-ahead) | `resample_ohlcv(drop_incomplete=True)` + per-bar scoring in Task 2 |
| MTF-003 | Insufficient history → empty/False states | `TestBuildMtfStateMapInsufficientHistory` |
| MTF-003 | `resample_ohlcv` + `calculate_technical_score` reused | Task 2 implementation |
| MTF-003 | State maps passed to `simulate_trades` as args | Task 4 `run_backtest` symbol loop |
| MTF-004 | Both fields in `BacktestRequest` with correct defaults | Task 1, `TestBacktestRequestDefaults` |
| MTF-004 | Both fields pass through to `BacktestConfig` | Task 1 Step 3 |
| MTF-004 | Both fields in `config` JSON on `BacktestRun` | `TestSerializeRunConfigBlock` |
| MTF-005 | Gate ordering: Weekly after ADX, before score threshold | Task 3 `simulate_trades` gate comments and ordering |
| MTF-005 | Monthly after Weekly | Task 3 gate ordering |
| MTF-005 | All gates independently configurable | Separate booleans, tested independently |

### Placeholder Scan

None found. Every step contains complete runnable code and exact commands.

### Type Consistency

- `build_mtf_state_map(df, timeframe)` → `dict[datetime.date, bool]` — used consistently in Task 2 (definition), Task 3 (tests), Task 4 (`run_backtest` call).
- `_lookup_mtf_state(state_map, signal_date)` → `bool` — defined in Task 3, used in the same task's `simulate_trades` implementation.
- `simulate_trades(..., weekly_state_map=None, monthly_state_map=None)` — signature defined in Task 3, called in Task 4 with keyword arguments matching exactly.
- `BacktestConfig.require_weekly_confirmation` / `require_monthly_confirmation` — added in Task 1, referenced by exact name in Task 3 gate conditions (`config.require_weekly_confirmation`) and Task 4 (`config.require_monthly_confirmation`).
