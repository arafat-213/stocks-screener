# Stock Search / Command Palette Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a robust stock search and command palette by creating a new backend search endpoint and upgrading the existing GlobalSearch component with debounced API calls and keyboard navigation.

**Architecture:** 
- **Backend:** A new `GET /api/stocks/search` endpoint in `stocks.py` using SQLAlchemy `ILIKE` for efficient querying across symbols and names.
- **Frontend:** Update `GlobalSearch.jsx` to replace pre-loaded filtering with a debounced API-driven search, add keyboard event listeners for selection, and enhance the result list UI.

**Tech Stack:** FastAPI, SQLAlchemy, React, Lucide React, Axios.

---

### Task 1: Backend Search Endpoint

**Files:**
- Modify: `backend/app/routers/stocks.py`
- Test: `backend/tests/api/test_stocks_search.py` (Create new)

- [ ] **Step 1: Create the search test file**

```python
import pytest

def test_search_stocks_empty(client):
    response = client.get("/api/stocks/search?q=")
    assert response.status_code == 200
    assert response.json() == []

def test_search_stocks_short(client):
    response = client.get("/api/stocks/search?q=R")
    assert response.status_code == 200
    assert response.json() == []

def test_search_stocks_basic(client, db):
    # Assumes RELIANCE exists in test DB
    response = client.get("/api/stocks/search?q=REL")
    assert response.status_code == 200
    results = response.json()
    assert isinstance(results, list)
    if len(results) > 0:
        assert "symbol" in results[0]
        assert "name" in results[0]
        assert "sector" in results[0]
```

- [ ] **Step 2: Implement search endpoint in `backend/app/routers/stocks.py`**

```python
from sqlalchemy import or_, func

@router.get("/stocks/search")
def search_stocks(q: str = "", db: Session = Depends(get_db)):
    if len(q) < 2:
        return []
        
    query = q.strip()
    
    # Ordering: Exact symbol match, then symbol starts with, then name contains
    # We'll use a CASE statement in SQL for ordering if possible, or do it in Python for simplicity since limit is 15
    
    results = db.query(Stock).filter(
        or_(
            Stock.symbol.ilike(f"%{query}%"),
            Stock.name.ilike(f"%{query}%")
        )
    ).limit(50).all() # Fetch more to sort in Python then slice
    
    # Sort in Python
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

- [ ] **Step 3: Run tests**

Run: `PYTHONPATH=backend ./backend/venv/bin/pytest backend/tests/api/test_stocks_search.py`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/stocks.py
git commit -m "feat(backend): add stock search endpoint"
```

---

### Task 2: Frontend API and Component Updates

**Files:**
- Modify: `frontend/src/api/client.js`
- Modify: `frontend/src/components/GlobalSearch.jsx`
- Modify: `frontend/src/components/GlobalSearch.css`

- [ ] **Step 1: Add API client function**

Modify `frontend/src/api/client.js`:
```javascript
export const searchStocks = (q) => apiClient.get(`/stocks/search?q=${encodeURIComponent(q)}`);
```

- [ ] **Step 2: Update `GlobalSearch.jsx` logic (Debounce & New State)**

```javascript
// Add imports
import { searchStocks } from '../api/client';

// Update Component
export const GlobalSearch = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]); // [{symbol, name, sector}]
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isOpen, setIsOpen] = useState(false);
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const debounceRef = useRef(null);
  
  // Update keyboard handler
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen(true);
      }
      if (e.key === 'Escape') setIsOpen(false);
      
      if (isOpen) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSelectedIndex(prev => results.length > 0 ? Math.min(prev + 1, results.length - 1) : -1);
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSelectedIndex(prev => Math.max(prev - 1, 0));
        }
        if (e.key === 'Enter' && selectedIndex >= 0) {
          e.preventDefault();
          handleSelect(results[selectedIndex].symbol);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, results, selectedIndex]);

  const handleQueryChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    setSelectedIndex(-1);
    clearTimeout(debounceRef.current);
    
    if (val.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    
    setLoading(true);
    debounceRef.current = setTimeout(() => {
      searchStocks(val)
        .then(res => {
          setResults(res.data);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    }, 200);
  };
```

- [ ] **Step 3: Update `GlobalSearch.jsx` Render**

```jsx
// Inside results div:
<div className="results">
  {loading && query.length >= 2 && results.length === 0 ? (
    <div className="searching-state">Searching...</div>
  ) : results.length > 0 ? (
    results.map((s, i) => (
      <div 
        key={s.symbol} 
        className={`result-item ${i === selectedIndex ? 'selected' : ''}`} 
        onClick={() => handleSelect(s.symbol)}
        onMouseEnter={() => setSelectedIndex(i)}
      >
        <div className="result-main">
          <span className="result-symbol">{s.symbol.replace('.NS', '')}</span>
          <span className="result-name text-muted">{s.name}</span>
        </div>
        <span className="result-sector text-xs text-muted">{s.sector}</span>
      </div>
    ))
  ) : query.length >= 2 ? (
    <div className="no-results">No stocks found</div>
  ) : (
    <div className="search-hint">Type at least 2 characters...</div>
  )}
</div>
```

- [ ] **Step 4: Update `GlobalSearch.css`**

```css
.result-symbol { font-weight: 600; font-size: 0.9rem; }
.result-name   { font-size: 0.8rem; margin-left: 8px; }
.result-main   { display: flex; align-items: baseline; }
.result-sector { font-size: 0.75rem; }
.result-item.selected { 
    background: var(--color-bg-elevated); 
    border-left: 3px solid var(--color-primary);
    padding-left: 9px; /* adjust for border */
}

.searching-state, .search-hint {
    padding: 24px;
    text-align: center;
    color: var(--color-text-muted);
}
```

- [ ] **Step 5: Verify in Browser**

1. Press `Cmd+K`.
2. Type "REL".
3. Verify results show Reliance.
4. Use Arrow keys to navigate.
5. Press Enter to select.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.js frontend/src/components/GlobalSearch.jsx frontend/src/components/GlobalSearch.css
git commit -m "feat(frontend): upgrade global search with debounced API and keyboard nav"
```
