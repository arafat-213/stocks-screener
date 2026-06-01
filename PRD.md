# Stock AI MVP — Design Document
**Date:** 2026-05-30
**Status:** Implementation Complete - Version 2.1.0

---

## Summary

A professional-grade AI-powered stock research tool for Indian markets (NSE/BSE). It runs a daily automated pipeline after market close to screen, score, and rank stocks based on fundamental quality and technical momentum. Beyond simple screening, it includes a robust backtesting engine, paper trading simulation, and a trade journaling system.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data Fetching | `yfinance`, `nsepython` |
| Technical Analysis | `pandas-ta` |
| Backend | `FastAPI` (Python) |
| Task Queue & Scheduler | `Celery` + `Redis` + `Celery Beat` |
| Database | `PostgreSQL` (Neon/Supabase/Local Docker) |
| Migrations | `Alembic` |
| Frontend | `React` + `Vite` + `TailwindCSS` + `Recharts` + `lightweight-charts` |
| Package Manager | `pip` + `npm` |
| Testing | `pytest`, `vitest` |

---

## Architecture Overview

The system uses a **Distributed Task Architecture** to handle heavy data processing without blocking the API or frontend.

```
┌─────────────────────────────────────────────────────┐
│             FASTAPI BACKEND (API Layer)             │
│  ┌──────────────────────┐  ┌─────────────────────┐  │
│  │   API ENDPOINTS      │  │    CELERY BEAT      │  │
│  │  /stocks, /backtest  │  │   (Scheduler)       │  │
│  └──────────┬───────────┘  └──────────┬──────────┘  │
└─────────────┼─────────────────────────┼─────────────┘
              │                         │
     ┌────────▼─────────────────────────▼────────┐
     │             CELERY WORKERS                │
     │  pipeline.py | backtest.py | paper.py     │
     └────────────────────┬──────────────────────┘
                          │
                 ┌────────▼────────┐
                 │  PostgreSQL DB  │
                 │  (Persistence)  │
                 └────────┬────────┘
                          │
                 ┌────────▼────────┐
                 │  React Frontend │
                 │  (Dashboard)    │
                 └─────────────────┘
```

---

## Core Features

### 1. Multi-Stage Research Pipeline
Runs daily at 4:05 PM IST.
- **Data Acquisition:** Batch fetching from `yfinance` with intelligent caching and SQLite-backed request persistence.
- **Liquidity Gate:** The system's only fundamental filter, rejecting stocks with Market Cap < 500 Cr or Daily Transaction Value < 2 Cr to ensure exit liquidity.
- **Technical Scorer:** Pure technical scoring model (0-100) using EMA stacks, MACD, RSI, and Volume Breakouts across Daily, Weekly, and Monthly timeframes.
- **Relative Strength (RS) Ranking:** Compares stock performance against the broader market benchmark to identify true market leadership.
- **Signal Digest:** Consolidates technical signals into actionable tiers (Tier 1: High-conviction breakouts, Tier 2: Pullbacks to support).

### 2. Backtesting Engine
- High-performance historical simulation using cached OHLCV data.
- Configurable strategies, position sizing, and risk management (Stop Loss, Targets).
- Detailed performance metrics: Sharpe Ratio, Win Rate, Max Drawdown, Equity Curves.

### 3. Paper Trading & Portfolio
- Virtual portfolio management with real-time execution simulation based on daily close.
- Automated tracking of "Pending" setups (Pullbacks to EMA20).
- Trailing stop-loss and target management.

### 4. Trade Journaling
- Integrated journal to bridge the gap between screening and execution.
- Manual entry or automated conversion from paper trades.
- Historical analysis of trade performance and exit reasons.

---

## Database Schema (Key Entities)

- **Stocks:** Master metadata for symbols, sectors, and industries.
- **Technical Signals:** Unified storage for multi-timeframe indicators (RSI, MACD, EMA, RS Score).
- **Fundamental Cache:** High-performance storage for screened fundamental metrics.
- **Pipeline Runs:** Checkpoint-based tracking of daily processing status.
- **Backtest Runs/Trades:** Detailed records of historical simulations.
- **Paper Positions/Trades:** Active and closed virtual positions.
- **Watchlist & Journal:** User-managed tracking of high-conviction ideas.

---

## API Endpoints

- `/api/dashboard`: Summary of latest signals, regime analysis, and pipeline health.
- `/api/screens`: Specialized scanners (Tier 1, Pullbacks, High RS, Consolidation).
- `/api/stocks/{symbol}`: Comprehensive detail view (Price, TA, Fundamentals, History).
- `/api/backtest`: Execute and retrieve historical simulations.
- `/api/portfolio`: Manage paper trading positions and performance.
- `/api/watchlist`: Manage and alert on specific symbols.
- `/api/reports`: Historical signal digests and market snapshots.

---

## Error Handling & Reliability

- **Checkpoint Persistence:** The pipeline can resume from the last successful phase after a failure.
- **Zombie Cleanup:** Automatic detection and recovery from crashed pipeline runs.
- **Exponential Backoff:** Resilient data fetching from `yfinance` to avoid rate limits.
- **Health Monitoring:** `/api/health` provides real-time status of DB, Cache, and Pipeline staleness.

---

## Development & Deployment

- **Local:** Docker Compose for Postgres/Redis. `uvicorn` for API, `celery` for workers.
- **Testing:** Comprehensive suite covering unit logic, pipeline integration, and API responses.
- **Migrations:** Strict adherence to Alembic for all schema changes.
