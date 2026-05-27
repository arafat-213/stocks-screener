# Design Specification: Celery + Redis Task Queue for Pipeline

## Overview
The current implementation of the backend runs a 40-minute IO/CPU-heavy data pipeline within the FastAPI process using `apscheduler.BackgroundScheduler`. This blocks thread pool resources and makes the pipeline vulnerable to premature termination if the web worker restarts (e.g., due to OOM, crashes, or deployments). 

To resolve this and gain hands-on experience with Redis, we will decouple the pipeline execution from the web server by implementing a distributed task queue using Celery as the worker manager and Redis as the message broker.

## Architecture & Data Flow
1. **Redis (Broker):** Acts as the message broker.
2. **FastAPI (Web):** Handles HTTP requests. The `/api/screener/run` endpoint (or equivalent trigger) will enqueue tasks to Redis and return immediately.
3. **Celery Worker (Process):** A standalone Python process that consumes tasks from Redis and executes the heavy pipeline logic.
4. **Celery Beat (Scheduler):** Replaces `apscheduler`. A lightweight process that enqueues scheduled tasks (e.g., daily pipeline runs) into Redis at configured intervals.

## Component Changes

### 1. Infrastructure
- Update `docker-compose.yml` to include a Redis service using the official `redis:alpine` image.

### 2. Dependencies
- **Add:** `celery` and `redis` to `backend/requirements.txt`.
- **Remove:** `apscheduler` from `backend/requirements.txt`.

### 3. Application Core
- **Create `backend/app/core/celery_app.py`**:
  - Initialize the Celery application.
  - Configure the broker URL to point to Redis (handling both Docker and local setups via environment variables or defaults).
  - Configure Celery Beat schedules (e.g., pipeline at 16:05 weekdays, cleanup at 02:30).
- **Create `backend/app/tasks.py`**:
  - Define `@celery_app.task` wrapped functions: `execute_pipeline_task` and `execute_cleanup_task`.
  - These tasks will instantiate their own `SessionLocal` database connections, run the respective orchestrator/cleanup functions, and ensure the sessions are closed.

### 4. FastAPI Refactoring (`backend/app/main.py`)
- Remove all `apscheduler` imports and setup logic.
- Remove the `lifespan` context manager logic that starts the scheduler.
- Update the manual trigger endpoints (e.g., in `screens.py` or `dashboard.py` if that's where they live) to use `<task_name>.delay()` instead of calling the pipeline synchronously or managing custom background tasks.

## Testing Strategy
- Verify Redis container starts and is accessible.
- Run FastAPI, Celery Worker, and Celery Beat locally.
- Hit the manual trigger API endpoint and verify FastAPI returns immediately while the Celery worker picks up and processes the task.
- Verify that status polling (reading from the database) continues to work as expected while the Celery worker updates the DB.
