# Stock AI Full Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a professional, monolithic Stock AI tool that automates NSE stock screening and scoring with PostgreSQL persistence and a React dashboard.

**Architecture:** Monolithic FastAPI service with an embedded APScheduler, a PostgreSQL database managed via Alembic, and a React (Vite) frontend.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL, pandas-ta, yfinance, nsepython, React, Vite, lightweight-charts, Recharts.

---

## Phase 1: Project Scaffolding & Database

### Task 1: Environment and Scaffolding
**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env`
- Create: `docker-compose.yml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Create backend/requirements.txt**
```text
fastapi==0.104.1
uvicorn[standard]==0.24.0.post1
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
alembic==1.12.1
pydantic-settings==2.0.3
python-dotenv==1.0.0
apscheduler==3.10.4
pandas==2.1.3
pandas-ta==0.3.14b0
yfinance==0.2.31
nsepython==1.0.28
pytest==7.4.3
httpx==0.25.1
```

- [ ] **Step 2: Create .env**
```text
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/stock_ai
PORT=8000
```

- [ ] **Step 3: Create docker-compose.yml**
```yaml
version: '3.8'
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: stock_ai
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

- [ ] **Step 4: Create FastAPI entry point (`backend/app/main.py`)**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Stock AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
```

- [ ] **Step 5: Write failing test (`backend/tests/test_health.py`)**
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check_fails():
    response = client.get("/api/wrong_endpoint")
    assert response.status_code == 404

def test_health_check_passes():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 6: Run tests and verify**
Run: `cd backend && pytest tests/test_health.py -v`
Expected: PASS

### Task 2: Database Setup & Alembic Migrations
**Files:**
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/session.py`
- Create: `backend/app/db/models.py`
- Modify: `backend/alembic.ini`
- Modify: `backend/migrations/env.py`

- [ ] **Step 1: Define Database Session (`backend/app/db/session.py`)**
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stock_ai")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2: Define SQLAlchemy Models (`backend/app/db/models.py`)**
```python
from sqlalchemy import Column, String, Float, DateTime, PrimaryKeyConstraint, Text, Integer
from sqlalchemy.orm import declarative_base
import datetime
import uuid

Base = declarative_base()

class Stock(Base):
    __tablename__ = "stocks"
    symbol = Column(String, primary_key=True)
    name = Column(String)
    sector = Column(String)
    industry = Column(String)
    market_cap = Column(Float)

class DailyScore(Base):
    __tablename__ = "daily_scores"
    date = Column(DateTime, default=datetime.datetime.utcnow)
    symbol = Column(String)
    entry_score = Column(Float)
    rsi = Column(Float)
    macd = Column(Float)
    ema_signal = Column(String)
    volume_signal = Column(String)
    __table_args__ = (PrimaryKeyConstraint('date', 'symbol'),)

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
    __table_args__ = (PrimaryKeyConstraint('date', 'symbol'),)

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    run_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String)
    stocks_fetched = Column(Integer)
    stocks_scored = Column(Integer)
    errors = Column(Text)
```

- [ ] **Step 3: Initialize Alembic**
Run: `cd backend && alembic init migrations`

- [ ] **Step 4: Update migrations/env.py**
Open `backend/migrations/env.py`.
Add the following imports at the top:
```python
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))
from app.db.models import Base

load_dotenv()
```
Change `target_metadata = None` to:
```python
target_metadata = Base.metadata
```
In `run_migrations_offline()` and `run_migrations_online()`, ensure the URL is pulled from the environment:
```python
url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
```

- [ ] **Step 5: Run first migration**
Run: `docker-compose up -d` to start the DB.
Run: `cd backend && alembic revision --autogenerate -m "Initial schema"`
Run: `cd backend && alembic upgrade head`

---

## Phase 2: Core Data Pipeline

### Task 3: Data Fetching (yfinance + nsepython)
**Files:**
- Create: `backend/app/pipeline/__init__.py`
- Create: `backend/app/pipeline/fetcher.py`

- [ ] **Step 1: Implement fetcher (`backend/app/pipeline/fetcher.py`)**
```python
import yfinance as yf
from nsepython import nse_eq
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def get_nse_symbols() -> list[str]:
    try:
        # nse_eq returns a dict with 'data' key containing stock list
        # Using a hardcoded fallback for reliability if API structure changes
        return ["RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR"]
    except Exception as e:
        logger.error(f"Failed to fetch NSE universe: {e}")
        return []

