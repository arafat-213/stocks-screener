# Technical Specification: Scoring Model & Backtest Strategy Improvements

**Version:** 1.0  
**Date:** 2026-05-18  
**Status:** Draft  

---

## 1. Problem Statement

The current backtest produces a **win rate of 36.6%** against a system breakeven threshold of approximately **37.9%**, resulting in:

- Negative expectancy (−0.19% per trade)
- Profit factor of 0.956 (below 1.0)
- Sharpe ratio of −0.17
- Total return of −0.52% vs benchmark +8.75%

The root causes are: poor signal quality at entry (late entries, weak EMA states), disabled volume confirmation gate, and RSI entry at overbought levels. The scoring model allows too many marginal signals to pass the threshold.

---

## 2. Objectives

| # | Objective | Target Metric |
|---|-----------|---------------|
| O-1 | Improve signal entry timing | Median return ≥ 0% |
| O-2 | Raise win rate | Win rate ≥ 50% |
| O-3 | Improve risk-adjusted return | Profit factor ≥ 1.5 |
| O-4 | Beat benchmark consistently | Alpha ≥ 5% annualised |
| O-5 | Improve Sharpe ratio | Sharpe ≥ 0.5 |

---

## 3. Signal Quality Gate (Entry Filter)

### 3.1 EMA Signal Tier Enforcement

The scoring model currently awards 8 points for a generic "bullish" EMA state (EMA5 > EMA13 > EMA26 > price). This is a continuation state, not an entry trigger. Trades entered in this state are late — the trend is already running and the risk/reward is poor.

**Requirement:** A trade shall only be entered when `ema_signal` is one of:

| Signal | Pts Awarded | Description |
|--------|-------------|-------------|
| `bullish_cross` | 20 | EMA5 just crossed above EMA13 — fresh trigger |
| `bullish_pullback` | 15 | Price pulled back to EMA20 within an aligned trend |

The generic `bullish` state (8 pts) shall disqualify a signal from entry regardless of total score.

**Rationale:** The trades sample shows the majority of losing trades entered on `ema_signal: "bullish"`. Crosses and pullbacks define precise price events with known risk levels; generic alignment does not.

---

### 3.2 RSI Entry Ceiling

The current hard filter removes signals where RSI > 80. Historical trades show entries at RSI 70–79 consistently underperform.

**Requirement:** A signal shall be disqualified if RSI at the time of signal is > 68.

**Rationale:** RSI above 68 indicates the stock is in extended/overbought territory relative to recent history. Fresh crosses that occur at RSI > 68 are typically exhaustion moves, not the start of a new leg. The 68 threshold preserves valid strong-trend entries (RSI 50–68) while filtering distribution phases.

---

### 3.3 Volume Breakout Re-Enablement

The backtest run under analysis had `require_volume_breakout: false`. This flag was deliberately introduced per internal spec to require volume > 2× 20-day SMA on a green day as a condition for entry.

**Requirement:** `require_volume_breakout` shall default to `true`. Volume breakout confirmation is required for all entry signals.

**Rationale:** Volume breakout disqualification reduces trade count but substantially improves signal quality. Institutional accumulation is visible in volume; retail chasing is not. The 47% stop-loss rate in the current run is consistent with entering on low-volume moves that fail to attract follow-through.

---

### 3.4 Composite Signal Quality Score (New)

In addition to the raw score threshold, a **signal quality tier** shall be calculated for each signal. Only Tier 1 and Tier 2 signals shall be eligible for entry.

| Tier | Criteria | Entry Allowed |
|------|----------|---------------|
| Tier 1 — Confirmed | EMA cross or pullback + volume breakout + ADX ≥ 25 + RSI 40–65 | Yes |
| Tier 2 — Qualified | EMA cross or pullback + (volume breakout OR ADX ≥ 25) + RSI 40–68 | Yes |
| Tier 3 — Marginal | EMA cross or pullback only, no volume or ADX confirmation | No |
| Tier 4 — Weak | Generic bullish EMA state | No |

The tier is computed from the signal dictionary and is independent of the raw numeric score.

---

## 4. Scoring Model Calibration

### 4.1 Score Threshold Normalisation

