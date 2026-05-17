# Technical Specification: Multi-Timeframe Entry Confirmation

**Version:** 1.0  
**Status:** Draft  
**Scope:** `app/backtest/engine.py`, `app/routers/backtest.py`

---

## Background

The backtest engine currently generates entry signals exclusively from Daily OHLCV scoring. Weekly and Monthly signals are computed by the pipeline and stored in `TechnicalSignal` for each symbol, but `simulate_trades` has no awareness of them. This allows the engine to enter trades on Daily signals that are moving counter to the prevailing Weekly or Monthly trend — a known source of low-quality entries.

This specification defines a confirmation gate that requires the Weekly timeframe to be in a bullish state at the time of a Daily signal before a trade may be entered. Monthly confirmation is available as an optional additional gate.

---

## Specification 1 — Weekly Bullish Confirmation Gate

**ID:** MTF-001  
**Priority:** Critical

### Problem

`simulate_trades` receives a list of Daily scored signal dicts and enters trades based on score threshold alone. No higher-timeframe context is considered. A Daily bullish signal in a stock whose Weekly trend is bearish (price below EMA26, RSI below 50) is a counter-trend entry and historically produces a higher stop-loss rate.

### Required Behaviour

- `simulate_trades` must accept a Weekly signal state map as an optional input parameter.
- The Weekly signal state map is a dict keyed by symbol, with a boolean value representing whether the symbol's most recent Weekly signal is bullish (`True`) or not (`False`).
- When the Weekly confirmation gate is enabled and a Weekly state map is provided, a Daily signal for a symbol must only be eligible for trade entry if the symbol's Weekly state is `True`.
- If the Weekly state map is provided but a symbol has no entry in the map, the signal must be rejected (fail-closed behaviour — absence of confirmation is treated as non-bullish).
- When the gate is disabled (via config), `simulate_trades` behaves identically to the pre-MTF baseline.
- The gate is evaluated after the score threshold check and all existing gates (200 EMA null-safety, ADX gate, volume breakout filter).

### Configuration

A new boolean field `require_weekly_confirmation` must be added to `BacktestConfig` and `BacktestRequest`:

| Field | Type | Default | Description |
|---|---|---|---|
| `require_weekly_confirmation` | bool | `True` | If true, Daily signals require the Weekly signal to be bullish. |

The default is `True` because the purpose of this feature is to eliminate counter-trend entries by default.

### Acceptance Criteria

- A Daily signal for a symbol whose Weekly state is `False` produces no trade, regardless of score.
- A Daily signal for a symbol whose Weekly state is `True` is eligible for entry (subject to all other gates).
- A symbol absent from the Weekly state map is treated as non-bullish and produces no trade.
- Setting `require_weekly_confirmation=False` disables the gate entirely and produces behaviour identical to the pre-MTF baseline for all affected signals.
- The gate has no effect when no Weekly state map is supplied to `simulate_trades`.

---

## Specification 2 — Monthly Bullish Confirmation Gate

**ID:** MTF-002  
**Priority:** High

### Problem

The Weekly gate eliminates counter-trend Daily entries within the intermediate trend. However, the Monthly trend represents the primary trend. Stocks in a Monthly downtrend can sustain multi-week Weekly recoveries that subsequently fail. An optional Monthly gate provides a second confirmation layer.

### Required Behaviour

- `simulate_trades` must accept a Monthly signal state map as an optional input parameter, structured identically to the Weekly state map.
- When the Monthly confirmation gate is enabled and a Monthly state map is provided, a Daily signal must only be eligible for entry if the symbol's Monthly state is `True`.
- The Monthly gate is applied independently of the Weekly gate. Both may be active simultaneously, in which case both must be `True` for entry.
- Fail-closed behaviour applies: a symbol absent from the Monthly state map is treated as non-bullish.
- When disabled, the Monthly gate has no effect on trade eligibility.

### Configuration

A new boolean field `require_monthly_confirmation` must be added to `BacktestConfig` and `BacktestRequest`:

| Field | Type | Default | Description |
|---|---|---|---|
| `require_monthly_confirmation` | bool | `False` | If true, Daily signals also require the Monthly signal to be bullish. |

The default is `False` because Monthly signals are slow-moving and will filter out a significant proportion of valid entries in shorter date ranges. It is available as an opt-in for longer backtests.

### Acceptance Criteria

- A Daily signal for a symbol whose Monthly state is `False` produces no trade when `require_monthly_confirmation=True`.
- A symbol absent from the Monthly state map is treated as non-bullish when the gate is enabled.
- When both Weekly and Monthly gates are active, both must be `True`; a symbol that is Weekly bullish but Monthly bearish is rejected.
- Setting `require_monthly_confirmation=False` disables the gate with no effect on other gates.

---

## Specification 3 — Weekly and Monthly State Map Construction

**ID:** MTF-003  
**Priority:** Critical

### Problem

