# Screener AI — Indian Market Research Tool

A personal AI-powered stock research tool for Indian markets (NSE/BSE) that runs a daily pipeline after market close to screen and score stocks based on fundamental and technical indicators.

## 🚀 Overview

- **Daily Pipeline:** Automatically fetches EOD data for the NSE universe.
- **Screening:** Filters stocks using fundamental metrics (P/E, Market Cap, etc.).
- **Scoring:** Ranks stocks using technical analysis (RSI, Moving Averages, Volume).
- **Dashboard:** Interactive React-based UI to visualize top-scored stocks and charts.

---

## 🛠 Tech Stack

- **Backend:** Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Celery.
- **Frontend:** React (Vite), Recharts, lightweight-charts.
- **Data Sources:** `yfinance`, `nsepython`.
- **Infrastructure:** Docker Compose (PostgreSQL, Redis).

---

## 🏁 Getting Started

### 1. Prerequisites
- Python 3.10+
- Node.js & npm
- Docker & Docker Compose

### 2. Infrastructure Setup
Spin up the PostgreSQL and Redis instances using Docker:
```bash
docker-compose up -d
```
*PostgreSQL will be available at `localhost:5434`, Redis at `localhost:6379`.*

### 3. Backend Setup
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run migrations:
   ```bash
   alembic upgrade head
   ```

### 4. Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```

---

## 🏃 How to Run

### **Full Stack Development**
To start the project for development, open four terminal windows:

#### **Terminal 1: Redis & DB**
```bash
docker-compose up -d
```

#### **Terminal 2: Backend API**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

#### **Terminal 3: Celery Worker**
```bash
cd backend
source venv/bin/activate
celery -A app.core.celery_app worker --loglevel=info
```

#### **Terminal 4: Celery Beat (Scheduler)**
```bash
cd backend
source venv/bin/activate
celery -A app.core.celery_app beat --loglevel=info
```

#### **Terminal 5: Frontend**
```bash
cd frontend
npm run dev
```

---

## 📝 Development Conventions

- **Stock Symbols:** Always use the `.NS` suffix for NSE stocks when querying data (e.g., `RELIANCE.NS`).
- **Migrations:** Any changes to `backend/app/models/` must be followed by an Alembic migration:
  ```bash
  alembic revision --autogenerate -m "description"
  alembic upgrade head
  ```
- **API Documentation:** Once the backend is running, visit [http://localhost:8000/docs](http://localhost:8000/docs) for Swagger UI.

## 📂 Project Structure
- `backend/`: FastAPI application logic and data pipeline.
- `frontend/`: React dashboard and components.
- `docs/`: Design documents, PRDs, and implementation plans.
