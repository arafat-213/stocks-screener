# Refined Stock Screener Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a tiered fundamental screener with sectoral D/E logic, 3-year profitability streak checks, and a versioned caching system to keep daily runs fast.

**Architecture:** Tiered filtering (Fast In-Memory -> Deep Cached) to optimize yfinance API usage. Sector-relative constants for Debt/Equity limits. Versioned SQLite cache for deep fundamental checks.

**Tech Stack:** Python, FastAPI, SQLAlchemy (Alembic), yfinance, pandas.

---

### Task 1: Update Database Models & Migrations

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/migrations/versions/<timestamp>_add_fundamental_cache.py` (via alembic)

- [ ] **Step 1: Update `FundamentalData` model and add `FundamentalCache`**
Modify `backend/app/db/models.py`:
```python
class FundamentalData(Base):
    __tablename__ = "fundamental_data"
    date = Column(DateTime, default=datetime.datetime.utcnow)
    symbol = Column(String)
    pe = Column(Float, nullable=True)
    pb = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    debt_equity = Column(Float, nullable=True)
    eps_growth = Column(Float, nullable=True)
    promoter_holding = Column(Float, nullable=True)
    pledged_percent = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    __table_args__ = (PrimaryKeyConstraint('date', 'symbol'),)

class FundamentalCache(Base):
    __tablename__ = "fundamental_cache"
    symbol = Column(String, primary_key=True)
    profitability_streak_passed = Column(Boolean)
    de_ratio = Column(Float)
    de_check_passed = Column(Boolean)
    pledged_data_missing = Column(Boolean, default=False) # Added for flagging
    sector = Column(String)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)
    cache_version = Column(Integer, default=1)
```

- [ ] **Step 2: Generate and run Alembic migration**
Run: `cd backend && alembic revision --autogenerate -m "add_fundamental_cache_and_extra_fields"`
Expected: New migration file created.
Run: `alembic upgrade head`
Expected: Database schema updated.

- [ ] **Step 3: Commit**
```bash
git add backend/app/db/models.py backend/migrations/versions/
git commit -m "db: add fundament# Refined Stock Screener Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a tiered fundamental screener with sectoral D/E logic, 3-year profitability streak checks, and a versioned caching system to keep daily runs fast.

**Architecture:** Tiered filtering (Fast In-Memory -> Deep Cached) to optimize yfinance API usage. Sector-relative constants for Debt/Equity limits. Versioned SQLite cache for deep fundamental checks.

**Tech Stack:** Python, FastAPI, SQLAlchemy (Alembic), yfinance, pandas.

---

### Task 1: Update Database Models & Migrations

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/migrations/versions/<timestamp>_add_fundamental_cache.py` (via alembic)

- [ ] **Step 1: Update `FundamentalData` model and add `FundamentalCache`**
Modify `backend/app/db/models.py`:
```python
class FundamentalData(Base):
    __tablename__ = "fundamental_data"
    date = Column(DateTime, default=datetime.datetime.utcnow)
    symbol = Column(String)
    pe = Column(Float, nullable=True)
    pb = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    debt_equity = Column(Float, nullable=True)
    eps_growth = Column(Float, nullable=True)
    promoter_holding = Column(Float, nullable=True)
    pledged_percent = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    __table_args__ = (PrimaryKeyConstraint('date', 'symbol'),)

class FundamentalCache(Base):
    __tablename__ = "fundamental_cache"
    symbol = Column(String, primary_key=True)
    profitability_streak_passed = Column(Boolean)
    de_ratio = Column(Float)
    de_check_passed = Column(Boolean)
    pledged_data_missing = Column(Boolean, default=False) # Added for flagging
    sector = Column(String)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)
    cache_version = Column(Integer, default=1)
```

- [ ] **Step 2: Generate and run Alembic migration**
Run: `cd backend && alembic revision --autogenerate -m "add_fundamental_cache_and_extra_fields"`
Expected: New migration file created.
Run: `alembic upgrade head`
Expected: Database schema updated.

- [ ] **Step 3: Commit**
```bash
git add backend/app/db/models.py backend/migrations/versions/
git commit -m "db: add fundamental_cache with flagging and update fundamental_data models"
```

---

### Task 2: Implement Tier 1 Fast Filters

**Files:**
- Modify: `backend/app/pipeline/screener.py`
- Test: `backend/tests/unit/test_screener_tier1.py`

- [ ] **Step 1: Define Constants and Tier 1 logic**
Modify `backend/app/pipeline/screener.py`:
```python
CURRENT_SCREENER_VERSION = 1

