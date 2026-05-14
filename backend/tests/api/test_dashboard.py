import pytest

def test_get_screener_results(client):
    response = client.get("/api/dashboard/screener/results")
    assert response.status_code == 200
    # The response is now a dict with "items" key, not a list
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)

def test_get_pipeline_latest(client):
    response = client.get("/api/dashboard/pipeline/latest")
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
