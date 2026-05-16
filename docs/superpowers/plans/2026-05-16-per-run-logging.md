# Per-Run Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement per-run logging where each pipeline run and backtest session generates a unique log file.

**Architecture:** A new `LoggingManager` will handle file handler lifecycle (setup/cleanup), replacing the static global file logger in `main.py` with dynamic handlers managed at runtime.

**Tech Stack:** Python logging module.

---

### Task 1: Create Logging Manager

**Files:**
- Create: `backend/app/core/logging_manager.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write `backend/app/core/logging_manager.py`**

```python
import logging
import os
import shutil

class LoggingManager:
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        self.current_handler = None

    def setup_run_logging(self, run_id: str):
        self.cleanup_run_logging()
        log_file = os.path.join(self.log_dir, f"run_{run_id}.log")
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        self.current_handler = handler
        return log_file

    def cleanup_run_logging(self):
        if self.current_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.current_handler)
            self.current_handler.close()
            self.current_handler = None

logging_manager = LoggingManager()
```

- [ ] **Step 2: Update `backend/app/main.py` to use `LoggingManager`**

Modify `backend/app/main.py` to remove the static `FileHandler` and only use `StreamHandler` initially.

```python
# ... (existing imports)
from app.core.logging_manager import logging_manager

# ... (inside logging configuration)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
# ...
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/logging_manager.py backend/app/main.py
git commit -m "feat: implement centralized LoggingManager"
```

### Task 2: Integrate into Pipeline Orchestrator

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Update Orchestrator to use LoggingManager**

In `backend/app/pipeline/orchestrator.py`, wrap the pipeline execution in `setup_run_logging` and `cleanup_run_logging`.

```python
# ...
from app.core.logging_manager import logging_manager

# ... inside PipelineOrchestrator ...
    def run_pipeline(self, run):
        log_file = logging_manager.setup_run_logging(run.run_id)
        logger.info(f"Logging started for run {run.run_id} at {log_file}")
        try:
            # ... existing logic ...
        finally:
            logging_manager.cleanup_run_logging()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/pipeline/orchestrator.py
git commit -m "feat: integrate per-run logging in pipeline"
```

### Task 3: Integrate into Backtest Engine

**Files:**
- Modify: `backend/app/backtest/engine.py`

- [ ] **Step 1: Update Backtest Engine to use LoggingManager**

```python
# ...
from app.core.logging_manager import logging_manager

# ... inside BacktestEngine ...
    def run_backtest(self, run_id, ...):
        log_file = logging_manager.setup_run_logging(run_id)
        logger.info(f"Logging started for backtest {run_id} at {log_file}")
        try:
            # ... existing logic ...
        finally:
            logging_manager.cleanup_run_logging()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/backtest/engine.py
git commit -m "feat: integrate per-run logging in backtest engine"
```