def passes_tier1_fast_filters(info: dict) -> tuple[bool, bool]:
    """Returns (passes_filter, should_flag_missing_pledge)"""
    if not info: return False, False

    # 1. Market Cap > ₹500 Cr (~$6M USD)
    mcap = info.get('marketCap', 0) or 0
    if mcap < 6_000_000: return False, False

    # 2. P/E (0 < pe < 150)
    pe = info.get('trailingPE') or info.get('forwardPE')
    if pe is None or pe <= 0 or pe > 150: return False, False

    # 3. ROE > 15%
    roe = info.get('returnOnEquity', 0) or 0
    if roe < 0.15: return False, False

    # 4. Promoter Pledge < 20%
    pledged = info.get('pledgedPercent')
    flag_missing = False
    if pledged is None:
        flag_missing = True
    elif pledged > 0.20:
        return False, False

    # 5. Liquidity (20-day avg vol > 500k)
    avg_vol = info.get('averageVolume', 0) or 0
    if avg_vol < 500_000: return False, False

    return True, flag_missing
```

- [ ] **Step 2: Write unit tests for Tier 1**
Create `backend/tests/unit/test_screener_tier1.py`:
```python
from app.pipeline.screener import passes_tier1_fast_filters

def test_tier1_passes_valid_stock():
    info = {
        'marketCap': 60_000_000, # USD
        'trailingPE': 25,
        'returnOnEquity': 0.18,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000
    }
    passed, flag = passes_tier1_fast_filters(info)
    assert passed is True
    assert flag is False

def test_tier1_flags_missing_pledge():
    info = {
        'marketCap': 60_000_000,
        'trailingPE': 25,
        'returnOnEquity': 0.18,
        'pledgedPercent': None,
        'averageVolume': 1_000_000
    }
    passed, flag = passes_tier1_fast_filters(info)
    assert passed is True
    assert flag is True

def test_tier1_rejects_loss_making():
    info = {'trailingPE': -5}
    passed, _ = passes_tier1_fast_filters(info)
    assert passed is False
```

- [ ] **Step 3: Run tests and commit**
Run: `pytest backend/tests/unit/test_screener_tier1.py`
Expected: PASS
```bash
git add backend/app/pipeline/screener.py backend/tests/unit/test_screener_tier1.py
git commit -m "feat: implement stage 1 tier 1 fast filters with USD mcap and flagging"
```

---

### Task 3: Implement Sector-Relative D/E and 3-Year Profitability

**Files:**
- Modify: `backend/app/pipeline/screener.py`
- Test: `backend/tests/unit/test_screener_tier2.py`

- [ ] **Step 1: Implement Tier 2 logic with robust row retrieval**
Modify `backend/app/pipeline/screener.py`:
```python
DE_LIMITS = {
    "Financial Services": 10,
    "Insurance": 8,
    "Real Estate": 4,
    "Utilities": 3,
    "default": 2
}

def get_row(df, keywords):
    for idx in df.index:
        if any(k.lower() in str(idx).lower() for k in keywords):
            return df.loc[idx]
    return None

def check_profitability_streak(financials) -> bool:
    """Checks if Net Income and Revenue are positive for last 3 years."""
    try:
        if financials.empty or len(financials.columns) < 3: return False

        ni_row = get_row(financials, ['net income', 'net earnings'])
        rev_row = get_row(financials, ['total revenue', 'revenue', 'total operating revenue'])

        if ni_row is None or rev_row is None: return False

        # yf returns reverse chrono: iloc[0:3] are last 3 years
        for i in range(3):
            if ni_row.iloc[i] <= 0 or rev_row.iloc[i] <= 0: return False
        return True
    except Exception:
        return False
```

- [ ] **Step 2: Write tests for profitability streak with mocks**
Create `backend/tests/unit/test_screener_tier2.py`:
```python
import pandas as pd
import pytest
from app.pipeline.screener import check_profitability_streak

