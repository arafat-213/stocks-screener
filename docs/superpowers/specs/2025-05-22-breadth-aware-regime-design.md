# Design Spec: Breadth-Aware Smart Regime Overrides

## Status
- **Date:** 2025-05-22
- **Status:** Approved (Autonomous)

## Context
The current regime engine in the backtest system uses benchmark (Nifty 50) technical indicators (RSI, ADX, Price vs EMA200) to determine market regimes (BULL, NEUTRAL, BEAR). These regimes scale position sizes to manage risk. However, low ADX environments are often ambiguous. "Market Breadth" — the percentage of stocks trading above their long-term trend (EMA 200) — provides a powerful confirmation signal that can override benchmark trend indicators.

## Requirements
- Incorporate `breadth_map` into the `_build_regime_map` logic.
- Implement "Smart Overrides" for low-ADX (< 15.0) environments.
- High breadth (> 60%) in low-ADX market should signal a "Hidden Bull".
- Low breadth (< 40%) in low-ADX market should signal "Dangerous Sideways" (BEAR).

## Architecture

### Components
1. **Breadth Calculation:** Use existing `_calculate_breadth_map` which computes % of stocks above EMA200 from the backtest universe.
2. **Regime Engine:** Updated `_build_regime_map` function in `backend/app/backtest/engine.py`.

### Logic Flow
In `_build_regime_map`, for each date:
1. Fetch `breadth` from `breadth_map`.
2. Check `adx` against `config.regime_adx_floor`.
3. If `adx` is below floor:
   - If `breadth > 60.0` -> `potential_regime = 2` (BULL)
   - Else if `breadth < config.min_market_breadth_pct` -> `potential_regime = 0` (BEAR)
   - Else -> `potential_regime = 1` (NEUTRAL)
4. If `adx` is above floor, use standard RSI/EMA200 logic.
5. Apply existing confirmation/hysteresis logic to determine the `current_regime`.

## Implementation Plan

### Step 1: `_build_regime_map` update
- Modify signature to accept `breadth_map`.
- Inject the override logic before the standard RSI/Price checks.

### Step 2: `run_backtest` integration
- Call `_calculate_breadth_map(all_dfs)` after signals/indicators are computed.
- Pass the result to `_build_regime_map`.

## Verification
- Unit test for `_build_regime_map` with mocked data covering the three override cases.
- Regression check on `run_backtest` flow.
