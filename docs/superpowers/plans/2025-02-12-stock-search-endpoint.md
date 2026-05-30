# Stock Search Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a new `GET /api/stocks/search` endpoint that allows searching for stocks by symbol or name with smart ordering.

**Architecture:** Add a new route in `backend/app/routers/stocks.py` that queries the `stocks` table using SQLAlchemy's `ilike` for case-insensitive partial matching. The results will be sorted in Python to prioritize exact symbol matches and prefix matches.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pytest

---

### Task 1: Create Search Test File

**Files:**
- Create: `backend/tests/api/test_stocks_search.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from app.db.models import Stock

def test_search_stocks_empty(client):
    response = client.get("/api/stocks/search?q=")
    assert response.status_code == 200
    assert response.json() == []

def test_search_stocks_short(client):
    response = client.get("/api/stocks/search?q=R")
    assert response.status_code == 200
    assert response.json() == []

def test_search_stocks_basic(client, db):
    # Seed data
    db.add(Stock(symbol="RELIANCE", name="Reliance Industries Ltd", sector="Energy"))
    db.add(Stock(symbol="RELINFRA", name="Reliance Infrastructure", sector="Infrastructure"))
    db.add(Stock(symbol="TCS", name="Tata Consultancy Services", sector="IT"))
    db.commit()

    # Exact symbol match should be first
    response = client.get("/api/stocks/search?q=RELIANCE")
    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    assert results[0]["symbol"] == "RELIANCE"

    # Partial match
    response = client.get("/api/stocks/search?q=REL")
    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 2
    symbols = [r["symbol"] for r in results]
    assert "RELIANCE" in symbols
    assert "RELINFRA" in symbols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend ./backend/venv/bin/pytest backend/tests/api/test_stocks_search.py`
Expected: FAIL (404 Not Found since endpoint doesn't exist)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/api/test_stocks_search.py
git commit -m "test(backend): add failing tests for stock search"
```

### Task 2: Implement Search Endpoint

**Files:**
- Modify: `backend/app/routers/stocks.py`

- [ ] **Step 1: Implement the search endpoint**

```python
from sqlalchemy import or_, func

@router.get("/stocks/search")
def search_stocks(q: str = "", db: Session = Depends(get_db)):
    if len(q) < 2:
        return []

    query = q.strip()

    # Ordering: Exact symbol match, then symbol starts with, then name contains
    results = db.query(Stock).filter(
        or_(
            Stock.symbol.ilike(f"%{query}%"),
            Stock.name.ilike(f"%{query}%")
        )
    ).limit(50).all()

    # Sort in Python for smart ordering
    query_upper = query.upper()
    def sort_key(s):
        if s.symbol == query_upper: return 0
        if s.symbol.startswith(query_upper): return 1
        if s.name.lower().startswith(query.lower()): return 2
        return 3

    sorted_results = sorted(results, key=sort_key)
    final_results = sorted_results[:15]

    return [
        {"symbol": s.symbol, "name": s.name, "sector": s.sector}
        for s in final_results
    ]
```

- [ ] **Step 2: Run tests to verify it passes**

Run: `PYTHONPATH=backend ./backend/venv/bin/pytest backend/tests/api/test_stocks_search.py`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/stocks.py
git commit -m "feat(backend): add stock search endpoint"
```
