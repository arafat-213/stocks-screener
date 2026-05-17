from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app
import datetime

client = TestClient(app)

def test_health_check_enhanced_ok():
    # Mock DB success
    # Mock response_cache.stats()
    # Mock PipelineRun query
    
    with patch("app.db.session.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        # Mock SELECT 1
        mock_db.execute.return_value = None
        
        # Mock PipelineRun
        mock_run = MagicMock()
        mock_run.status = "complete"
        mock_run.timestamp = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
        
        with patch("app.main.response_cache") as mock_cache:
            mock_cache.stats.return_value = {"hits": 10, "misses": 2, "keys": 5}
            
            with patch("app.main.db_query_pipeline_run") as mock_query:
                mock_query.return_value = mock_run
                
                response = client.get("/api/health")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
                assert data["db"] == "ok"
                assert data["cache"] == {"hits": 10, "misses": 2, "keys": 5}
                assert data["pipeline"]["last_status"] == "complete"
                assert data["pipeline"]["is_stale"] is False
                assert data["version"] == "2.1.0"

def test_health_check_db_down():
    with patch("app.db.session.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.execute.side_effect = Exception("DB Down")
        
        with patch("app.main.response_cache") as mock_cache:
            mock_cache.stats.return_value = {"hits": 0, "misses": 0, "keys": 0}
            
            response = client.get("/api/health")
            assert response.status_code == 200 # We still return 200 but with error status in body
            data = response.json()
            assert data["status"] == "error"
            assert data["db"] == "error"

def test_health_check_stale_data():
    with patch("app.db.session.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        # Mock PipelineRun with old timestamp
        mock_run = MagicMock()
        mock_run.status = "complete"
        mock_run.timestamp = datetime.datetime.utcnow() - datetime.timedelta(hours=30)
        
        with patch("app.main.response_cache") as mock_cache:
            mock_cache.stats.return_value = {"hits": 10, "misses": 2, "keys": 5}
            
            with patch("app.main.db_query_pipeline_run") as mock_query:
                mock_query.return_value = mock_run
                
                response = client.get("/api/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "degraded"
                assert data["pipeline"]["is_stale"] is True
