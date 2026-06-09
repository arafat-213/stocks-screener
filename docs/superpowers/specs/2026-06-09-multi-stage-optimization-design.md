# Design Spec: Multi-Stage "Finalist-Filter" Strategy Optimization

## Goal
Identify "anti-fragile" trading strategies that demonstrate consistent alpha across extreme market regimes (Crash, Chop, Bull) while avoiding over-optimization through multi-stage validation.

## 1. Architectural Overview
The workflow transitions from a broad **Discovery Sweep** to a narrow **Finalist Validation**, ending in a **Consolidated Trade Audit**.

### Stage 1: Discovery Sweep (In-Sample)
- **Goal:** Filter a large parameter grid to find strategies that survive stress.
- **Folds:**
    - `Fold 1 (Crash)`: 2020-02-01 to 2020-04-30 (COVID-19 Stress Test)
    - `Fold 2 (Chop)`: 2021-10-19 to 2023-03-20 (Survival Test)
    - `Fold 3 (Bull)`: 2023-03-21 to 2024-02-01 (Performance Test)
- **Primary Metric:** `Robustness Score = Mean(Sharpe) - Std(Sharpe)`
- **Constraint:** Full Universe (up to 2500 symbols).

### Stage 2: Finalist Validation (Out-of-Sample)
- **Goal:** Verify that Top 5 finalists aren't "curve-fitted" to the Discovery folds and haven't suffered structural decay in the most recent market.
- **Selection:** Automatic promotion of Top 5 configs by Robustness Score.
- **Validation Folds:**
    - `Fold 4 (Recovery)`: 2020-05-01 to 2021-10-18
    - `Fold 5 (Post-Bull)`: 2024-02-02 to 2025-06-01
    - `Fold 6 (Recent/Current)`: 2025-06-02 to 2026-06-09 (Recency Stress Test)
- **Failure Condition:** If a finalist has a negative Sharpe in *any* validation fold, it is flagged as "Fragile."

### Stage 2.5: The "Whole Story" Stress Test
- **Goal:** Analyze path dependency, true peak-to-trough drawdown, and compounding behavior.
- **Action:** Run one continuous backtest from `2020-02-01` to `Today` for all Stage 2 survivors.
- **Key Metrics:**
    - **True Max Drawdown:** The absolute largest equity drop over the entire 6.5-year history.
    - **Compounding Alpha:** How the strategy scales capital over a long horizon without resetting.
    - **Regime Hand-offs:** Performance during the specific weeks where market regimes shift.

### Stage 3: Consolidated Audit
- **Goal:** Deep-dive into the trade-level mechanics of the survivors.
- **Action:** Merge trades from ALL 6 segmented folds + the Stage 2.5 continuous run into a single analytical dataset.
- **Metrics:**
    - True Capital Utilization (using DB `position_size`).
    - Sector-wise Alpha distribution.
    - Exit reason breakdown (Stop Loss vs. Holding Period vs. Signal Invalidation).
    - Monthly PnL Heatmap across the entire 2020-2026 period.

## 2. Technical Implementation

### Script: `backend/parameter_sweep.py`
- Refactor `_run_one` to handle Stage 1 logic.
- Add `run_validation` function for Stage 2.
- Add `run_continuous_test` for Stage 2.5.
- Implement the `Mean - Std` robustness metric.
- Update `MAX_CONCURRENT` and `DEFAULTS` for production-level runs.
- Remove `symbol_limit` to trigger full universe backtests.

### Script: `verify_backtest_trades.py`
- Refactor `analyze_trades` to support multiple `run_ids`.
- Remove capital utilization fallbacks; strictly use `position_size`.
- Enhance the Monthly Returns Heatmap to span multiple years correctly.

## 3. Success Criteria
- [ ] Sweep script successfully backfills missing 2020 data for the universe.
- [ ] Top 5 finalists are automatically identified and validated.
- [ ] Final report provides a consolidated view of all trades across the full 4-year period.
- [ ] Robustness Score successfully penalizes strategies with high variance across regimes.

## 4. Risks & Mitigations
- **Risk:** Backfilling 2500 symbols from 2020 might hit `yfinance` rate limits.
- **Mitigation:** The engine's signal cache will minimize redundant requests once data is locally cached.
- **Risk:** Heavy DB load during trade consolidation.
- **Mitigation:** Use SQLAlchemy `bulk_insert_mappings` (already in engine) and efficient trade queries.
