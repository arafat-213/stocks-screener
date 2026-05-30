# Pipeline Orchestrator Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the pipeline fetcher and orchestrator to support indices, track funnel counts, capture price snapshots, and implement market snapshot logic.

**Architecture:**
- Update `fetch_stock_data` in `fetcher.py` to allow symbols without `.NS` suffix.
- Track survivor counts at each tier in `run_pipeline`.
- Calculate price and percentage change from historical data for daily signals.
- Fetch index data (e.g., ^NSEI) and store as a market snapshot.

**Tech Stack:** Python, SQLAlchemy, yfinance, pandas.

---

### Task 1: Update fetch_stock_data in fetcher.py

**Files:**
- Modify: `backend/app/pipeline/fetcher.py`

- [ ] **Step 1: Write failing test for index fetching**
Add a test in a new file `backend/tests/unit/test_fetcher.py` that tries to fetch data for `^NSEI` and fails if it appends `.NS`.

```python
from app.pipeline.fetcher import fetch_stock_data
from unittest.mock import patch, MagicMock

@patch('yfinance.Ticker')
def test_fetch_stock_data_index(mock_ticker):
    mock_instance = MagicMock()
    mock_ticker.return_value = mock_instance
    mock_instance.history.return_value = MagicMock(empty=False)

    fetch_stock_data("^NSEI", append_ns=False)
    mock_ticker.assert_called_with("^NSEI")

    fetch_stock_data("RELIANCE", append_ns=True)
    mock_ticker.assert_called_with("RELIANCE.NS")
```

- [ ] **Step 2: Run test and verify failure**
Run: `pytest backend/tests/unit/test_fetcher.py`
Expected: TypeError (unexpected keyword argument 'append_ns')

- [ ] **Step 3: Implement signature change in fetcher.py**

```python
def fetch_stock_data(symbol: str, append_ns: bool = True, period: str = "1y"):
    try:
        ticker_symbol = f"{symbol}.NS" if append_ns else symbol
        ticker = yf.Ticker(ticker_symbol)
        # ... rest same
```

- [ ] **Step 4: Run test and verify pass**
Run: `pytest backend/tests/unit/test_fetcher.py`

- [ ] **Step 5: Commit**
```bash
git add backend/app/pipeline/fetcher.py backend/tests/unit/test_fetcher.py
git commit -m "fetcher: support non-NS symbols for indices"
```

### Task 2: Track funnel counts in orchestrator.py

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Update existing test to check for counts**
In `backend/tests/unit/test_orchestrator.py`, assert that `run.tier1_count` and `run.tier2_count` are populated.

```python
    # ... after run_pipeline(mock_db)
    # Get the run object that was added to the mock db
    run = mock_db.add.call_args_list[0][0][0]
    assert run.tier1_count == 1 # RELIANCE survived T1
    assert run.tier2_count == 1 # RELIANCE survived T2
```

- [ ] **Step 2: Run test and verify failure**
Run: `pytest backend/tests/unit/test_orchestrator.py`
Expected: AssertionError

- [ ] **Step 3: Update orchestrator.py to track counts**

```python
        # 1. Tier 1 Screening
        # ...
        run.tier1_count = len(tier1_survivors)
        db.commit()

        # ...
        # 3. Final Filtering & Scoring
        tier2_survivors_count = 0
        for symbol in tier1_survivors:
            # ...
            # Tier 2 Filters
            if not cache.profitability_streak_passed or not cache.de_check_passed:
                continue

            tier2_survivors_count += 1
            # ...

        run.tier2_count = tier2_survivors_count
        db.commit()
```

- [ ] **Step 4: Run test and verify pass**
Run: `pytest backend/tests/unit/test_orchestrator.py`

- [ ] **Step 5: Commit**
```bash
git add backend/app/pipeline/orchestrator.py backend/tests/unit/test_orchestrator.py
git commit -m "pipeline: track funnel counts in PipelineRun"
```

### Task 3: Capture price snapshots in scoring loop

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Update existing test to check for price fields**
In `backend/tests/unit/test_orchestrator.py`, verify `signal.close_price` and `signal.price_change_pct` for 'D' timeframe.

```python
    # Find the technical signal for timeframe 'D'
    # This might require mocking the TechnicalSignal constructor or capturing calls to db.add
```

- [ ] **Step 2: Run test and verify failure**

- [ ] **Step 3: Update orchestrator.py to capture price data**

```python
                # ... inside tf loop, before TechnicalSignal creation
                close_price = None
                price_change_pct = None
                if tf == 'D' and len(working_df) >= 2:
                    close_price = float(working_df['Close'].iloc[-1])
                    prev_close = float(working_df['Close'].iloc[-2])
                    price_change_pct = ((close_price - prev_close) / prev_close) * 100

                # ... when creating/updating signal
                signal.close_price = close_price
                signal.price_change_pct = price_change_pct
```

- [ ] **Step 4: Run test and verify pass**

- [ ] **Step 5: Commit**
```bash
git add backend/app/pipeline/orchestrator.py
git commit -m "pipeline: capture price snapshots in daily signals"
```

### Task 4: Implement Market Snapshot logic

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Write test for market snapshot**
Add a test case in `backend/tests/unit/test_orchestrator.py` (or new file) that verifies `MarketSnapshot` is upserted at the end of `run_pipeline`.

- [ ] **Step 2: Run test and verify failure**

- [ ] **Step 3: Implement market snapshot logic in run_pipeline**

```python
        # 5. Market Snapshot
        try:
            # Use last signal_date or today
            snap_date = datetime.date.today() # Better to derive from hist data if possible
            idx_symbol = "^NSEI"
            idx_hist, _ = fetch_stock_data(idx_symbol, append_ns=False, period="5d")
            if idx_hist is not None and len(idx_hist) >= 2:
                idx_close = float(idx_hist['Close'].iloc[-1])
                idx_prev = float(idx_hist['Close'].iloc[-2])
                idx_change = ((idx_close - idx_prev) / idx_prev) * 100

                from app.db.models import MarketSnapshot
                snapshot = MarketSnapshot(
                    date=snap_date,
                    symbol=idx_symbol,
                    close=idx_close,
                    change_pct=idx_change
                )
                db.merge(snapshot)
                db.commit()
        except Exception as e:
            logger.warning(f"Failed to capture market snapshot: {e}")
```

- [ ] **Step 4: Run test and verify pass**

- [ ] **Step 5: Commit**
```bash
git add backend/app/pipeline/orchestrator.py
git commit -m "pipeline: implement market snapshot logic"
```