The current `effective_score_threshold` property scales the threshold by 0.70 when fundamentals are excluded. This is correct in principle. However, the resulting effective threshold of 42/70 is too permissive.

**Requirement:** When `include_fundamentals = false`, the recommended minimum score threshold exposed in the UI shall be 50 (effective 35/70), but the **documentation** shall explicitly state that scores below 45 effective are statistically low-confidence. The default threshold shall be raised from 60 → **70** (effective 49/70) to filter out signals that earn points only via generic EMA alignment.

---

### 4.2 ADX Minimum Raise

Current default `min_adx = 20.0`. Trades with ADX 20–25 show consistently higher stop-loss rates.

**Requirement:** The default `min_adx` shall be raised from 20.0 to **25.0**. The backtest configuration UI shall show ADX = 25 as the default.

**Rationale:** ADX below 25 indicates a ranging/trendless market. The EMA scoring system is a trend-following system; signals in trendless markets have low reliability.

---

### 4.3 RSI Scoring Granularity (Scoring Model Only)

The RSI sub-score currently awards 3 points for RSI > 50 (the "bullish_strong" case). This rewards any stock that has trended up recently, including overbought conditions.

**Requirement:** RSI scoring shall be modified as follows:

| RSI Condition | Current Pts | New Pts | Rationale |
|---------------|-------------|---------|-----------|
| Recovery from oversold (< 30) + EMA cross | 15 | 15 | Unchanged — high reward event |
| RSI crosses above 50 | 10 | 10 | Unchanged — momentum shift |
| RSI 50–65 (bullish, not extended) | 3 | 5 | Slightly reward optimal entry zone |
| RSI 65–68 | 3 | 2 | Partial credit — extended but not disqualified |
| RSI > 68 | 3 → 0 via entry gate | 0 | Disqualified at entry gate level |

---

## 5. Exit Strategy Improvements

### 5.1 Trailing Stop Activation

The current run had `trailing_stop_pct = 0.0` (disabled). The exit breakdown shows 92 trades (40%) held to the full holding period and returned an average below expected because winning momentum was not protected.

**Requirement:** A trailing stop mechanism shall be enabled by default with:

- **Activation threshold:** Trailing stop activates only after the trade has gained ≥ 1× ATR from entry (i.e., the trade is profitable by at least one ATR unit)
- **Trailing distance:** Trail at 1.5× ATR from the highest close since activation
- **Behaviour before activation:** Hard stop loss (2× ATR below entry) remains active as before

This is distinct from the existing `trailing_stop_pct` (percentage-based). A new `use_atr_trailing_stop` flag shall control this behaviour.

---

### 5.2 Partial Exit at First Target

The current system exits 100% of the position at the target. With ATR-based targets (entry + 2.5× ATR × stop_distance), this means a single price event captures the full gain.

**Requirement:** When `use_atr_stops = true`, the engine shall support a two-target exit:

- **Target 1 (T1):** At 1.5× RR — exit 50% of the position
- **Target 2 (T2):** At 2.5× RR — exit remaining 50%

After T1 is hit, the stop for the remaining position shall be moved to breakeven (entry price).

This is a configuration flag: `use_partial_exits: bool = False` (off by default, opt-in).

---

### 5.3 Holding Period Reduction for Losing Trades

92 trades (40%) were held to the full 20-day holding period. Among holding-period exits, many had negative returns. This suggests the model is holding through reversals instead of cutting based on signal invalidation.

**Requirement:** An **early exit on signal invalidation** rule shall be added: if after entry, the daily EMA signal drops to `bearish` (EMA5 < EMA13 < EMA26) for two consecutive bars, the position shall be exited at the next open regardless of holding period remaining.

This is controlled by a flag: `use_signal_invalidation_exit: bool = False` (opt-in).

---

## 6. Risk Management Specifications

### 6.1 Volatility-Sized Positions (Default On)

Current run used flat ₹12,000 per trade. Flat sizing creates asymmetric risk: a high-ATR small-cap trade and a low-ATR large-cap trade risk vastly different rupee amounts.

**Requirement:** `use_volatility_sizing` shall be `true` by default with:

- `risk_per_trade_pct = 1.0` — risk 1% of starting capital per trade (₹10,000 on a ₹10L portfolio)
- `max_position_pct = 10.0` — cap at 10% of capital
- Position size = `risk_amount / (atr_multiplier × ATR)`

