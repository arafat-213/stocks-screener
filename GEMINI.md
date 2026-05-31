# Stock AI — Technical Standards & Enforcement

This document defines the **Law of the Land** for the Stock AI project. Adherence to these standards is mandatory for all changes. Do not prioritize "working code" over "correct architecture."

## 1. The Pipeline Laws (Backend)

The daily research pipeline is the core of this system. It must be resilient, resumable, and traceable.

*   **Idempotency or Death:** Every pipeline stage (Tier 1, Scoring, Backtest, etc.) MUST be idempotent. Running a stage twice should never duplicate data or leave the DB in an inconsistent state.
*   **Checkpointing:** New sub-tasks within the pipeline must use the `PipelineCheckpoint` system. They must be able to resume from the last successful symbol after a crash.
*   **The NSE Suffix:** All Indian stock symbols MUST have the `.NS` suffix. Never use raw symbols (e.g., `RELIANCE`) in database queries or API logic.
*   **Timezone Integrity:**
    - Internal processing and DB storage: `UTC`.
    - Display and Indian Market logic: `Asia/Kolkata` (IST).
    - Always use `datetime.now(datetime.timezone.utc)` for timestamps.
*   **Error Classification:** Use the `classify_error` utility for all pipeline failures. Log specific symbol failures to `PipelineError` table; do not let a single stock failure crash the entire run.
*   **Concurrency Guard:** Never start a pipeline run or backtest if one is already `running`. Use `cleanup_zombie_runs` to handle crashed processes on startup.

## 2. Data Integrity & Schema

*   **Migrations are Holy:** Direct DB manipulation is forbidden. Every schema change (even adding an index) MUST have an Alembic migration.
*   **SQLAlchemy Only:** No raw SQL strings unless explicitly approved for performance-critical bottlenecks. Use the ORM or the Core expression language.
*   **Pydantic Enforcement:** All API endpoints must use Pydantic models for both Input (Request) and Output (Response) validation. No `dict` passing.

## 3. Frontend Architecture

*   **No Raw State Manipulation:** Use `lodash/fp` (map, filter, reduce) for all data transformations. Never mutate props or state directly.
*   **Component Purity:** Components should be "dumb" display units where possible. Complex logic (TA calculations, ranking) belongs in the Backend.
*   **Theme Consistency:** Adhere strictly to the Tailwind color palette. Custom CSS is a last resort.
*   **UX Response:** Long-running actions (Triggering pipeline, starting backtest) must have immediate UI feedback (Loaders, Toast notifications).

## 4. Testing & Verification

*   **Regression First:** Every bug fix must include a `pytest` case that reproduces the failure.
*   **Mocking External APIs:** Never run tests against live `yfinance` or NSE servers. Use `unittest.mock` or `pytest-mock` to provide consistent fixtures.
*   **CI Cleanliness:** Tests must pass before any feature is considered "done."

---

## Building and Running

### Local Development (Docker)
1. Run `docker-compose up -d` to spin up PostgreSQL (port 5434) and Redis (port 6380).

### Backend Setup
1. `cd backend/`
2. `pip install -r requirements.txt`
3. `alembic upgrade head`
4. `uvicorn app.main:app --reload`
5. Start Worker: `celery -A app.core.celery_app worker --loglevel=info`

### Frontend Setup
1. `cd frontend/`
2. `npm install`
3. `npm run dev`
