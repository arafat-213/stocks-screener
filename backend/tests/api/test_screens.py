import pytest

def test_list_screens(client):
    response = client.get("/api/screens/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "slug" in data[0]
    assert "label" in data[0]
    assert "description" in data[0]
    assert "category" in data[0]

def test_get_screen_results_not_found(client):
    response = client.get("/api/screens/non-existent-slug")
    assert response.status_code == 404
    assert response.json()["detail"] == "Screen not found"

def test_get_screen_results_empty(client):
    # Use a real slug but with live=False. 
    # Even if DB is empty, it should fallback to live or return empty list if no data at all.
    response = client.get("/api/screens/52w-high?live=false")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
