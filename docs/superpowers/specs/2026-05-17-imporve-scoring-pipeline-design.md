# Technical Specification: Scoring & Pipeline Fixes

**Version:** 1.0  
**Status:** Draft  
**Scope:** `app/backtest/engine.py`, `app/pipeline/scorer.py`, `app/pipeline/orchestrator.py`

---

## Background

Backtesting over 2023–2025 revealed structural issues in the signal scoring and pipeline filtering logic. The primary symptoms are a ~47% stop-loss exit rate, negative median trade return despite a positive mean, and total returns significantly below benchmark. This document specifies corrections to address the root causes identified.

---

## Specification 1 — Minimum Bar Requirement for Signal Generation

**ID:** SPEC-001  
**Priority:** Critical  
**Affected component:** `engine.py → score_series()`

### Problem

The minimum bar count before signal generation begins is currently 60. The 200-period EMA requires 200 bars to produce a valid value. Between bar 60 and bar 199, `above_200ema` resolves to `None`. The existing hard filter only suppresses signals when `above_200ema` is explicitly `False`, allowing signals to pass through during the entire period when the 200 EMA is not yet computable.

### Required Behaviour

- The minimum bar threshold before any signal is evaluated must be raised to **210 bars**.
- No signal — regardless of score — may be generated for a symbol until at least 210 bars of OHLCV data are present in the slice.
- The `above_200ema` null-pass condition must be treated as a filter failure. A signal with `above_200ema = None` must be suppressed in the same way as one with `above_200ema = False`.

### Acceptance Criteria

- Zero signals generated for any symbol on bar slices shorter than 210 bars.
- A symbol with fewer than 210 total historical bars produces an empty scored signal list.
- `above_200ema = None` results in a zeroed score, identical to the explicit `False` case.

---

## Specification 2 — MACD Component Scoring Rebalance

**ID:** SPEC-002  
**Priority:** High  
**Affected component:** `scorer.py → calculate_technical_score()`

### Problem

The current MACD scoring awards more points (12) when the MACD line is above the signal line but still in negative territory than when it is above the signal line in positive territory (6). This inversely rewards ambiguous early-recovery setups over confirmed bullish momentum.

### Required Behaviour

The point allocation for the MACD sub-component must reflect trend confirmation strength as follows:

| Condition | Points |
|---|---|
| Fresh MACD crossover (any territory) | 20 |
| MACD above signal line AND MACD line is positive | 12 |
| MACD above signal line AND MACD line is negative | 6 |

"Positive territory" means the MACD line value is greater than zero. "Negative territory" means the MACD line value is less than or equal to zero.

### Acceptance Criteria

- A stock with MACD > signal and MACD > 0 (no fresh cross) scores 12 pts on the MACD component.
- A stock with MACD > signal and MACD < 0 (no fresh cross) scores 6 pts on the MACD component.
- A fresh crossover continues to score 20 pts regardless of the absolute MACD value.
- No other MACD scoring path is changed.

---

## Specification 3 — RSI Sub-Component Score Cap

**ID:** SPEC-003  
**Priority:** High  
**Affected component:** `scorer.py → calculate_technical_score()`

### Problem

When both an RSI recovery condition and a fresh EMA cross are simultaneously present, the RSI component awards 20 points — exceeding the stated 15-point budget for the RSI sub-component. Combined with the EMA cross scoring 20 points, these two conditions alone can drive a signal to 40 points, clearing the 45-point threshold with minimal additional confirmation.

### Required Behaviour

- The RSI sub-component has an absolute maximum of **15 points** regardless of which condition path is taken.
- The "recovery confirmed by EMA cross" bonus path must be capped at 15 points, not 20.
- The EMA cross remains a separate input into the EMA sub-component and is not otherwise changed.

### Point allocation after cap:

| Condition | Points |
|---|---|
| RSI recovery + fresh EMA cross confirmation | 15 (was 20) |
| RSI recovery without EMA confirmation | 15 |
| RSI crossing 50 from below | 10 |
| RSI > 50 (no cross, no recovery) | 3 |

### Acceptance Criteria

- The maximum total score attributable to the RSI sub-component is 15 in all code paths.
- An RSI recovery with EMA confirmation produces the same RSI sub-score as an RSI recovery without EMA confirmation.
- Total possible technical score remains 70.

---

## Specification 4 — ADX Trend Strength Gate

**ID:** SPEC-004  
**Priority:** High  
**Affected component:** `engine.py → simulate_trades()`

### Problem

ADX is computed and stored on every signal but is never used as a filter during trade simulation. Signals generated in choppy, low-trend-strength environments have identical eligibility to those in strong trending conditions, contributing to false breakouts and stop-loss exits.

### Required Behaviour

- A minimum ADX threshold must be applied as a hard gate before a signal is eligible for trade entry.
- The default minimum ADX value is **20**.
- Signals where `adx_at_signal` is below the threshold or is `None` must be skipped — no trade is entered regardless of score.
- The ADX threshold must be a configurable parameter on `BacktestConfig` and `BacktestRequest`, with a default of 20 and a valid range of 0 (disabled) to 50.
- A value of 0 disables the ADX gate entirely for backward compatibility testing.

