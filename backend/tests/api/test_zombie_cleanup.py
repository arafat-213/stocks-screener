import pytest
from sqlalchemy.orm import Session
from app.db.models import PipelineRun
from app.pipeline.orchestrator import cleanup_zombie_runs, request_pipeline_stop
from app.db.session import SessionLocal

def test_cleanup_zombie_runs(db: Session):
    # 1. Create a zombie run
    zombie = PipelineRun(status="running", run_id="zombie_run_1")
    db.add(zombie)
    db.commit()

    # 2. Run cleanup
    cleanup_zombie_runs(db)
    
    # 3. Verify status changed to failed
    db.refresh(zombie)
    assert zombie.status == "failed"
    assert "Interrupted" in zombie.errors

def test_force_stop_logic(db: Session):
    # 1. Create a running run
    run = PipelineRun(status="running", run_id="force_stop_test")
    db.add(run)
    db.commit()

    # 2. First stop request (sets flag)
    request_pipeline_stop(db)
    db.refresh(run)
    assert run.stop_requested is True
    assert run.status == "running"

    # 3. Second stop request (force stops)
    request_pipeline_stop(db)
    db.refresh(run)
    assert run.status == "stopped"
    assert "Force stopped" in run.errors
