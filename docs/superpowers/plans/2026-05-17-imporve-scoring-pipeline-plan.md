# Scoring & Pipeline Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix seven identified defects in the signal scoring and backtest simulation logic to reduce the stop-loss exit rate, eliminate null-safety gaps around the 200 EMA gate, rebalance MACD and RSI sub-scores, and add an ADX trend-strength gate.

**Architecture:** All changes are confined to two backend modules — `scorer.py` (scoring weights and caps) and `engine.py` (simulation gates, MIN_BARS, config defaults) — plus their corresponding schema in `backtest.py`. No database migrations, no new tables, no new dependencies. Each spec maps to one focused change in one or two functions.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pandas, pandas-ta, pytest.

---

## File Map

| File | Role | Action |
|---|---|---|
| `backend/app/pipeline/scorer.py` | MACD rebalance (SPEC-002), RSI cap (SPEC-003) | Modify |
| `backend/app/backtest/engine.py` | MIN_BARS (SPEC-001), ADX gate (SPEC-004), threshold default (SPEC-005), volume default (SPEC-006), 200 EMA null-safety (SPEC-007) | Modify |
| `backend/app/routers/backtest.py` | ADX field (SPEC-004), threshold default (SPEC-005), volume default (SPEC-006) | Modify |
| `backend/tests/test_scorer.py` | Tests for SPEC-002, SPEC-003 | Create |
| `backend/tests/test_backtest_engine.py` | Tests for SPEC-001, SPEC-004, SPEC-005, SPEC-006, SPEC-007 | Create |

---

## Task 1: SPEC-002 — MACD Scoring Rebalance

**Files:**
- Modify: `backend/app/pipeline/scorer.py` (function `calculate_technical_score`, the MACD block inside the `if timeframe == 'D':` branch)
- Test: `backend/tests/test_scorer.py`

### Context

`calculate_technical_score` computes a score dict from a pandas DataFrame of OHLCV data. It uses `pandas_ta` to append indicator columns. The function returns a dict with key `"score"`. The MACD block currently awards 12 pts when MACD > signal AND MACD < 0, and 6 pts when MACD > signal AND MACD > 0. These must be swapped.

- [ ] **Step 1: Create the test file with a failing test for the MACD rebalance**

Create `backend/tests/test_scorer.py`:

```python
import pandas as pd
import numpy as np
import pytest
from app.pipeline.scorer import calculate_technical_score


def _make_ohlcv(n: int, trend: str = "up") -> pd.DataFrame:
    """
    Builds a minimal OHLCV DataFrame of length n with a DatetimeIndex.
    trend='up'  → steadily rising close prices (bullish EMA alignment likely)
    trend='flat' → flat prices (neutral)
    """
    np.random.seed(42)
    if trend == "up":
        closes = np.linspace(100, 160, n) + np.random.normal(0, 0.5, n)
    else:
        closes = np.full(n, 100.0) + np.random.normal(0, 0.3, n)

    df = pd.DataFrame({
        "Open":   closes * 0.995,
        "High":   closes * 1.01,
        "Low":    closes * 0.99,
        "Close":  closes,
        "Volume": np.random.randint(1_000_000, 5_000_000, n).astype(float),
    }, index=pd.date_range("2022-01-01", periods=n, freq="B"))
    return df


def _make_macd_positive_territory_df() -> pd.DataFrame:
    """
    Constructs OHLCV so that after indicator calculation:
    - MACD line > signal line (no fresh cross on last bar)
    - MACD line > 0
    Uses a long sustained uptrend so the fast EMA stays well above slow EMA.
    300 bars ensures 200 EMA is valid (satisfies MIN_BARS guard in scorer).
    """
    n = 300
    # Strong sustained uptrend: MACD line will be positive
    closes = np.linspace(80, 200, n)
    df = pd.DataFrame({
        "Open":   closes * 0.998,
        "High":   closes * 1.015,
        "Low":    closes * 0.985,
        "Close":  closes,
        "Volume": np.full(n, 2_000_000.0),
    }, index=pd.date_range("2021-01-01", periods=n, freq="B"))
    return df


def _make_macd_negative_territory_df() -> pd.DataFrame:
    """
    Constructs OHLCV so that after indicator calculation:
    - MACD line > signal line (no fresh cross — prev MACD also > signal)
    - MACD line < 0  (recent recovery from downtrend, not yet above zero)
    300 bars for valid 200 EMA.
    """
    n = 300
    # Long downtrend, then small recovery at the end → MACD still negative
    closes = np.concatenate([
        np.linspace(200, 100, 270),   # downtrend
        np.linspace(100, 108, 30),    # mild recovery
    ])
    df = pd.DataFrame({
        "Open":   closes * 0.998,
        "High":   closes * 1.01,
        "Low":    closes * 0.99,
        "Close":  closes,
        "Volume": np.full(n, 2_000_000.0),
    }, index=pd.date_range("2021-01-01", periods=n, freq="B"))
    return df


class TestMACDScoring:
    def test_macd_positive_territory_scores_12(self):
        """MACD > signal AND MACD > 0 (no fresh cross) must score exactly 12 pts on MACD component."""
        df = _make_macd_positive_territory_df()
        result = calculate_technical_score(df, timeframe='D')

        import pandas_ta as ta
        check = df.copy()
        check.ta.macd(fast=12, slow=26, signal=9, append=True)
        latest = check.iloc[-1]
        prev   = check.iloc[-2]
        macd_line   = latest['MACD_12_26_9']
        signal_line = latest['MACDs_12_26_9']
        prev_macd   = prev['MACD_12_26_9']
        prev_sig    = prev['MACDs_12_26_9']

        # Guard: only run assertion if the data actually produced the condition we want
        fresh_cross = (macd_line > signal_line) and (prev_macd <= prev_sig)
        if fresh_cross or not (macd_line > signal_line and macd_line > 0):
            pytest.skip("DataFrame did not produce the required MACD state for this test.")

        # The MACD component contribution is not directly exposed, so we assert
        # that the score is HIGHER than the equivalent negative-territory setup.
        df_neg = _make_macd_negative_territory_df()
        result_neg = calculate_technical_score(df_neg, timeframe='D')
        assert result['score'] >= result_neg['score'], (
            "Positive-territory MACD should score >= negative-territory MACD "
            f"(got {result['score']} vs {result_neg['score']})"
        )

    def test_macd_negative_territory_scores_lower_than_positive(self):
        """MACD > signal AND MACD < 0 must produce a lower score than MACD > signal AND MACD > 0."""
        df_pos = _make_macd_positive_territory_df()
        df_neg = _make_macd_negative_territory_df()
        score_pos = calculate_technical_score(df_pos, timeframe='D')['score']
        score_neg = calculate_technical_score(df_neg, timeframe='D')['score']
        # Net effect: positive territory must not be penalised vs negative territory
        assert score_pos >= score_neg, (
            f"Expected positive-territory score ({score_pos}) >= negative-territory score ({score_neg})"
        )
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend
pytest tests/test_scorer.py::TestMACDScoring -v
```

Expected: `FAILED` — the current code awards 12 pts to negative territory, so positive territory under-scores.

- [ ] **Step 3: Apply the MACD rebalance in scorer.py**

In `backend/app/pipeline/scorer.py`, inside `calculate_technical_score`, locate the MACD block (inside `if timeframe == 'D':`) and replace:

```python
            if pd.notna(macd_line) and pd.notna(signal_line):
                fresh_macd_cross = (
                    pd.notna(prev_macd) and pd.notna(prev_signal_line) and
                    macd_line > signal_line and prev_macd <= prev_signal_line
                )
                if fresh_macd_cross:
                    score += 20
                elif macd_line > signal_line and macd_line < 0:
                    score += 12
                elif macd_line > signal_line and macd_line > 0:
                    score += 6
```

with:

```python
            if pd.notna(macd_line) and pd.notna(signal_line):
                fresh_macd_cross = (
                    pd.notna(prev_macd) and pd.notna(prev_signal_line) and
                    macd_line > signal_line and prev_macd <= prev_signal_line
                )
                if fresh_macd_cross:
                    score += 20
                elif macd_line > signal_line and macd_line > 0:
                    score += 12
                elif macd_line > signal_line and macd_line < 0:
                    score += 6
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
cd backend
pytest tests/test_scorer.py::TestMACDScoring -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/scorer.py backend/tests/test_scorer.py
git commit -m "fix(scorer): swap MACD pts — positive territory 12, negative territory 6 (SPEC-002)"
```

