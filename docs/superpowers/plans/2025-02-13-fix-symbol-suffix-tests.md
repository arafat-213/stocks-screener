# Fix Symbol Suffix Violations in Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce that all Indian stock symbols in backend tests use the `.NS` suffix to comply with project technical standards.

**Architecture:** Surgical replacement of hardcoded stock symbols in test files.

**Tech Stack:** Python, pytest, SQLAlchemy.

---

### Task 1: Update `backend/tests/api/test_stocks_search.py`

**Files:**
- Modify: `backend/tests/api/test_stocks_search.py`

- [ ] **Step 1: Update symbols to include .NS suffix**

```python
# In test_search_stocks_basic
db.add(Stock(symbol="RELIANCE.NS", name="Reliance Industries Ltd", sector="Energy"))
db.add(Stock(symbol="RELINFRA.NS", name="Reliance Infrastructure", sector="Infrastructure"))
db.add(Stock(symbol="TCS.NS", name="Tata Consultancy Services", sector="IT"))

# In assertions
assert results[0]["symbol"] == "RELIANCE.NS"
assert "RELIANCE.NS" in symbols
assert "RELINFRA.NS" in symbols

# In test_search_stocks_with_ns_suffix
db.add(Stock(symbol="RELIANCE.NS", name="Reliance Industries Ltd", sector="Energy"))
response = client.get(f"/api/stocks/search?q=RELIANCE{suffix}")
assert results[0]["symbol"] == "RELIANCE.NS"
```

- [ ] **Step 2: Run tests to verify**

Run: `pytest backend/tests/api/test_stocks_search.py -v`
Expected: PASS

---

### Task 2: Update `backend/tests/api/test_symbol_suffix.py`

**Files:**
- Modify: `backend/tests/api/test_symbol_suffix.py`

- [ ] **Step 1: Update symbols to include .NS suffix**

```python
# In test_get_stock_detail_case_insensitive_suffix
stock = Stock(symbol="RELIANCE.NS", name="Reliance Industries", sector="Energy")
assert response.json()["symbol"] == "RELIANCE.NS"

# In test_refresh_cache_case_insensitive_suffix
stock = Stock(symbol="RELIANCE.NS", name="Reliance Industries", sector="Energy")
assert response.json()["message"] == "Force refresh scheduled for RELIANCE.NS"
cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == "RELIANCE.NS").first()

# In test_cache_status_case_insensitive_suffix
stock = Stock(symbol="RELIANCE.NS", name="Reliance Industries", sector="Energy")
fund_cache = FundamentalCache(symbol="RELIANCE.NS", force_refresh=False)
assert response.json()["symbol"] == "RELIANCE.NS"
```

- [ ] **Step 2: Run tests to verify**

Run: `pytest backend/tests/api/test_symbol_suffix.py -v`
Expected: PASS

---

### Task 3: Update `backend/tests/api/test_suffix_detail.py`

**Files:**
- Modify: `backend/tests/api/test_suffix_detail.py`

- [ ] **Step 1: Update symbols to include .NS suffix**

```python
# In test_get_stock_detail_with_ns_suffix_case_insensitive
db.add(Stock(symbol="RELIANCE.NS", name="Reliance Industries Ltd", sector="Energy"))
assert data["symbol"] == "RELIANCE.NS"
```

- [ ] **Step 2: Run tests to verify**

Run: `pytest backend/tests/api/test_suffix_detail.py -v`
Expected: PASS

---

### Task 4: Update `backend/tests/unit/test_new_screens.py`

**Files:**
- Modify: `backend/tests/unit/test_new_screens.py`

- [ ] **Step 1: Update all symbols in model instantiations and assertions**

Replace `RELIANCE` with `RELIANCE.NS`, `TCS` with `TCS.NS`, `INFY` with `INFY.NS`, `WIPRO` with `WIPRO.NS`, `MARUTI` with `MARUTI.NS`, `HCLTECH` with `HCLTECH.NS` throughout the file.

- [ ] **Step 2: Run tests to verify**

Run: `pytest backend/tests/unit/test_new_screens.py -v`
Expected: PASS

---

### Task 5: Update `backend/tests/unit/test_models.py`

**Files:**
- Modify: `backend/tests/unit/test_models.py`

- [ ] **Step 1: Replace AAPL with RELIANCE.NS**

```python
def test_technical_signal_ema_fields():
    signal = TechnicalSignal(
        symbol="RELIANCE.NS",
        ...
    )
```

- [ ] **Step 2: Run tests to verify**

Run: `pytest backend/tests/unit/test_models.py -v`
Expected: PASS

---

### Task 6: Final Global Check and Verification

- [ ] **Step 1: Search for any remaining violations**

Run: `grep -rE "symbol=['\"][A-Z]+['\"]" backend/tests | grep -v "\.NS"`

- [ ] **Step 2: Fix any remaining items found**

- [ ] **Step 3: Run all backend tests**

Run: `pytest backend/tests -v`
Expected: PASS
