# Stock AI — Indian Market Research Tool

A personal AI-powered stock research tool for Indian markets (NSE/BSE) that runs a daily pipeline after market close to screen and score stocks.

## Project Overview

- **Purpose:** Daily automated screening of NSE stocks using fundamental filters and technical analysis scoring.
- **Data Sources:** `yfinance` (EOD OHLCV + Fundamentals), `nsepython` (NSE universe).
- **Processing:** Two-stage engine (Fundamental Screener -> Technical Scorer).
- **Architecture:**
    - **Backend:** `FastAPI` (Python) with distributed task queue via `Celery` and `Redis`.
    - **Database:** `PostgreSQL` (Managed via Neon/Supabase or local Docker).
    - **Frontend:** `React` (Vite) dashboard with `Recharts` and `lightweight-charts`.

## Tech Stack

- **Backend:** Python, FastAPI, PostgreSQL (SQLAlchemy), Celery, Redis, pandas-ta.
- **Migrations:** Alembic.
- **Frontend:** React (Vite), Recharts, lightweight-charts.
- **Testing:** pytest, pytest-cov, httpx.
- **Data:** yfinance, nsepython.

## Building and Running

### Local Development (Docker)
1. Run `docker-compose up -d` to spin up PostgreSQL and Redis instances.

### Backend
1. Navigate to `backend/` directory.
2. Install dependencies: `pip install -r requirements.txt`
3. Run migrations: `alembic upgrade head`
4. Start API: `uvicorn app.main:app --reload`
5. Start Worker: `celery -A app.core.celery_app worker --loglevel=info`
6. Start Beat: `celery -A app.core.celery_app beat --loglevel=info`

### Frontend
1. Navigate to `frontend/` directory.
2. Install dependencies: `npm install`
3. Start the dev server: `npm run dev`

### Testing
- Run tests: `pytest`

## Development Conventions

- **Stock Symbols:** Always use the `.NS` suffix for NSE-listed stocks (e.g., `RELIANCE.NS`) when fetching data via `yfinance`.
- **Database:** PostgreSQL for persistence. Schema changes must be handled via **Alembic migrations**.
- **Architecture:** FastAPI service for the web layer. Background tasks (scrapers) are handled by Celery workers, with scheduling managed by Celery Beat.

## Key Files

- [PRD.md](./PRD.md): Detailed Product Requirements Document and Architecture Design.
- `backend/app/main.py`: FastAPI entry point (Planned).
- `backend/app/pipeline/`: Core logic for fetching, screening, and scoring (Planned).
- `frontend/src/pages/Dashboard.jsx`: Main dashboard view (Planned).
