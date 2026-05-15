# Design Spec: Chart Aware Trade setup Design

---

# **Part 1: Feature Specification — Chart-Aware Trade Setups**

### **Goal**

Compute entry zones, ATR-based stops, and R-multiple targets from actual chart structure. Embed these in every stock response so every screen and card is immediately actionable.

### **The Core Problem**

The current system produces a score and `is_bullish`. Neither tells a user what to do. The backtest exposed why this matters: with flat-percentage stops, a 5% stop on a volatile midcap and a stable largecap are treated identically, which is wrong. Win rates cluster around 33% across all configs because trade management has no relationship to the chart.

The fix is to compute stop and target from the chart's own volatility (ATR) and structure (EMA levels, resistance). This data is already in the pipeline — it just isn't surfaced.

### **What Gets Built (High-Level)**

1. **New Stored Fields**: Four new EMA price levels (EMA 5, 13, 20, 26) will be permanently stored during the pipeline run on the `TechnicalSignal` table.
2. **Setup Engine**: A pure, mathematically driven function (`compute_trade_setup()`) that calculates trade parameters with zero database or I/O overhead.
3. **API Response Augmentation**: A new `setup` object will be embedded into dashboard results, screener results, and individual stock details.

### **System Architecture & Data Flow**

**1. Pipeline run (4:35 PM)**

* `calculate_technical_score()` executes.
* Existing fields (`atr`, `resistance_level`, `ema_signal`, `close_price`) are combined with new fields (`ema5_level`, `ema13_level`, `ema20_level`, `ema26_level`).
* All are stored to the `TechnicalSignal` table.

**2. API request (Any time)**

* DB query fetches the `TechnicalSignal` row.
* `compute_trade_setup(signal)` is called at serialization time.
* Calculated payload is embedded as `"setup"` in the JSON response.

### **Business Logic & Rules**

#### **1. Setup Type Selection (Priority Order)**

| Condition | Assigned Setup Type |
| --- | --- |
| `ema_signal == "bullish_cross"` | `ema_crossover` |
| `ema_signal == "bullish_pullback"` | `pullback_to_ema20` |
| `pct_from_resistance` between -3.0 and 0.0 | `resistance_breakout` |
| *Else (Fallback)* | `trend_continuation` |

#### **2. Entry Zones**

| Setup Type | Entry Low | Entry High | Rationale |
| --- | --- | --- | --- |
| `ema_crossover` | Price × 0.995 | Price × 1.005 | Enter near current price, cross is fresh |
| `pullback_to_ema20` | EMA20 × 0.99 | EMA20 × 1.01 | Enter around EMA20 level |
| `resistance_breakout` | Resistance × 1.002 | Resistance × 1.01 | Enter just above broken resistance |
| `trend_continuation` | Price × 0.99 | Price × 1.01 | Generic ±1% around close |

#### **3. Stop Loss Calculation**

* **Entry Midpoint:** `entry_mid = (entry_low + entry_high) / 2`
* **Stop Loss Level:** `stop_loss = entry_mid - (2.0 × atr)`
* **Stop Basis Tag:** `"2× ATR below entry"`
*(Note: ATR adapts to each stock's volatility. A calm largecap might produce a 2.5% stop; a volatile smallcap might produce an 8% stop. Both are correct for their respective charts.)*

#### **4. Target Calculation (R-Multiples)**

* **Risk Per Share:** `risk = entry_mid - stop_loss`
* **Target 1 (1.5R):** `target_1 = entry_mid + (1.5 × risk)`
* **Target 2 (2.5R):** `target_2 = entry_mid + (2.5 × risk)`

#### **5. Guard Conditions**

The setup engine must return `null`/`None` if **any** of the following fail:

* `atr` is null or zero.
* `close_price` is null.
* `risk <= 0` (invalidates the trade, stop would be above entry).
* *Specific to `pullback_to_ema20`:* If `ema20_level` is null, fall through to `trend_continuation`.
* *Specific to `resistance_breakout`:* If `resistance_level` is null, fall through to `trend_continuation`.

### **Output Data Contract**

When successful, the `setup` field embedded in APIs will adhere to this shape:

```json
{
  "setup_type": "pullback_to_ema20",
  "entry_zone": {
    "low": 892.40,
    "high": 912.60
  },
  "stop_loss": 843.20,
  "stop_basis": "2× ATR below entry",
  "targets": [
    { "level": 986.30, "rr": 1.5 },
    { "level": 1043.50, "rr": 2.5 }
  ],
  "atr": 29.43,
  "risk_per_share": 59.30
}

```
---