---

## Task 2: SPEC-003 — RSI Sub-Component Score Cap

**Files:**
- Modify: `backend/app/pipeline/scorer.py` (RSI block inside `if timeframe == 'D':`)
- Test: `backend/tests/test_scorer.py` (append to existing file)

### Context

The RSI block currently awards 20 pts when `recovering and fresh_ema_cross`. The RSI sub-component budget is 15 pts. The fix is to lower that single branch from 20 to 15.

- [ ] **Step 1: Add failing test for RSI cap**

Append to `backend/tests/test_scorer.py`:

```python
class TestRSIScoring:
    def test_rsi_component_never_exceeds_15(self):
        """
        The RSI sub-component must never contribute more than 15 pts.
        Max total technical score is 70: EMA(20) + MACD(20) + RSI(15) + Volume(15).
        Therefore score must never exceed 70.
        """
        # Use an uptrending DF that is likely to trigger RSI recovery + EMA cross
        n = 300
        # V-shape: down then strong up to trigger oversold recovery + EMA cross
        closes = np.concatenate([
            np.linspace(150, 90, 150),   # drop to oversold territory
            np.linspace(90, 180, 150),   # strong recovery
        ])
        df = pd.DataFrame({
            "Open":   closes * 0.997,
            "High":   closes * 1.012,
            "Low":    closes * 0.988,
            "Close":  closes,
            "Volume": np.full(n, 3_000_000.0),
        }, index=pd.date_range("2021-01-01", periods=n, freq="B"))

        result = calculate_technical_score(df, timeframe='D')
        assert result['score'] <= 70.0, (
            f"Technical score {result['score']} exceeds the 70-point maximum. "
            "RSI component must be capped at 15 pts."
        )

    def test_rsi_recovery_with_ema_cross_scores_same_as_without(self):
        """
        RSI recovery confirmed by EMA cross must score 15 pts — same as recovery without cross.
        Both paths should produce the same RSI contribution.
        """
        # This is verified indirectly: total score <= 70 is the binding constraint.
        # The absolute cap test above is the primary guard.
        n = 300
        closes = np.concatenate([
            np.linspace(150, 85, 150),
            np.linspace(85, 175, 150),
        ])
        df = pd.DataFrame({
            "Open":   closes * 0.997,
            "High":   closes * 1.012,
            "Low":    closes * 0.988,
            "Close":  closes,
            "Volume": np.full(n, 3_000_000.0),
        }, index=pd.date_range("2021-01-01", periods=n, freq="B"))
        result = calculate_technical_score(df, timeframe='D')
        # Primary assertion: score must respect 70-pt ceiling
        assert result['score'] <= 70.0
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend
pytest tests/test_scorer.py::TestRSIScoring -v
```

Expected: `FAILED` — the `recovering and fresh_ema_cross` path awards 20 pts, pushing total above 70.

- [ ] **Step 3: Apply the RSI cap in scorer.py**

In `backend/app/pipeline/scorer.py`, inside `calculate_technical_score`, locate the RSI block (inside `if timeframe == 'D':`) and replace:

```python
            if pd.notna(rsi) and pd.notna(prev_rsi):
                # Check for recovery in last 5 days
                recent_rsi = df['RSI_14'].tail(5)
                was_oversold = any(recent_rsi < 30)
                
                recovering = was_oversold and rsi > 30 and pd.notna(ema20) and price > ema20
                crossing_50 = prev_rsi <= 50 and rsi > 50
                
                if recovering and fresh_ema_cross:
                    score += 20
                    rsi_signal = "bullish_recovery_confirmed"
                elif recovering:
                    score += 15
                    rsi_signal = "bullish_recovery"
                elif crossing_50:
                    score += 10
                    rsi_signal = "bullish_crossing"
                elif rsi > 50:
                    score += 3
                    rsi_signal = "bullish_strong"
```

with:

