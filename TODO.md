# Backtest Performance Optimization Progress

- [x] **Task 1: Vectorize Core TA Components in `TechnicalStrategy`**
  - [x] Step 1: Create unit test for vectorized components
  - [x] Step 2: Implement vectorized components in `calculate_indicators`
  - [x] Step 3: Update `evaluate` to use pre-computed columns
- [x] **Task 2: Vectorize Signal Logic in `TechnicalStrategy`**
  - [x] Step 1: Add `calculate_signals` method
  - [x] Step 2: Commit changes
- [ ] **Task 3: Optimize `backtest/engine.py`**
  - [ ] Step 1: Update `_compute_all_indicators` to include signals
  - [ ] Step 2: Refactor `build_mtf_state_map` to be vectorized
  - [ ] Step 3: Optimize `simulate_trades` loop
- [ ] **Task 4: Verification & Benchmarking**
  - [ ] Step 1: Create performance benchmark
  - [ ] Step 2: Run existing tests
  - [ ] Step 3: Final check and commit
