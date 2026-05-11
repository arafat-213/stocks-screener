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

def test_get_dashboard_changes(client):
    response = client.get("/api/dashboard/changes")
    assert response.status_code == 200
    data = response.json()
    assert "changes" in data
    assert "as_of" in data
    assert "prev_date" in data
    assert isinstance(data["changes"], list)