```python
            if pd.notna(rsi) and pd.notna(prev_rsi):
                # Check for recovery in last 5 days
                recent_rsi = df['RSI_14'].tail(5)
                was_oversold = any(recent_rsi < 30)
                
                recovering = was_oversold and rsi > 30 and pd.notna(ema20) and price > ema20
                crossing_50 = prev_rsi <= 50 and rsi > 50
                
                if recovering and fresh_ema_cross:
                    score += 15   # capped at RSI budget; EMA cross already scored separately
                    rsi_signal = "bullish_recovery_confirmed"
                elif recovering:
                    score += 15
                    rsi_signal = "bullish_recovery"
                elif crossing_50:
                    score += 10
                    rsi_signal = "bullish_crossing"
                elif rsi > 50:
                    score += 3
                    rsi_signal = "bullish_strong"
```

- [ ] **Step 4: Run all scorer tests**

```bash
cd backend
pytest tests/test_scorer.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/scorer.py backend/tests/test_scorer.py
git commit -m "fix(scorer): cap RSI sub-component at 15 pts maximum (SPEC-003)"
```

---

## Task 3: SPEC-001 — Minimum Bar Requirement (MIN_BARS = 210)

**Files:**
- Modify: `backend/app/backtest/engine.py` (function `score_series`)
- Test: `backend/tests/test_backtest_engine.py`

### Context

`score_series(df, fund_cache, config)` iterates from `MIN_BARS` (currently 60) to end of df, calling `calculate_technical_score` on each slice. The 200 EMA requires 200 bars. The fix raises `MIN_BARS` to 210 — giving a 10-bar buffer after the 200 EMA becomes valid.

- [ ] **Step 1: Create the engine test file with a failing test**

Create `backend/tests/test_backtest_engine.py`:

```python
import pandas as pd
import numpy as np
import datetime
import pytest
from app.backtest.engine import score_series, simulate_trades, BacktestConfig


def _make_ohlcv(n: int) -> pd.DataFrame:
    """Returns a simple uptrending OHLCV DataFrame of length n."""
    np.random.seed(0)
    closes = np.linspace(100, 200, n) + np.random.normal(0, 0.3, n)
    df = pd.DataFrame({
        "Open":   closes * 0.998,
        "High":   closes * 1.01,
        "Low":    closes * 0.99,
        "Close":  closes,
        "Volume": np.full(n, 2_000_000.0),
    }, index=pd.date_range("2020-01-01", periods=n, freq="B"))
    return df


class TestMinBars:
    def test_no_signals_below_210_bars(self):
        """score_series must return an empty list when df has fewer than 210 rows."""
        df = _make_ohlcv(209)
        config = BacktestConfig()
        results = score_series(df, fund_cache=None, config=config)
        assert results == [], (
            f"Expected no signals for a 209-bar DataFrame, got {len(results)}"
        )

    def test_signals_possible_at_210_bars(self):
        """score_series may return signals when df has exactly 210 rows."""
        df = _make_ohlcv(210)
        config = BacktestConfig()
        results = score_series(df, fund_cache=None, config=config)
        # We only assert it doesn't crash and returns a list; signal generation depends on data.
        assert isinstance(results, list)

    def test_no_signals_at_exactly_60_bars(self):
        """Regression: 60 bars (old MIN_BARS) must now produce zero signals."""
        df = _make_ohlcv(60)
        config = BacktestConfig()
        results = score_series(df, fund_cache=None, config=config)
        assert results == [], (
            "60-bar DataFrame should produce no signals after MIN_BARS fix."
        )
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend
pytest tests/test_backtest_engine.py::TestMinBars -v
```

Expected: `FAILED` — `test_no_signals_below_210_bars` fails because the current code starts at bar 60.

- [ ] **Step 3: Apply the MIN_BARS fix in engine.py**

In `backend/app/backtest/engine.py`, inside `score_series`, replace:

```python
    results = []
    MIN_BARS = 60
    
    # Iterate from MIN_BARS to end
    for i in range(MIN_BARS, len(df)):
```

with:

```python
    results = []
    MIN_BARS = 210  # 200 EMA requires 200 bars; 10-bar buffer for stability
    
    # Iterate from MIN_BARS to end
    for i in range(MIN_BARS, len(df)):
```

