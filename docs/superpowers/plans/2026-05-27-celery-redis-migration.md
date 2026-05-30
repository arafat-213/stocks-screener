# Celery + Redis Pipeline Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the long-running stock screening pipeline out of the FastAPI process into a distributed task queue using Celery and Redis.

**Architecture:**
- Redis service added to `docker-compose.yml`.
- Celery worker process handles pipeline execution.
- Celery Beat process handles scheduling (replacing APScheduler).
- FastAPI enqueues tasks via Redis.

**Tech Stack:** Python, Celery, Redis, FastAPI, SQLAlchemy.

---

### Task 1: Infrastructure & Dependencies

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add Redis to docker-compose.yml**
Update `docker-compose.yml` to include the redis service.
```yaml
services:
  # ... existing db service ...
  redis:
    image: redis:alpine
    ports:
      - "6380:6379"
    restart: always
```

- [ ] **Step 2: Update backend/requirements.txt**
Add `celery` and `redis`, and remove `apscheduler`.
```text
celery==5.3.6
redis==5.0.1
# remove apscheduler line
```

- [ ] **Step 3: Verify infrastructure**
Run `docker-compose up -d redis`.
Run `pip install -r backend/requirements.txt`.
Expected: Redis container is running, and new packages are installed.

- [ ] **Step 4: Commit**
```bash
git add docker-compose.yml backend/requirements.txt
git commit -m "infra: add redis and celery dependencies"
```

---

### Task 2: Celery Application Setup

**Files:**
- Create: `backend/app/core/celery_app.py`

- [ ] **Step 1: Create celery_app.py**
Initialize the Celery app and configure the Beat schedule.
```python
import os
from celery import Celery
from celery.schedules import crontab

redis_url = os.getenv("REDIS_URL", "redis://localhost:6380/0")

celery_app = Celery(
    "stock_ai",
    broker=redis_url,
    backend=redis_url,
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    beat_schedule={
        "daily-pipeline-at-4pm": {
            "task": "app.tasks.execute_pipeline_task",
            "schedule": crontab(day_of_week="1-5", hour=16, minute=5),
        },
        "nightly-cleanup-at-2am": {
            "task": "app.tasks.execute_cleanup_task",
            "schedule": crontab(hour=2, minute=30),
        },
    },
)
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/core/celery_app.py
git commit -m "feat: initialize celery app and beat schedule"
```

---

### Task 3: Define Celery Tasks

**Files:**
- Create: `backend/app/tasks.py`

- [ ] **Step 1: Create tasks.py**
Implement task wrappers for the pipeline and cleanup.
```python
import logging
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.cleanup import run_cleanup

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.execute_pipeline_task")
def execute_pipeline_task():
    logger.info("Starting scheduled pipeline task")
    db = SessionLocal()
    try:
        run_pipeline(db)
    except Exception as e:
        logger.error(f"Pipeline task failed: {e}")
        raise
    finally:
        db.close()

@celery_app.task(name="app.tasks.execute_cleanup_task")
def execute_cleanup_task():
    logger.info("Starting scheduled cleanup task")
    db = SessionLocal()
    try:
        run_cleanup(db)
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        raise
    finally:
        db.close()
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/tasks.py
git commit -m "feat: define celery tasks for pipeline and cleanup"
```

---

### Task 4: Refactor FastAPI and Remove APScheduler

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/routers/screens.py` (or whichever router triggers the run)

- [ ] **Step 1: Remove APScheduler from main.py**
Remove imports, `scheduler` instance, and the `lifespan` logic starting it.
```python
# Remove these lines:
# from apscheduler.schedulers.background import BackgroundScheduler
# scheduler = BackgroundScheduler()

# In lifespan, remove:
# scheduler.add_job(...)
# scheduler.start()
# scheduler.shutdown()
```

- [ ] **Step 2: Update manual trigger endpoints**
Search for usages of `run_pipeline(db)` in routers and replace with `execute_pipeline_task.delay()`.
```python
# Before:
# run_pipeline(db)

# After:
from app.tasks import execute_pipeline_task
execute_pipeline_task.delay()
```

- [ ] **Step 3: Verify application starts**
Run `uvicorn app.main:app` and check logs.
Expected: FastAPI starts without APScheduler logs.

- [ ] **Step 4: Commit**
```bash
git add backend/app/main.py backend/app/routers/*.py
git commit -m "refactor: remove apscheduler and use celery for manual triggers"
```

---

### Task 5: Final Validation

- [ ] **Step 1: Run full stack**
Ensure Redis is up. Start Celery worker: `celery -A app.core.celery_app worker --loglevel=info`.
Start FastAPI.
- [ ] **Step 2: Trigger via API**
Use the frontend or `curl` to trigger the pipeline.
Expected: FastAPI returns 202/success immediately. Celery worker logs show the task starting.
- [ ] **Step 3: Verify DB updates**
Poll the health/status endpoint.
Expected: Status updates correctly as the Celery task progresses.
- [ ] **Step 4: Commit**
```bash
git commit --allow-empty -m "test: verify full celery + redis flow"
```
