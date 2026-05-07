# Dashboard & Detail Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the loop on Stock Details (with on-demand chart data), Reports (with historical browsing), and Screener (with client-side filtering).

**Architecture:** Monolithic FastAPI backend serving structured JSON; React frontend using lightweight-charts for price action and Recharts for score trends. yfinance is fetched on-demand via the project's existing `fetch_stock_data` helper. Navigation is handled via `react-router-dom`.

**Tech Stack:** FastAPI, SQLAlchemy, yfinance, React, react-router-dom, lightweight-charts, Recharts.

---

### Task 0: Frontend - Routing Setup

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/main.jsx`

- [ ] **Step 1: Install react-router-dom**
Run: `npm install react-router-dom` (in frontend directory)

- [ ] **Step 2: Wrap App in BrowserRouter**
Update `main.jsx` to wrap `<App />` in `<BrowserRouter>`.

- [ ] **Step 3: Define Routes in App.jsx**
Map `/` to `Dashboard`, `/stocks/:symbol` to `StockDetail`, `/reports` to `Reports`, and `/screener` to `Screener`.

---

### Task 1: Backend - Stock Detail Endpoint

**Files:**
- Modify: `backend/app/routers/stocks.py`
- Test: `backend/tests/api/test_stocks_detail.py`

- [ ] **Step 1: Write the failing test for stock detail**
```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_stock_detail_not_found():
    response = client.get("/api/stocks/NONEXISTENT")
    assert response.status_code == 404
```

- [ ] **Step 2: Implement the `/api/stocks/{symbol}` endpoint**
Use `fetch_stock_data` from `app.pipeline.fetcher`.
```python
from app.pipeline.fetcher import fetch_stock_data

@router.get("/{symbol}")
def get_stock_detail(symbol: str, db: Session = Depends(get_db)):
    clean_symbol = symbol.replace(".NS", "").upper()
    stock = db.query(Stock).filter(Stock.symbol == clean_symbol).first()
    if not stock: raise HTTPException(status_code=404, detail="Stock not found")
    
    # Use existing helper for consistency
    hist, _ = fetch_stock_data(clean_symbol, period="1y")
    ohlcv = []
    if not hist.empty:
        for idx, row in hist.iterrows():
            ohlcv.append({
                "time": idx.date().isoformat(),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": int(row['Volume'])
            })

    # Scores (Latest for each timeframe)
    latest_scores = {}
    for tf in ['D', 'W', 'M']:
        s = db.query(TechnicalSignal).filter(
            TechnicalSignal.symbol == clean_symbol,
            TechnicalSignal.timeframe == tf
        ).order_by(TechnicalSignal.date.desc()).first()
        if s:
            latest_scores[tf] = {
                "score": s.entry_score,
                "ema_signal": s.ema_signal,
                "volume_signal": s.volume_signal,
                "rsi_signal": s.rsi_signal,
                "rsi": s.rsi
            }
    
    # History (last 30 daily)
    history = db.query(TechnicalSignal).filter(
        TechnicalSignal.symbol == clean_symbol,
        TechnicalSignal.timeframe == 'D'
    ).order_by(TechnicalSignal.date.desc()).limit(30).all()
    score_history = [{"date": h.date.isoformat(), "score": h.entry_score} for h in reversed(history)]

    # Fundamentals
    cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == clean_symbol).first()
    data = db.query(FundamentalData).filter(FundamentalData.symbol == clean_symbol).order_by(FundamentalData.date.desc()).first()
    
    return {
        "symbol": clean_symbol,
        "name": stock.name,
        "ohlcv": ohlcv,
        "scores": latest_scores,
        "score_history": score_history,
        "fundamentals": {
            "pe": data.pe if data else None,
            "roe": data.roe if data else None,
            "debt_equity": cache.de_ratio if cache else None,
            "sector": cache.sector if cache else stock.sector,
            "eps_growth": data.eps_growth if data else None
        }
    }
```

---

### Task 2: Backend - Reports History & Latest Endpoints

**Files:**
- Modify: `backend/app/routers/reports.py`
- Test: `backend/tests/api/test_reports.py`

- [ ] **Step 1: Implement report endpoints**
Fix pathing to avoid `/api/reports/` vs `/api/reports`.
```python
@router.get("")  # Maps to /api/reports
def list_reports(db: Session = Depends(get_db)):
    dates = db.query(func.date(TechnicalSignal.date)).distinct().order_by(func.date(TechnicalSignal.date).desc()).all()
    return [str(d[0]) for d in dates]

@router.get("/latest")
def get_latest_report(db: Session = Depends(get_db)):
    latest_date = db.query(func.max(func.date(TechnicalSignal.date))).scalar()
    if not latest_date: return []
    return get_report_by_date(str(latest_date), db)

@router.get("/{date}")
def get_report_by_date(date: str, db: Session = Depends(get_db)):
    # ... query logic from previous plan ...
```

---

### Task 3: Frontend - Stock Detail UI

**Files:**
- Modify: `frontend/src/pages/StockDetail.jsx`
- Modify: `frontend/src/components/CandlestickChart.jsx`
- Modify: `frontend/src/api/client.js`

- [ ] **Step 1: Multi-Timeframe Confluence UI**
Use card styling similar to `StockCard.jsx`.
```jsx
const ConfluencePanel = ({ scores }) => (
  <div className="grid grid-cols-3 gap-4">
    {['D', 'W', 'M'].map(tf => (
      <div key={tf} className="p-4 border rounded shadow-sm bg-white">
        <h3 className="text-lg font-bold">{tf === 'D' ? 'Daily' : tf === 'W' ? 'Weekly' : 'Monthly'}</h3>
        <div className="text-2xl font-mono">{scores[tf]?.score || '--'}</div>
        <div className="text-sm text-gray-500">{scores[tf]?.ema_signal}</div>
      </div>
    ))}
  </div>
);
```

- [ ] **Step 2: Score Trend Chart**
Use `ResponsiveContainer` and `LineChart` from Recharts to show `score_history`.

- [ ] **Step 3: Navigation Wiring**
Update `StockCard.jsx` to wrap content in a `<Link>` to `/stocks/{symbol}`.

---

### Task 4: Frontend - Reports and Screener Enhancements

**Files:**
- Modify: `frontend/src/pages/Reports.jsx`
- Modify: `frontend/src/pages/Screener.jsx`

- [ ] **Step 1: Implement Reports historical browser**
Sidebar for dates, main table for data. Use `useEffect` to fetch latest report by default.

- [ ] **Step 2: Implement Screener client-side filtering**
Add FilterBar component with inputs for ROE, Score, P/E, and Sector. Filter the `top_stocks` state locally.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/pages/
git commit -m "feat: enhance reports history and screener filters"
```