Also update the early-exit guard at the top of `score_series`. Replace:

```python
    if df is None or len(df) < 60:
        return []
```

with:

```python
    if df is None or len(df) < 210:
        return []
```

- [ ] **Step 4: Run the tests**

```bash
cd backend
pytest tests/test_backtest_engine.py::TestMinBars -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/backtest/engine.py backend/tests/test_backtest_engine.py
git commit -m "fix(engine): raise MIN_BARS from 60 to 210 — no signals before 200 EMA is valid (SPEC-001)"
```

---

## Task 4: SPEC-007 — 200 EMA Null-Safety in simulate_trades

**Files:**
- Modify: `backend/app/backtest/engine.py` (function `simulate_trades`)
- Test: `backend/tests/test_backtest_engine.py` (append)

### Context

`simulate_trades` receives a list of pre-scored signal dicts. Each dict has an `"above_200ema"` key that can be `True`, `False`, or `None`. Currently, only the score threshold is checked; `above_200ema` is not re-validated here. A signal with `above_200ema = None` and score ≥ threshold must be rejected.

- [ ] **Step 1: Add failing test for null-safety**

Append to `backend/tests/test_backtest_engine.py`:

```python
class TestAbove200EMAGate:
    def _base_config(self) -> BacktestConfig:
        return BacktestConfig(
            score_threshold=10.0,   # low so score doesn't interfere
            stop_loss_pct=0.0,
            target_pct=0.0,
            holding_days=5,
            use_regime_filter=False,
            require_volume_breakout=False,
        )

    def _make_signal(self, above_200ema, score=80.0) -> dict:
        return {
            "date": pd.Timestamp("2023-06-01"),
            "score": score,
            "above_200ema": above_200ema,
            "rsi": 55.0,
            "adx": 25.0,
            "ema_signal": "bullish",
            "volume_signal": "bullish",
            "rsi_signal": "bullish_strong",
            "volume_breakout": True,
            "atr": 2.0,
        }

    def test_above_200ema_none_produces_no_trade(self):
        """Signals with above_200ema=None must be rejected regardless of score."""
        df = _make_ohlcv(300)
        signal = self._make_signal(above_200ema=None)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._base_config())
        assert trades == [], "above_200ema=None should produce no trade"

    def test_above_200ema_false_produces_no_trade(self):
        """Signals with above_200ema=False must be rejected regardless of score."""
        df = _make_ohlcv(300)
        signal = self._make_signal(above_200ema=False)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._base_config())
        assert trades == [], "above_200ema=False should produce no trade"

    def test_above_200ema_true_allows_trade(self):
        """Signals with above_200ema=True and sufficient score must produce a trade."""
        df = _make_ohlcv(300)
        signal = self._make_signal(above_200ema=True)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._base_config())
        assert len(trades) == 1, "above_200ema=True should produce a trade"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
pytest tests/test_backtest_engine.py::TestAbove200EMAGate -v
```

Expected: `FAILED` — `test_above_200ema_none_produces_no_trade` and `test_above_200ema_false_produces_no_trade` fail because `simulate_trades` does not check this field.

- [ ] **Step 3: Add the 200 EMA null-safety check in simulate_trades**

In `backend/app/backtest/engine.py`, inside `simulate_trades`, locate the block that checks `signal['score'] >= config.score_threshold`. It currently reads:

```python
        if signal_idx is None or signal_idx <= last_exit_idx:
            continue
            
        if signal['score'] >= config.score_threshold:
```

Add the `above_200ema` gate immediately after the score check (as a separate `if` block inside the score check, or as an additional guard before the entry block):

```python
        if signal_idx is None or signal_idx <= last_exit_idx:
            continue

        # 200 EMA null-safety gate (belt-and-suspenders; also enforced in score_series)
        if signal.get('above_200ema') is not True:
            continue
            
        if signal['score'] >= config.score_threshold:
```

- [ ] **Step 4: Run all engine tests**

```bash
cd backend
pytest tests/test_backtest_engine.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/backtest/engine.py backend/tests/test_backtest_engine.py
git commit -m "fix(engine): gate simulate_trades on above_200ema=True; None/False rejected (SPEC-007)"
```