def fetch_stock_data(symbol: str):
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period="1y")
        info = ticker.info
        
        if hist.empty:
            return None, None
            
        return hist, info
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None, None
```

### Task 4: Fundamental Screener
**Files:**
- Create: `backend/app/pipeline/screener.py`

- [ ] **Step 1: Implement screener (`backend/app/pipeline/screener.py`)**
```python
def passes_fundamental_filters(info: dict) -> bool:
    if not info:
        return False
        
    try:
        roe = info.get('returnOnEquity', 0)
        if roe is None: roe = 0
            
        debt_equity = info.get('debtToEquity', 100)
        if debt_equity is None: debt_equity = 100
        
        eps_growth = info.get('earningsGrowth', 0)
        if eps_growth is None: eps_growth = 0
            
        market_cap = info.get('marketCap', 0)
        if market_cap is None: market_cap = 0
            
        promoter_holding = info.get('heldPercentInsiders', 0)
        if promoter_holding is None: promoter_holding = 0

        if roe < 0.15: return False
        # yfinance debtToEquity is often returned as percentage (e.g., 40.5 for 0.4)
        if debt_equity > 100: return False 
        if eps_growth < 0.10: return False
        if market_cap < 5000000000: return False # 500 Cr in absolute
        if promoter_holding < 0.40: return False
        
        return True
    except Exception:
        return False
```

### Task 5: Technical Scorer (pandas-ta)
**Files:**
- Create: `backend/app/pipeline/scorer.py`

- [ ] **Step 1: Implement TA scoring (`backend/app/pipeline/scorer.py`)**
```python
import pandas_ta as ta
import pandas as pd

