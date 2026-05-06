# Stock AI — Indian Market Research Tool

A personal AI-powered stock research tool for Indian markets (NSE/BSE) that runs a daily pipeline after market close to screen and score stocks.

## Project Overview

- **Purpose:** Daily automated screening of NSE stocks using fundamental filters and technical analysis scoring.
- **Data Sources:** `yfinance` (EOD OHLCV + Fundamentals), `nsepython` (NSE universe).
- **Processing:** Two-stage engine (Fundamental Screener -> Technical Scorer).
- **Architecture:** 
    - **Backend:** Monolithic `FastAPI` (Python) with embedded `APScheduler`.
    - **Database:** `PostgreSQL` (Managed via Neon/Supabase or local Docker).
    - **Frontend:** `React` (Vite) dashboard with `Recharts` and `lightweight-charts`.

## Tech Stack

- **Backend:** Python, FastAPI, PostgreSQL (SQLAlchemy), APScheduler, pandas-ta.
- **Migrations:** Alembic.
- **Frontend:** React (Vite), Recharts, lightweight-charts.
- **Testing:** pytest, pytest-cov, httpx.
- **Data:** yfinance, nsepython.

## Building and Running

*Note: The project is currently in the design phase (see [PRD.md](./PRD.md)). The following commands are inferred based on the tech stack.*

### Local Development (Docker)
1. Run `docker-compose up -d` to spin up a local PostgreSQL instance.

### Backend
1. Navigate to `backend/` directory.
2. Install dependencies: `pip install -r requirements.txt`
3. Run migrations: `alembic upgrade head`
4. Run the application: `uvicorn app.main:app --reload`

### Frontend
1. Navigate to `frontend/` directory.
2. Install dependencies: `npm install`
3. Start the dev server: `npm run dev`

### Testing
- Run tests: `pytest`

## Development Conventions

- **Stock Symbols:** Always use the `.NS` suffix for NSE-listed stocks (e.g., `RELIANCE.NS`) when fetching data via `yfinance`.
- **Database:** PostgreSQL for persistence. Schema changes must be handled via **Alembic migrations**.
- **Architecture:** Monolithic FastAPI service. Background tasks (scrapers) are handled by APScheduler within the same process.

## Key Files

- [PRD.md](./PRD.md): Detailed Product Requirements Document and Architecture Design.
- `backend/app/main.py`: FastAPI entry point (Planned).
- `backend/app/pipeline/`: Core logic for fetching, screening, and scoring (Planned).
- `frontend/src/pages/Dashboard.jsx`: Main dashboard view (Planned).