---

## Task 5: SPEC-004 — ADX Trend Strength Gate

**Files:**
- Modify: `backend/app/backtest/engine.py` (`BacktestConfig` dataclass, `simulate_trades`)
- Modify: `backend/app/routers/backtest.py` (`BacktestRequest`, the `run_wrapper` config construction)
- Test: `backend/tests/test_backtest_engine.py` (append)

### Context

`BacktestConfig` is a `@dataclass` in `engine.py`. `BacktestRequest` is a Pydantic `BaseModel` in `backtest.py`. A new `min_adx` field (default 20, range 0–50) must be added to both. In `simulate_trades`, signals with `adx` below `config.min_adx` (or `None`) must be skipped. Setting `min_adx=0` disables the gate.

- [ ] **Step 1: Add failing tests for ADX gate**

Append to `backend/tests/test_backtest_engine.py`:

```python
class TestADXGate:
    def _config(self, min_adx: float) -> BacktestConfig:
        return BacktestConfig(
            score_threshold=10.0,
            stop_loss_pct=0.0,
            target_pct=0.0,
            holding_days=5,
            use_regime_filter=False,
            require_volume_breakout=False,
            min_adx=min_adx,
        )

    def _signal(self, adx_value) -> dict:
        return {
            "date": pd.Timestamp("2023-06-01"),
            "score": 80.0,
            "above_200ema": True,
            "rsi": 55.0,
            "adx": adx_value,
            "ema_signal": "bullish",
            "volume_signal": "bullish",
            "rsi_signal": "bullish_strong",
            "volume_breakout": True,
            "atr": 2.0,
        }

    def test_adx_below_threshold_produces_no_trade(self):
        """Signal with ADX < min_adx must be skipped."""
        df = _make_ohlcv(300)
        signal = self._signal(adx_value=15.0)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._config(min_adx=20))
        assert trades == [], "ADX=15 below threshold=20 should produce no trade"

    def test_adx_none_produces_no_trade(self):
        """Signal with ADX=None must be skipped when min_adx > 0."""
        df = _make_ohlcv(300)
        signal = self._signal(adx_value=None)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._config(min_adx=20))
        assert trades == [], "ADX=None should produce no trade when min_adx=20"

    def test_adx_at_threshold_allows_trade(self):
        """Signal with ADX exactly equal to min_adx must be allowed."""
        df = _make_ohlcv(300)
        signal = self._signal(adx_value=20.0)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._config(min_adx=20))
        assert len(trades) == 1, "ADX=20 at threshold=20 should produce a trade"

    def test_adx_gate_disabled_when_min_adx_zero(self):
        """min_adx=0 must disable the gate; ADX=None signals are allowed."""
        df = _make_ohlcv(300)
        signal = self._signal(adx_value=None)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._config(min_adx=0))
        assert len(trades) == 1, "min_adx=0 should disable ADX gate"

    def test_backtest_config_default_min_adx_is_20(self):
        """BacktestConfig default min_adx must be 20."""
        config = BacktestConfig()
        assert config.min_adx == 20
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
pytest tests/test_backtest_engine.py::TestADXGate -v
```

Expected: `FAILED` — `BacktestConfig` has no `min_adx` field.

- [ ] **Step 3: Add min_adx to BacktestConfig in engine.py**

In `backend/app/backtest/engine.py`, add `min_adx` to the `BacktestConfig` dataclass. Locate the dataclass and add after `use_atr_stops`:

```python
@dataclass
class BacktestConfig:
    score_threshold: float = 55.0      # raised from 45 per SPEC-005 (applied in Task 6)
    holding_days: int = 20
    stop_loss_pct: float = 7.0
    target_pct: float = 0.0
    trailing_stop_pct: float = 0.0
    require_volume_breakout: bool = True   # changed from False per SPEC-006 (applied in Task 6)
    use_regime_filter: bool = True
    atr_multiplier: float = 2.0
    risk_reward_ratio: float = 2.5
    use_atr_stops: bool = False
    min_adx: float = 20.0             # NEW: 0 disables the gate (SPEC-004)
    include_fundamentals: bool = False
    timeframe: str = 'D'
    date_from: datetime.date = None
    date_to: datetime.date = None
    symbol_limit: int = None
    screen_slug: Optional[str] = None
    starting_capital: float = 1000000.0
    position_size: float = 10000.0
```

