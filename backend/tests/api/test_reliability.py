import pytest
import time
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.db.models import PipelineRun
from app.db.session import SessionLocal

client = TestClient(app)

def test_cors_configuration():
    """Verify that CORS is configured with explicit origins and allow_credentials=True"""
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"

def test_pipeline_concurrency_guard():
    """Verify that multiple concurrent pipelines are blocked with 409 Conflict"""
    # We use SessionLocal directly because run_pipeline_wrapper uses it
    db = SessionLocal()
    run = PipelineRun(status="running", run_id="test_run_concurrency")
    db.add(run)
    db.commit()
    
    try:
        # This request uses Depends(get_db) which we override in conftest
        # BUT trigger_screener checks the DB. If sqlite :memory: is used per session, 
        # this might still fail if not sharing engine.
        # However, for this test, we just want to see if the guard works.
        response = client.post("/api/screener/run", json={"limit": 1})
        assert response.status_code == 409
        assert "already running" in response.json()["detail"]
    finally:
        db.delete(run)
        db.commit()
        db.close()

def test_pipeline_stop_signal():
    """Verify that stop_pipeline updates the stop_requested flag in the DB"""
    db = SessionLocal()
    run = PipelineRun(status="running", run_id="test_run_stop")
    db.add(run)
    db.commit()
    
    try:
        response = client.post("/api/pipeline/stop")
        assert response.status_code == 200
        
        db.refresh(run)
        assert run.stop_requested is True
    finally:
        db.delete(run)
        db.commit()
        db.close()

def test_lifespan_health():
    """Basic health check to ensure app with lifespan starts correctly"""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
