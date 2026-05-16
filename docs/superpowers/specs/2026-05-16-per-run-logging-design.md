# Logging Strategy Design: Per-Run Logging

## Overview
Implement a per-run logging strategy to improve log manageability. Each pipeline run and backtest session will generate a dedicated log file, helping isolate issues and keep individual logs manageable.

## Proposed Changes

### 1. Centralized Log Manager
Create a new utility `backend/app/core/logging_manager.py` that provides functionality to:
- Configure the root logger to send logs to `stdout` (for console monitoring).
- Provide a `setup_run_logging(run_id: str, log_dir: str)` function that adds a `FileHandler` for a specific run ID.
- Provide a `cleanup_run_logging()` function to remove the file handler when the run is finished.

### 2. Pipeline Integration
- In `backend/app/pipeline/orchestrator.py`, wrap the pipeline execution logic in a context manager or explicit setup/cleanup that calls `setup_run_logging` with the current `run_id`.

### 3. Backtest Engine Integration
- In `backend/app/backtest/engine.py`, ensure that `setup_run_logging` is called with the backtest `run_id` before the backtest process starts.

### 4. Main Configuration Update
- Update `backend/app/main.py` to remove the global `pipeline.log` `FileHandler` and keep only the `StreamHandler`.
- Ensure the application logs still capture process-level events.

## Benefits
- Clear isolation of logs per run.
- Easier to associate logs with specific pipeline failures.
- Prevents unbounded growth of a single `pipeline.log` file.
