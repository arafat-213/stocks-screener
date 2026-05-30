# Stock AI — Indian Market Research Tool

A personal AI-powered stock research tool for Indian markets (NSE/BSE) that runs a daily pipeline after market close to screen, score, and rank stocks. Includes backtesting, paper trading, and a trade journal.

## Project Overview

- **Purpose:** Daily automated screening of NSE stocks using fundamental filters and technical momentum scoring.
- **Data Sources:** `yfinance` (EOD OHLCV + Fundamentals), `nsepython` (NSE universe).
- **Processing:** Multi-stage distributed engine (Fundamental Screener -> Technical Scorer -> RS Ranking -> Signal Digest).
- **Architecture:**
    - **Backend:** `FastAPI` (Python) with distributed task queue via `Celery` and `Redis`.
    - **Database:** `PostgreSQL` (Managed via Alembic migrations).
    - **Frontend:** `React` (Vite) dashboard with `TailwindCSS`, `Recharts`, and `lightweight-charts`.

## Tech Stack

- **Backend:** Python, FastAPI, PostgreSQL (SQLAlchemy), Celery, Redis, pandas-ta.
- **Migrations:** Alembic.
- **Frontend:** React (Vite), TailwindCSS, Recharts, lightweight-charts.
- **Testing:** pytest (Backend), vitest (Frontend).
- **Data:** yfinance (with request caching), nsepython.

## Building and Running

### Local Development (Docker)
1. Run `docker-compose up -d` to spin up PostgreSQL (port 5434) and Redis (port 6380) instances.

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
- Backend: `pytest`
- Frontend: `npm test`

## Development Conventions

- **Stock Symbols:** Always use the `.NS` suffix for NSE-listed stocks (e.g., `RELIANCE.NS`).
- **Timeframes:** Data is processed daily ('D'), weekly ('W'), and monthly ('M').
- **Database:** PostgreSQL for persistence. Schema changes **must** be handled via **Alembic migrations**.
- **Pipelines:** Long-running tasks (scrapers, backtests) must be handled by Celery workers.
- **Timezones:** Internal processing uses `Asia/Kolkata`.

## Key Files

- [PRD.md](./PRD.md): Detailed Product Requirements and Architecture.
- `backend/app/main.py`: FastAPI entry point and health checks.
- `backend/app/pipeline/orchestrator.py`: Core logic for the daily research pipeline.
- `backend/app/db/models.py`: SQLAlchemy models for signals, backtests, and paper trading.
- `frontend/src/App.jsx`: Main routing for Dashboard, Backtest, Portfolio, and Intelligence.

## Frontend rules
- Use map, filter, sort, size, length, forEach, reduce, slice, trim from lodash/fp instead of array native helpers.
- Use ui-ux-pro-max skill while designing frontend components and pages