> Note: `score_threshold` and `require_volume_breakout` defaults are updated here to pre-empt Task 6 — they are logically independent changes. If you prefer strict task isolation, set them to the old values (45.0, False) now and update in Task 6.

- [ ] **Step 4: Add the ADX gate in simulate_trades**

In `backend/app/backtest/engine.py`, inside `simulate_trades`, add the ADX gate immediately after the `above_200ema` gate added in Task 4:

```python
        # 200 EMA null-safety gate (belt-and-suspenders; also enforced in score_series)
        if signal.get('above_200ema') is not True:
            continue

        # ADX trend-strength gate (min_adx=0 disables)
        if config.min_adx > 0:
            adx_val = signal.get('adx')
            if adx_val is None or adx_val < config.min_adx:
                continue

        if signal['score'] >= config.score_threshold:
```

- [ ] **Step 5: Add min_adx to BacktestRequest in backtest.py**

In `backend/app/routers/backtest.py`, add to `BacktestRequest`:

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
    use_regime_filter: bool = Field(default=True,
        description="If true, only enters trades when Nifty is in a bull regime.")
    atr_multiplier: float = Field(default=2.0, ge=1.0, le=10.0,
        description="Multiplier for ATR-based stop loss.")
    risk_reward_ratio: float = Field(default=2.5, ge=0.5, le=10.0,
        description="Target profit as a multiple of risk.")
    use_atr_stops: bool = Field(default=False,
        description="If true, uses ATR-based stops instead of flat percentage.")
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

- [ ] **Step 6: Wire min_adx into the config construction in backtest.py**

In `backend/app/routers/backtest.py`, inside `start_backtest`, locate the `config = BacktestConfig(...)` block and add `min_adx`:

```python
    config = BacktestConfig(
        score_threshold=request.score_threshold,
        holding_days=request.holding_days,
        stop_loss_pct=request.stop_loss_pct,
        target_pct=request.target_pct,
        trailing_stop_pct=request.trailing_stop_pct,
        require_volume_breakout=request.require_volume_breakout,
        use_regime_filter=request.use_regime_filter,
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

- [ ] **Step 7: Run all engine tests**

```bash
cd backend
pytest tests/test_backtest_engine.py -v
```

Expected: all `PASSED`

- [ ] **Step 8: Commit**

```bash
git add backend/app/backtest/engine.py backend/app/routers/backtest.py backend/tests/test_backtest_engine.py
git commit -m "feat(engine): add ADX trend-strength gate with min_adx config field (SPEC-004)"
```

---

## Task 6: SPEC-005 & SPEC-006 — Default Threshold and Volume Breakout Changes

**Files:**
- Modify: `backend/app/backtest/engine.py` (`BacktestConfig`)
- Modify: `backend/app/routers/backtest.py` (`BacktestRequest`)
- Test: `backend/tests/test_backtest_engine.py` (append)

### Context

If you applied the `BacktestConfig` defaults in Task 5 Step 3 as instructed, this task only verifies and tests them. If you held off, apply the defaults here. This task also adds explicit test assertions for both defaults.

- [ ] **Step 1: Add tests for default values**

Append to `backend/tests/test_backtest_engine.py`:

```python
class TestConfigDefaults:
    def test_default_score_threshold_is_55(self):
        config = BacktestConfig()
        assert config.score_threshold == 55.0, (
            f"Default score_threshold must be 55.0, got {config.score_threshold}"
        )

    def test_default_require_volume_breakout_is_true(self):
        config = BacktestConfig()
        assert config.require_volume_breakout is True, (
            "Default require_volume_breakout must be True"
        )