def test_streak_passes_3yr_positive():
    data = {
        '2025': [100, 1000],
        '2024': [80, 900],
        '2023': [60, 800]
    }
    df = pd.DataFrame(data, index=['Net Income', 'Total Revenue'])
    assert check_profitability_streak(df) is True

def test_streak_fails_if_one_year_negative():
    data = {
        '2025': [100, 1000],
        '2024': [-5, 900],
        '2023': [60, 800]
    }
    df = pd.DataFrame(data, index=['Net Income', 'Total Revenue'])
    assert check_profitability_streak(df) is False

def test_streak_fails_if_less_than_3yr_data():
    data = {'2025': [100, 1000]}
    df = pd.DataFrame(data, index=['Net Income', 'Total Revenue'])
    assert check_profitability_streak(df) is False
```

- [ ] **Step 3: Run tests and commit**
Run: `pytest backend/tests/unit/test_screener_tier2.py`
Expected: PASS
```bash
git add backend/app/pipeline/screener.py backend/tests/unit/test_screener_tier2.py
git commit -m "feat: add robust profitability streak logic and unit tests"
```

---

### Task 4: Implement Tiered Caching & Batching

**Files:**
- Modify: `backend/app/pipeline/screener.py`
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Implement `fetch_in_batches` and Caching Orchestration**
Modify `backend/app/pipeline/screener.py`:
```python
import time
import yfinance as yf

def fetch_and_cache_deep_fundamentals(symbols, db_session):
    """Fetch 3yr financials in batches and update cache."""
    batch_size = 50
    delay = 1.0
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        for symbol in batch:
            try:
                ticker = yf.Ticker(symbol)
                financials = ticker.financials
                info = ticker.info

                streak = check_profitability_streak(financials)
                de = info.get('debtToEquity', 100) # Default to failing
                sector = info.get('sector', 'default')
                limit = DE_LIMITS.get(sector, DE_LIMITS['default'])

                # Update FundamentalCache row here...
            except Exception as e:
                print(f"Failed {symbol}: {e}")
        time.sleep(delay)
```

- [ ] **Step 2: Update Orchestrator**
Modify `orchestrator.py` to:
1. Run Tier 1 on all symbols.
2. Identify which Tier 1 survivors need cache refresh.
3. Call `fetch_and_cache_deep_fundamentals` for those.
4. Filter out any that fail Tier 2 (from cache or fresh fetch).

---

### Task 5: Refine Stage 2 Scoring

**Files:**
- Modify: `backend/app/pipeline/scorer.py`

- [ ] **Step 1: Align P/E and Pledge scoring with spec**
```python
def calculate_fundamental_score(info: dict) -> float:
    score = 0
    pe = info.get('trailingPE') or info.get('forwardPE')

    # P/E Score (20% weight relative to 100 total, so 20 pts max)
    if pe is None: score += 0
    elif pe < 25: score += 20
    elif pe < 50: score += 15
    elif pe < 100: score += 5
    else: score -= 5 # Penalty for very expensive

    # Promoter Pledge (10% weight -> 10 pts max)
    pledged = info.get('pledgedPercent')
    if pledged is None: score += 0
    elif pledged < 0.05: score += 10
    elif pledged < 0.15: score += 5
    elif pledged < 0.20: score += 2
    else: score += 0 # Should have been filtered, but safe default

    return score
```

- [ ] **Step 2: Integrate into final score (70% Technical / 30% Fundamental)**
Modify `scorer.py` final weighted sum logic.

---

### Task 6: Final Verification & Pipeline Run

- [ ] **Step 1: Run full pipeline integration test**
- [ ] **Step 2: Verification Checklist**
    - [ ] Pipeline completes in < 5 min with warm cache (time it)
    - [ ] Pipeline completes in < 15 min on cold run
    - [ ] `fundamental_cache` has rows with correct `cache_version = 1`
    - [ ] No stock with `pe < 0` appears in `daily_scores`
    - [ ] At least one Financial Services stock present (D/E check working)
    - [ ] At least 30 stocks in top scored results
    - [ ] Verify `pledged_data_missing` flag is True for symbols with missing pledge data
al_cache with flagging and update fundamental_data models"
```

