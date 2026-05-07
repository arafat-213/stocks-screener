from fastapi.testclient import TestClient
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_screener_results():
    response = client.get("/api/screener/results")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_get_pipeline_latest():
    response = client.get("/api/pipeline/latest")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "market_context" in data

