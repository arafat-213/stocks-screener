# Design Spec - Fix Symbol Suffix Violations in Tests

## Goal
Enforce the 'Law of the Land' regarding Indian stock symbols in the backend test suite. Specifically, all Indian stock symbols MUST have the `.NS` suffix.

## Scope
- `backend/tests/api/test_stocks_search.py`
- `backend/tests/api/test_symbol_suffix.py`
- `backend/tests/api/test_suffix_detail.py`
- `backend/tests/unit/test_new_screens.py`
- `backend/tests/unit/test_models.py`
- Any other files in `backend/tests/` identified during implementation.

## Proposed Changes

### 1. Update Model Instantiations
Change all `Stock(symbol="...")`, `TechnicalSignal(symbol="...")`, and `FundamentalCache(symbol="...")` calls to use symbols with the `.NS` suffix.

### 2. Update Assertions
Update test assertions that check for symbols, ensuring they expect the `.NS` suffix.

### 3. Update API Search/Query Tests
Ensure search queries and expected results reflect the mandatory suffix.

### 4. Symbol Mapping
- `RELIANCE` -> `RELIANCE.NS`
- `TCS` -> `TCS.NS`
- `INFY` -> `INFY.NS`
- `WIPRO` -> `WIPRO.NS`
- `RELINFRA` -> `RELINFRA.NS`
- `MARUTI` -> `MARUTI.NS`
- `HCLTECH` -> `HCLTECH.NS`
- `AAPL` -> `RELIANCE.NS` (to maintain project consistency)

## Verification Plan
- Run the modified test files using `pytest`.
- Specifically verify:
  - `pytest backend/tests/api/test_stocks_search.py`
  - `pytest backend/tests/api/test_symbol_suffix.py`
  - `pytest backend/tests/unit/test_new_screens.py`
