# Stock AI MVP — Design Specification
**Date:** 2026-05-06
**Author:** Solo Developer
**Status:** Approved — Ready for Implementation

---

## 1. Project Overview
A personal AI-powered stock research tool for Indian markets (NSE/BSE). It automates the daily task of screening ~2000 stocks down to a high-quality shortlist based on fundamental filters and technical analysis scoring.

## 2. Architecture: Monolithic Service
The system follows a monolithic architecture for simplicity in development and deployment on free-tier cloud services.

### Components:
- **Backend (FastAPI):**
  - **API Layer:** Serves endpoints for the React dashboard.
  - **Background Scheduler (APScheduler):** Embedded in FastAPI, runs daily jobs at 4:05 PM (Market Close).
  - **Pipeline Orchestrator:** Manages the sequence of data fetching, screening, scoring, and persistence.
- **Processing Engine:**
  - `fetcher.py`: Retrieves OHLCV and fundamental data using `yfinance` and `nsepython`.
  - `screener.py`: Applies Stage 1 fundamental filters (ROE, Debt, EPS growth, etc.).
  - `scorer.py`: Calculates technical analysis scores (0-100) using `pandas-ta`.
- **Database (PostgreSQL):**
  - Managed via **Alembic** migrations.
  - Stores master stock lists, daily technical scores, and pipeline run logs.
- **Frontend (React + Vite):**
  - Interactive dashboard for visualizing reports, charts, and pipeline health.

---

## 3. Data Flow

### 3.1 Daily Automated Pipeline (4:05 PM Weekdays)
1. **Trigger:** `APScheduler` starts the orchestrator.
2. **Fetch Symbols:** `nsepython` fetches the full NSE stock universe.
3. **Fetch Data:** `yfinance` fetches 1-year OHLCV and latest fundamentals for all symbols in parallel batches (50 symbols/batch).
4. **Fundamental Screening:** Filters symbols by:
   - ROE > 15%
   - Debt/Equity < 1
   - EPS Growth (YoY) > 10%
   - Market Cap > ₹500 Cr
   - Promoter Holding > 40%
5. **Technical Scoring:** Shortlisted stocks are scored 0-100 based on:
   - EMA 5/13/26 alignment (25%)
   - MACD crossover (25%)
   - RSI 14 (20%)
   - Volume vs 20 SMA (15%)
   - Price vs 52-week range (15%)
6. **Persistence:** Scored stocks and pipeline logs are written to PostgreSQL.

### 3.2 User-Triggered Actions
- **Manual Run:** User clicks "Run Screener Now" &rarr; Backend spawns a `BackgroundTask`.
- **Stock Detail:** User clicks a stock &rarr; Backend returns full price history and fundamental analysis for charting.

---

## 4. Database Schema (PostgreSQL)

### Table: `stocks`
- `symbol` (VARCHAR, PK)
- `name` (VARCHAR)
- `sector` (VARCHAR)
- `industry` (VARCHAR)
- `market_cap` (DOUBLE PRECISION)

### Table: `daily_scores`
- `date` (TIMESTAMP, PK)
- `symbol` (VARCHAR, PK, FK to stocks)
- `entry_score` (DOUBLE PRECISION)
- `rsi` (DOUBLE PRECISION)
- `macd` (DOUBLE PRECISION)
- `ema_signal` (VARCHAR)
- `volume_signal` (VARCHAR)

### Table: `fundamental_data`
- `date` (TIMESTAMP, PK)
- `symbol` (VARCHAR, PK, FK to stocks)
- `pe` (DOUBLE PRECISION)
- `pb` (DOUBLE PRECISION)
- `roe` (DOUBLE PRECISION)
- `debt_equity` (DOUBLE PRECISION)
- `eps_growth` (DOUBLE PRECISION)
- `promoter_holding` (DOUBLE PRECISION)

### Table: `pipeline_runs`
- `run_id` (UUID, PK)
- `timestamp` (TIMESTAMP)
- `status` (VARCHAR) - `running`, `complete`, `failed`
- `stocks_fetched` (INTEGER)
- `stocks_scored` (INTEGER)
- `errors` (TEXT)

---

## 5. Error Handling & Edge Cases
- **Market Holidays:** Pipeline checks against a hardcoded NSE holiday list before execution.
- **API Rate Limits:** `yfinance` fetches are batched with exponential backoff on retries.
- **Insufficient Data:** Stocks with < 60 days of history are skipped for TA scoring.
- **Database Resilience:** All pipeline writes use transactions to ensure data integrity.

---

## 6. Testing Strategy
- **Unit Tests:** Focus on scoring math and screening filters (`pytest`).
- **Integration Tests:** End-to-end pipeline execution with mock API responses.
- **API Tests:** Verify REST endpoints and error codes (`httpx`).
- **Coverage Target:** 80% for core processing logic.

---

## 7. Deployment Strategy (Free Tiers)
- **Database:** Neon.tech (Managed PostgreSQL).
- **Backend:** Railway or Render (FastAPI Monolith in Docker).
- **Frontend:** Vercel or Netlify (React Static Build).
- **Local Dev:** `docker-compose` for local PostgreSQL instance.