---

### Task 2: Implement Tier 1 Fast Filters

**Files:**
- Modify: `backend/app/pipeline/screener.py`
- Test: `backend/tests/unit/test_screener_tier1.py`

- [ ] **Step 1: Define Constants and Tier 1 logic**
Modify `backend/app/pipeline/screener.py`:
```python
CURRENT_SCREENER_VERSION = 1

def passes_tier1_fast_filters(info: dict) -> tuple[bool, bool]:
    """Returns (passes_filter, should_flag_missing_pledge)"""
    if not info: return False, False

    # 1. Market Cap > ₹500 Cr (~$6M USD)
    mcap = info.get('marketCap', 0) or 0
    if mcap < 6_000_000: return False, False

    # 2. P/E (0 < pe < 150)
    pe = info.get('trailingPE') or info.get('forwardPE')
    if pe is None or pe <= 0 or pe > 150: return False, False

    # 3. ROE > 15%
    roe = info.get('returnOnEquity', 0) or 0
    if roe < 0.15: return False, False

    # 4. Promoter Pledge < 20%
    pledged = info.get('pledgedPercent')
    flag_missing = False
    if pledged is None:
        flag_missing = True
    elif pledged > 0.20:
        return False, False

    # 5. Liquidity (20-day avg vol > 500k)
    avg_vol = info.get('averageVolume', 0) or 0
    if avg_vol < 500_000: return False, False

    return True, flag_missing
```

- [ ] **Step 2: Write unit tests for Tier 1**
Create `backend/tests/unit/test_screener_tier1.py`:
```python
from app.pipeline.screener import passes_tier1_fast_filters

def test_tier1_passes_valid_stock():
    info = {
        'marketCap': 60_000_000, # USD
        'trailingPE': 25,
        'returnOnEquity': 0.18,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000
    }
    passed, flag = passes_tier1_fast_filters(info)
    assert passed is True
    assert flag is False

def test_tier1_flags_missing_pledge():
    info = {
        'marketCap': 60_000_000,
        'trailingPE': 25,
        'returnOnEquity': 0.18,
        'pledgedPercent': None,
        'averageVolume': 1_000_000
    }
    passed, flag = passes_tier1_fast_filters(info)
    assert passed is True
    assert flag is True

def test_tier1_rejects_loss_making():
    info = {'trailingPE': -5}
    passed, _ = passes_tier1_fast_filters(info)
    assert passed is False
```

- [ ] **Step 3: Run tests and commit**
Run: `pytest backend/tests/unit/test_screener_tier1.py`
Expected: PASS
```bash
git add backend/app/pipeline/screener.py backend/tests/unit/test_screener_tier1.py
git commit -m "feat: implement stage 1 tier 1 fast filters with USD mcap and flagging"
```

---

### Task 3: Implement Sector-Relative D/E and 3-Year Profitability

**Files:**
- Modify: `backend/app/pipeline/screener.py`
- Test: `backend/tests/unit/test_screener_tier2.py`

- [ ] **Step 1: Implement Tier 2 logic with robust row retrieval**
Modify `backend/app/pipeline/screener.py`:
```python
DE_LIMITS = {
    "Financial Services": 10,
    "Insurance": 8,
    "Real Estate": 4,
    "Utilities": 3,
    "default": 2
}

def get_row(df, keywords):
    for idx in df.index:
        if any(k.lower() in str(idx).lower() for k in keywords):
            return df.loc[idx]
    return None

def check_profitability_streak(financials) -> bool:
    """Checks if Net Income and Revenue are positive for last 3 years."""
    try:
        if financials.empty or len(financials.columns) < 3: return False

        ni_row = get_row(financials, ['net income', 'net earnings'])
        rev_row = get_row(financials, ['total revenue', 'revenue', 'total operating revenue'])

        if ni_row is None or rev_row is None: return False

        # yf returns reverse chrono: iloc[0:3] are last 3 years
        for i in range(3):
            if ni_row.iloc[i] <= 0 or rev_row.iloc[i] <= 0: return False
        return True
    except Exception:
        return False
```