The Weekly and Monthly state maps required by MTF-001 and MTF-002 must be derived from the OHLCV data available to the backtest engine. The state at any given Daily signal date must reflect the Weekly or Monthly signal that was valid at that point in historical time, not the current live signal stored in the database. Using current database signals would introduce look-ahead bias.

### Required Behaviour

- For each symbol processed by the backtest, the Weekly and Monthly state at a given Daily signal date must be computed from the same historical OHLCV data used for Daily scoring.
- The Weekly state on a given date is `True` if the most recently completed Weekly bar (the last Weekly bar whose end date is on or before the Daily signal date) satisfies the existing Weekly bullish definition: RSI > 50 and price above EMA26.
- The Monthly state on a given date is `True` if the most recently completed Monthly bar (the last Monthly bar whose end date is on or before the Daily signal date) satisfies the existing Monthly bullish definition: RSI > 50 and price above EMA13 or EMA26.
- The Weekly and Monthly states are pre-computed per symbol across the full backtest date range before simulation begins, not re-computed per signal date. The result is a dict mapping each bar date to a boolean state.
- The state computation reuses the existing `resample_ohlcv` utility and `calculate_technical_score` function with the appropriate timeframe argument. No new indicator logic is introduced.
- If a symbol has insufficient history for Weekly or Monthly indicator computation, the state for all dates for that symbol defaults to `False` (fail-closed).

### Acceptance Criteria

- The Weekly state used on any given Daily signal date reflects the most recently completed Weekly bar prior to or on that date, not a future bar.
- The Monthly state used on any given Daily signal date reflects the most recently completed Monthly bar prior to or on that date.
- A symbol with fewer bars than required for Weekly indicator computation has all Weekly states set to `False`.
- State computation does not query the `TechnicalSignal` database table; it derives states entirely from OHLCV data.
- The state maps are passed into `simulate_trades` as arguments; `simulate_trades` does not perform OHLCV access or resample operations internally.

---

## Specification 4 — Backtest API Schema Updates

**ID:** MTF-004  
**Priority:** High

### Problem

The two new configuration fields must be exposed in the backtest API so that users can enable or disable each confirmation gate independently when submitting a backtest request.

### Required Behaviour

- `BacktestRequest` must expose `require_weekly_confirmation` (bool, default `True`) and `require_monthly_confirmation` (bool, default `False`).
- Both fields must be passed through to `BacktestConfig` in the request handler.
- The `config` JSON stored on the `BacktestRun` database record must include both fields, so that historical runs can be inspected and reproduced.
- Field descriptions in the API schema must clearly state the default and the impact of enabling each gate (fewer trades, higher signal quality).

### Acceptance Criteria

- A `BacktestRequest` submitted with no `require_weekly_confirmation` field defaults to `True`.
- A `BacktestRequest` submitted with no `require_monthly_confirmation` field defaults to `False`.
- The serialised `config` JSON on a completed `BacktestRun` record contains both fields with the values used during that run.
- The existing `_serialize_run` function returns both fields as part of the `config` block in the API response.

---

## Specification 5 — Gate Ordering and Interaction

**ID:** MTF-005  
**Priority:** Medium

### Problem

The existing gate sequence in `simulate_trades` must be extended to include the MTF gates in a defined position relative to existing gates, to ensure consistent and predictable filtering behaviour.

### Required Behaviour

The complete gate sequence for a signal to be eligible for trade entry must be, in order:

1. Date range filter (`date_from`, `date_to`)
2. Volume breakout filter (`require_volume_breakout`)
3. Signal index validity and `last_exit_idx` guard
4. 200 EMA null-safety gate (`above_200ema` is not `True` → reject)
5. ADX trend-strength gate (`adx` < `min_adx` → reject)
6. **Weekly confirmation gate** (`require_weekly_confirmation` and Weekly state is not `True` → reject) ← new
7. **Monthly confirmation gate** (`require_monthly_confirmation` and Monthly state is not `True` → reject) ← new
8. Score threshold check (`score` ≥ `score_threshold`)
9. Regime filter on entry date (`use_regime_filter`)

The MTF gates are positioned after the existing hard gates and before the score threshold check. This ordering means the score threshold acts as a final quality filter on signals that have already passed all structural and contextual checks.

### Acceptance Criteria

- A signal rejected by the 200 EMA gate is not evaluated against the Weekly gate.
- A signal rejected by the Weekly gate is not evaluated against the Monthly gate.
- A signal rejected by a MTF gate is not evaluated against the score threshold.
- All gates remain independently configurable; disabling one gate does not affect the behaviour of any other gate.

---

## Out of Scope

The following are explicitly excluded from this specification:

- Changes to how Weekly or Monthly signals are stored in the `TechnicalSignal` table.
- Changes to the pipeline scoring logic for Weekly or Monthly timeframes.
- Use of live database `TechnicalSignal` records as the source of Weekly or Monthly state (look-ahead bias concern — see MTF-003).
- Sector-level or index-level multi-timeframe confirmation.
- UI or dashboard changes to display MTF confirmation status on individual stocks.
- Any changes to the `score_series` function or Daily scoring logic.