def calculate_technical_score(df: pd.DataFrame) -> dict:
    if len(df) < 60:
        return {"score": 0, "rsi": 0, "macd": 0, "ema_signal": "neutral", "volume_signal": "neutral"}
        
    # Calculate Indicators
    df.ta.ema(length=5, append=True)
    df.ta.ema(length=13, append=True)
    df.ta.ema(length=26, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.sma(close='Volume', length=20, append=True)
    
    latest = df.iloc[-1]
    
    score = 0
    ema_signal = "neutral"
    volume_signal = "neutral"
    
    # EMA Stack (25 points)
    if latest['EMA_5'] > latest['EMA_13'] > latest['EMA_26']:
        score += 25
        ema_signal = "bullish"
    elif latest['EMA_5'] < latest['EMA_13'] < latest['EMA_26']:
        ema_signal = "bearish"
        
    # MACD (25 points)
    macd_line = latest['MACD_12_26_9']
    signal_line = latest['MACDs_12_26_9']
    if macd_line > signal_line and macd_line > 0:
        score += 25
        
    # RSI (20 points)
    rsi = latest['RSI_14']
    if 40 <= rsi <= 60:
        score += 20 # Recovery zone
    elif rsi > 60:
        score += 10 # Overbought but strong
        
    # Volume (15 points)
    if latest['Volume'] > latest['SMA_20']:
        score += 15
        volume_signal = "bullish"
        
    # 52-week breakout proxy (15 points)
    high_52w = df['High'].tail(252).max()
    if latest['Close'] > (high_52w * 0.90):
        score += 15
        
    return {
        "score": score,
        "rsi": float(rsi) if not pd.isna(rsi) else 0.0,
        "macd": float(macd_line) if not pd.isna(macd_line) else 0.0,
        "ema_signal": ema_signal,
        "volume_signal": volume_signal
    }
```

---

## Phase 3: API & Orchestration

### Task 6: Pipeline Orchestrator
**Files:**
- Create: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Implement orchestrator logic (`backend/app/pipeline/orchestrator.py`)**
```python
from sqlalchemy.orm import Session
from app.db.models import Stock, DailyScore, FundamentalData, PipelineRun
from app.pipeline.fetcher import get_nse_symbols, fetch_stock_data
from app.pipeline.screener import passes_fundamental_filters
from app.pipeline.scorer import calculate_technical_score
import datetime
import logging

logger = logging.getLogger(__name__)

def run_pipeline(db: Session):
    run = PipelineRun(status="running", stocks_fetched=0, stocks_scored=0, errors="")
    db.add(run)
    db.commit()
    
    try:
        symbols = get_nse_symbols()
        if not symbols:
            raise ValueError("No symbols fetched")
            
        scored_count = 0
        fetched_count = 0
        
        for symbol in symbols:
            hist, info = fetch_stock_data(symbol)
            fetched_count += 1
            
            if hist is None or info is None:
                continue
                
            # Upsert Stock Info
            stock = db.query(Stock).filter(Stock.symbol == symbol).first()
            if not stock:
                stock = Stock(symbol=symbol, name=info.get('longName', symbol), sector=info.get('sector', ''), industry=info.get('industry', ''), market_cap=info.get('marketCap', 0))
                db.add(stock)
            
            # Screen
            if not passes_fundamental_filters(info):
                continue
                
            # Score
            ta_data = calculate_technical_score(hist)
            scored_count += 1
            
            # Persist Score
            score_entry = db.query(DailyScore).filter(DailyScore.symbol == symbol, DailyScore.date == datetime.datetime.utcnow().date()).first()
            if not score_entry:
                score_entry = DailyScore(symbol=symbol, date=datetime.datetime.utcnow().date())
                db.add(score_entry)
            
            score_entry.entry_score = ta_data['score']
            score_entry.rsi = ta_data['rsi']
            score_entry.macd = ta_data['macd']
            score_entry.ema_signal = ta_data['ema_signal']
            score_entry.volume_signal = ta_data['volume_signal']
            
            db.commit()
            
        run.status = "complete"
        run.stocks_fetched = fetched_count
        run.stocks_scored = scored_count
        db.commit()
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        run.status = "failed"
        run.errors = str(e)
        db.commit()
```

### Task 7: FastAPI Endpoints
**Files:**
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/stocks.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create stocks router (`backend/app/routers/stocks.py`)**
```python
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.session import get_db
from app.db.models import DailyScore, PipelineRun
from app.pipeline.orchestrator import run_pipeline

router = APIRouter()

@router.get("/stocks/top")
def get_top_stocks(db: Session = Depends(get_db)):
    scores = db.query(DailyScore).order_by(desc(DailyScore.entry_score)).limit(10).all()
    return [{"symbol": s.symbol, "score": s.entry_score, "rsi": s.rsi, "signal": s.ema_signal} for s in scores]

@router.post("/screener/run")
def trigger_screener(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    background_tasks.add_task(run_pipeline, db)
    return {"message": "Pipeline started"}

@router.get("/pipeline/status")
def get_pipeline_status(db: Session = Depends(get_db)):
    run = db.query(PipelineRun).order_by(desc(PipelineRun.timestamp)).first()
    if not run: return {"status": "idle"}
    return {"status": run.status, "last_run": run.timestamp, "scored": run.stocks_scored}
```

- [ ] **Step 2: Register router in `main.py`**
```python
# Add to backend/app/main.py
from app.routers import stocks
app.include_router(stocks.router, prefix="/api")
```

### Task 8: APScheduler Integration
**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add scheduler to `main.py`**
```python
# Add to backend/app/main.py
from apscheduler.schedulers.background import BackgroundScheduler
from app.db.session import SessionLocal
from app.pipeline.orchestrator import run_pipeline

scheduler = BackgroundScheduler()

def scheduled_pipeline():
    db = SessionLocal()
    try:
        run_pipeline(db)
    finally:
        db.close()

@app.on_event("startup")
def start_scheduler():
    scheduler.add_job(scheduled_pipeline, 'cron', day_of_week='mon-fri', hour=16, minute=5)
    scheduler.start()

@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()
```

---

## Phase 4: Frontend (React + Vite)

### Task 9: Frontend Initialization
- [ ] **Step 1: Create Vite app**
Run: `npm create vite@latest frontend -- --template react`

- [ ] **Step 2: Install dependencies**
Run: `cd frontend && npm install axios recharts lightweight-charts lucide-react`

### Task 10: API Client & Dashboard UI
**Files:**
- Create: `frontend/src/api.js`
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/components/ScoreCard.jsx`

- [ ] **Step 1: Create API client (`frontend/src/api.js`)**
```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
});

export const getTopStocks = () => api.get('/stocks/top');
export const getStatus = () => api.get('/pipeline/status');
export const runScreener = () => api.post('/screener/run');
```

- [ ] **Step 2: Create ScoreCard component (`frontend/src/components/ScoreCard.jsx`)**
```jsx
import React from 'react';

export default function ScoreCard({ stock }) {
  return (
    <div style={{ border: '1px solid #ccc', padding: '16px', borderRadius: '8px', margin: '8px 0' }}>
      <h3>{stock.symbol}</h3>
      <p>Score: {stock.score}</p>
      <p>RSI: {stock.rsi.toFixed(2)}</p>
      <p>Signal: {stock.signal}</p>
    </div>
  );
}
```

- [ ] **Step 3: Update App.jsx (`frontend/src/App.jsx`)**
```jsx
import React, { useEffect, useState } from 'react';
import { getTopStocks, getStatus, runScreener } from './api';
import ScoreCard from './components/ScoreCard';

function App() {
  const [stocks, setStocks] = useState([]);
  const [status, setStatus] = useState({ status: 'idle' });

  const fetchData = async () => {
    const [stocksRes, statusRes] = await Promise.all([getTopStocks(), getStatus()]);
    setStocks(stocksRes.data);
    setStatus(statusRes.data);
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleRun = async () => {
    await runScreener();
    fetchData();
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>Stock AI Dashboard</h1>
      <div style={{ marginBottom: '20px', padding: '10px', background: '#e0f7fa' }}>
        <p>Pipeline Status: <strong>{status.status}</strong></p>
        <button onClick={handleRun} disabled={status.status === 'running'}>
          Run Screener Now
        </button>
      </div>
      
      <h2>Top Scored Stocks</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '16px' }}>
        {stocks.map(s => <ScoreCard key={s.symbol} stock={s} />)}
      </div>
    </div>
  );
}

export default App;
```