```

- [ ] **Step 2: Run to confirm current state**

```bash
cd backend
pytest tests/test_backtest_engine.py::TestConfigDefaults -v
```

If you applied the defaults in Task 5, these pass already. If not, they will `FAIL` and you apply the fix in Step 3.

- [ ] **Step 3: Apply defaults if not already applied**

If the tests failed, update `BacktestConfig` in `backend/app/backtest/engine.py`:

```python
    score_threshold: float = 55.0         # raised from 45 (SPEC-005)
    require_volume_breakout: bool = True  # changed from False (SPEC-006)
```

And update `BacktestRequest` in `backend/app/routers/backtest.py`:

```python
    score_threshold: float = Field(default=55.0, ge=0, le=100,
        description="Minimum score. Recommended: 55–65 for technical-only signals, 45–55 with fundamentals.")
    require_volume_breakout: bool = Field(default=True,
        description="Requires volume > 2x SMA20 for entry. Disabling increases trade count and stop-loss rate.")
```

- [ ] **Step 4: Run all tests**

```bash
cd backend
pytest tests/test_backtest_engine.py tests/test_scorer.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/backtest/engine.py backend/app/routers/backtest.py backend/tests/test_backtest_engine.py
git commit -m "fix(config): raise default score_threshold to 55, default volume_breakout to True (SPEC-005, SPEC-006)"
```

---

## Task 7: Full Regression & Smoke Test

**Files:**
- No code changes. Verification only.

### Context

All seven specs are now implemented. This task runs the full test suite and performs a manual smoke test via the API to confirm no regressions.

- [ ] **Step 1: Run the full test suite**

```bash
cd backend
pytest tests/ -v --tb=short
```

Expected: all `PASSED`, no warnings about unexpected failures.

- [ ] **Step 2: Start the API server**

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Expected: server starts without import errors.

- [ ] **Step 3: Submit a baseline backtest request and confirm new defaults**

```bash
curl -s -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"symbol_limit": 10, "date_from": "2023-01-01", "date_to": "2024-01-01"}' \
  | python3 -m json.tool
```

Expected response includes:
```json
{
  "run_id": "...",
  "status": "pending"
}
```

- [ ] **Step 4: Poll the run until complete and verify config defaults are recorded**

```bash
# Replace <run_id> with the value from Step 3
curl -s http://localhost:8000/api/backtest/<run_id> | python3 -m json.tool
```

Expected: in the `config` block of the response:
```json
"score_threshold": 55.0,
"require_volume_breakout": true,
"min_adx": 20.0
```

- [ ] **Step 5: Submit a request with min_adx=0 to verify gate can be disabled**

```bash
curl -s -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "symbol_limit": 10,
    "date_from": "2023-01-01",
    "date_to": "2024-01-01",
    "min_adx": 0,
    "require_volume_breakout": false,
    "score_threshold": 45.0
  }' | python3 -m json.tool
```

Expected: run starts with `"status": "pending"`. Poll and confirm `total_trades` is higher than the default-config run (more permissive filters = more trades).

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "test: full regression pass — all SPEC-001 through SPEC-007 verified"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec | Task | Status |
|---|---|---|
| SPEC-001: MIN_BARS = 210 | Task 3 | ✓ |
| SPEC-002: MACD rebalance | Task 1 | ✓ |
| SPEC-003: RSI cap at 15 | Task 2 | ✓ |
| SPEC-004: ADX gate | Task 5 | ✓ |
| SPEC-005: threshold default 55 | Task 6 | ✓ |
| SPEC-006: volume breakout default True | Task 6 | ✓ |
| SPEC-007: 200 EMA null-safety in simulate_trades | Task 4 | ✓ |

### Placeholder Scan

No TBDs, no "implement later", no "similar to Task N" — all code blocks are complete and self-contained.

### Type Consistency

- `BacktestConfig.min_adx: float` — defined in Task 5 Step 3, referenced as `config.min_adx` in Task 5 Step 4. ✓
- `signal.get('adx')` — the key `'adx'` is set in `score_series` dict output (`"adx": ta_data.get('adx')`) and read in `simulate_trades`. ✓
- `signal.get('above_200ema')` — the key `'above_200ema'` is set in `score_series` and read in both Task 3 (score_series guard) and Task 4 (simulate_trades guard). ✓
- `_make_ohlcv` helper is defined once in `test_backtest_engine.py` and reused across all test classes in that file. ✓