- [ ] **Step 2: Write tests for profitability streak with mocks**
Create `backend/tests/unit/test_screener_tier2.py`:
```python
import pandas as pd
import pytest
from app.pipeline.screener import check_profitability_streak

def test_streak_passes_3yr_positive():
    data = {
        '2025': [100, 1000],
        '2024': [80, 900],
        '2023': [60, 800]
    }
    df = pd.DataFrame(data, index=['Net Income', 'Total Revenue'])
    assert check_profitability_streak(df) is True

def test_streak_fails_if_one_year_negative():
    data = {
        '2025': [100, 1000],
        '2024': [-5, 900],
        '2023': [60, 800]
    }
    df = pd.DataFrame(data, index=['Net Income', 'Total Revenue'])
    assert check_profitability_streak(df) is False

def test_streak_fails_if_less_than_3yr_data():
    data = {'2025': [100, 1000]}
    df = pd.DataFrame(data, index=['Net Income', 'Total Revenue'])
    assert check_profitability_streak(df) is False
```

- [ ] **Step 3: Run tests and commit**
Run: `pytest backend/tests/unit/test_screener_tier2.py`
Expected: PASS
```bash
git add backend/app/pipeline/screener.py backend/tests/unit/test_screener_tier2.py
git commit -m "feat: add robust profitability streak logic and unit tests"
```

---

### Task 4: Implement Tiered Caching & Batching

**Files:**
- Modify: `backend/app/pipeline/screener.py`
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Implement `fetch_in_batches` and Caching Orchestration**
Modify `backend/app/pipeline/screener.py`:
```python
import time
import yfinance as yf

def fetch_and_cache_deep_fundamentals(symbols, db_session):
    """Fetch 3yr financials in batches and update cache."""
    batch_size = 50
    delay = 1.0
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        for symbol in batch:
            try:
                ticker = yf.Ticker(symbol)
                financials = ticker.financials
                info = ticker.info

                streak = check_profitability_streak(financials)
                de = info.get('debtToEquity', 100) # Default to failing
                sector = info.get('sector', 'default')
                limit = DE_LIMITS.get(sector, DE_LIMITS['default'])

                # Update FundamentalCache row here...
            except Exception as e:
                print(f"Failed {symbol}: {e}")
        time.sleep(delay)
```

- [ ] **Step 2: Update Orchestrator**
Modify `orchestrator.py` to:
1. Run Tier 1 on all symbols.
2. Identify which Tier 1 survivors need cache refresh.
3. Call `fetch_and_cache_deep_fundamentals` for those.
4. Filter out any that fail Tier 2 (from cache or fresh fetch).

---

### Task 5: Refine Stage 2 Scoring

**Files:**
- Modify: `backend/app/pipeline/scorer.py`

- [ ] **Step 1: Align P/E and Pledge scoring with spec**
```python
def calculate_fundamental_score(info: dict) -> float:
    score = 0
    pe = info.get('trailingPE') or info.get('forwardPE')

    # P/E Score (20% weight relative to 100 total, so 20 pts max)
    if pe is None: score += 0
    elif pe < 25: score += 20
    elif pe < 50: score += 15
    elif pe < 100: score += 5
    else: score -= 5 # Penalty for very expensive

    # Promoter Pledge (10% weight -> 10 pts max)
    pledged = info.get('pledgedPercent')
    if pledged is None: score += 0
    elif pledged < 0.05: score += 10
    elif pledged < 0.15: score += 5
    elif pledged < 0.20: score += 2
    else: score += 0 # Should have been filtered, but safe default

    return score
```

- [ ] **Step 2: Integrate into final score (70% Technical / 30% Fundamental)**
Modify `scorer.py` final weighted sum logic.

---

### Task 6: Final Verification & Pipeline Run

- [ ] **Step 1: Run full pipeline integration test**
- [ ] **Step 2: Verification Checklist**
    - [ ] Pipeline completes in < 5 min with warm cache (time it)
    - [ ] Pipeline completes in < 15 min on cold run
    - [ ] `fundamental_cache` has rows with correct `cache_version = 1`
    - [ ] No stock with `pe < 0` appears in `daily_scores`
    - [ ] At least one Financial Services stock present (D/E check working)
    - [ ] At least 30 stocks in top scored results
    - [ ] Verify `pledged_data_missing` flag is True for symbols with missing pledge data