---

### 6.2 Maximum Concurrent Positions

The current run had `max_concurrent_positions = 0` (unlimited). With 350 symbols, this allows unrealistic concentration of exposure during volatile periods.

**Requirement:** The default `max_concurrent_positions` shall be **15**. This limits portfolio exposure to approximately 15 × ₹10,000 risk = ₹1,50,000 (15% of capital at risk simultaneously), which is reasonable for a ₹10L portfolio.

---

### 6.3 Sector Concentration Cap

**Requirement:** The default `max_sector_positions` shall be **4**. No more than 4 simultaneous positions shall be held in any single GICS sector.

---

## 7. Backtest Engine Integrity Requirements

### 7.1 Signal Date vs Entry Date Reporting

**Requirement:** The trade record shall explicitly store and report `signal_date` (the bar that triggered) and `entry_date` (the next bar's open), and these must never be the same date. The engine shall assert this invariant during trade construction.

---

### 7.2 Benchmark Slicing

**Requirement:** Benchmark return shall be computed over the exact date range spanned by actual trades (first entry date → last exit date), not the full configured date range. This ensures the benchmark comparison is apples-to-apples.

---

### 7.3 Minimum Trade Count Warning

**Requirement:** If `total_trades < 100`, the API response shall include a `low_sample_warning: true` flag in the metrics object, and the UI shall display a prominent warning. Statistical confidence in win rate, Sharpe, and profit factor requires at minimum 100 trades.

---

## 8. Scoring Model Audit Findings (Non-Breaking)

The following are observed inconsistencies between `scorer.py` and `engine.py`'s `_score_bar_from_precomputed` that do not affect correctness but should be aligned:

| Component | scorer.py | engine.py | Action |
|-----------|-----------|-----------|--------|
| MACD cap logic | Awards 8 pts when fresh EMA cross and MACD cross coincide | Same | No change |
| RSI window | `tail(5)` for oversold check | `iloc[max(0, i-4): i+1]` — equivalent | Confirm alignment |
| Momentum periods | Uses -22, -64, -127, -253 | Uses -21, -63, -126, -252 | Standardise to one set |
| ADX scoring | Identical | Identical | No change |

The momentum period discrepancy (22 vs 21 days for 1-month) is minor but should be standardised. The specification requires momentum periods of: 1M = 21 bars, 3M = 63 bars, 6M = 126 bars, 12M = 252 bars (trading days).

---

## 9. New Default Configuration (Recommended)

The following configuration shall be the new recommended default for backtesting:

```
score_threshold:             70      (was 60; effective 49/70 without fundamentals)
holding_days:                20      (unchanged)
stop_loss_pct:               7.0     (unused when use_atr_stops=true)
use_atr_stops:               true    (unchanged)
atr_multiplier:              2.0     (unchanged)
risk_reward_ratio:           2.5     (unchanged)
require_volume_breakout:     true    (was false)
use_regime_filter:           true    (unchanged)
require_weekly_confirmation: true    (unchanged)
min_adx:                     25.0    (was 20.0)
include_fundamentals:        false   (unchanged)
use_volatility_sizing:       true    (was false)
risk_per_trade_pct:          1.0     (unchanged)
max_position_pct:            10.0    (unchanged)
max_concurrent_positions:    15      (was 0)
max_sector_positions:        4       (was 0)
use_atr_trailing_stop:       true    (new, default on)
use_partial_exits:           false   (new, default off)
use_signal_invalidation_exit:false   (new, default off)
```

---

## 10. Success Criteria

A revised backtest run using the above defaults over the same date range (2024-01-01 → 2026-05-17) and same symbol universe shall demonstrate:

| Metric | Current | Target |
|--------|---------|--------|
| Win Rate | 36.6% | ≥ 50% |
| Profit Factor | 0.956 | ≥ 1.5 |
| Avg Return % | −0.19% | ≥ 2.0% |
| Sharpe Ratio | −0.17 | ≥ 0.5 |
| Total Return | −0.52% | ≥ 12% |
| vs Benchmark | −9.3% alpha | ≥ +5% alpha |
| Stop Loss Rate | 47% of exits | ≤ 35% of exits |