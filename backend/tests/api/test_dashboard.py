import pytest

def test_get_screener_results(client):
    response = client.get("/api/screener/results")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_get_pipeline_latest(client):
    response = client.get("/api/pipeline/latest")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "market_context" in data