### Acceptance Criteria

- No trade is entered when the signal's ADX value is below the configured threshold.
- `None` ADX is treated as below threshold (gate fails).
- Setting `min_adx = 0` in config produces behaviour identical to the pre-fix baseline.
- The `BacktestRequest` schema exposes `min_adx` with a default of 20.

---

## Specification 5 — Score Threshold Calibration

**ID:** SPEC-005  
**Priority:** High  
**Affected component:** `engine.py → BacktestConfig`, `routers/backtest.py → BacktestRequest`

### Problem

The default score threshold of 45 is insufficiently selective. Given the current scoring topology, a stock can cross 45 with a fresh EMA cross (20 pts) and volume on a green day (15 pts) alone — a two-condition signal that lacks MACD and RSI confirmation. This produces entries in low-conviction setups.

### Required Behaviour

- The default score threshold must be raised from **45 to 55**.
- The valid range remains 0–100.
- Existing API documentation (field description strings) must reflect updated guidance: threshold of 55–65 recommended for technical-only signals; 45–55 when fundamentals are included.
- No other scoring weights or paths are changed by this specification.

### Rationale for 55

At 55, a signal requires meaningful multi-indicator alignment. The minimum path to 55 now requires at minimum:
- A fresh EMA crossover (20) + fresh MACD crossover (20) = 40 — still short, forcing at least RSI or volume confirmation to cross the threshold.
- Or: EMA bullish alignment (8) + MACD positive territory (12) + Volume (15) + RSI > 50 (3) + RSI crossing 50 (10) = 48 — still below, requiring one additional quality condition.

### Acceptance Criteria

- Default `BacktestConfig.score_threshold` is 55.
- Default `BacktestRequest.score_threshold` is 55.
- The field description is updated to reflect that 55 is the recommended starting point.

---

## Specification 6 — `require_volume_breakout` Default

**ID:** SPEC-006  
**Priority:** Medium  
**Affected component:** `engine.py → BacktestConfig`, `routers/backtest.py → BacktestRequest`

### Problem

`require_volume_breakout` defaults to `False`. Given that volume confirmation is the primary differentiator between genuine breakouts and low-conviction technical alignments — and given the 47% stop-loss rate observed — the default posture should require volume confirmation.

### Required Behaviour

- The default value of `require_volume_breakout` in both `BacktestConfig` and `BacktestRequest` must be changed from `False` to **`True`**.
- No logic changes to how the filter is applied when enabled.
- The field description must be updated to note that disabling this filter is expected to increase trade count and stop-loss rate.

### Acceptance Criteria

- A `BacktestRequest` submitted with no `require_volume_breakout` field defaults to `True`.
- `BacktestConfig` instantiated with no arguments has `require_volume_breakout = True`.

---

## Specification 7 — Null Safety on `above_200ema` Filter in `simulate_trades`

**ID:** SPEC-007  
**Priority:** Medium  
**Affected component:** `engine.py → simulate_trades()`

### Problem

The `above_200ema` null-pass behaviour described in SPEC-001 is addressed in `score_series`. However, `simulate_trades` receives a pre-scored signal list and does not independently verify the 200 EMA condition. Signals scored before SPEC-001 is applied (e.g. from a pre-existing run) could still produce trades.

### Required Behaviour

- `simulate_trades` must check that `above_200ema` is explicitly `True` on each signal before entering a trade.
- If `above_200ema` is `False` or `None`, the signal must be skipped regardless of score.
- This is a belt-and-suspenders check independent of the `score_series` fix in SPEC-001.

### Acceptance Criteria

- A signal with `above_200ema = None` and score ≥ threshold is not traded.
- A signal with `above_200ema = False` and score ≥ threshold is not traded.
- A signal with `above_200ema = True` continues to be eligible for trade entry subject to all other filters.

---

## Consolidated Change Summary

| Spec | Component | Change Type | Default Impact |
|---|---|---|---|
| SPEC-001 | `engine.py` | Bug fix — MIN_BARS | Reduces signal count significantly |
| SPEC-002 | `scorer.py` | Logic rebalance — MACD points | Reduces scores on MACD-only setups |
| SPEC-003 | `scorer.py` | Score cap — RSI max 15 pts | Reduces scores on recovery setups |
| SPEC-004 | `engine.py` | New gate — ADX ≥ 20 | Filters low-trend signals |
| SPEC-005 | `engine.py`, `backtest.py` | Default change — threshold 45→55 | Reduces trade count |
| SPEC-006 | `engine.py`, `backtest.py` | Default change — volume breakout on | Reduces trade count |
| SPEC-007 | `engine.py` | Null safety — 200 EMA in trade sim | Filters pre-200-bar signals |

---

## Out of Scope

The following issues were identified but are excluded from this specification:

- Extending the backtest date range or changing the benchmark.
- Fundamental scoring changes.
- Pipeline Tier 1/Tier 2 filtering thresholds.
- Equity curve construction methodology.
- Multi-symbol position sizing or portfolio-level risk management.
- Weekly and Monthly timeframe scoring logic.