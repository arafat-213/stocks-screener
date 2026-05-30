from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.cache import response_cache
from app.main import app
from app.screens.cache import screen_cache

client = TestClient(app)


def setup_function():
    response_cache.invalidate()
    screen_cache.invalidate()


def test_screens_caching():
    # 1. First request - MISS
    response = client.get("/api/screens/52w-high")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"

    # 2. Second request - HIT
    response = client.get("/api/screens/52w-high")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "HIT"


def test_screens_cache_clear():
    # 1. Populate cache
    client.get("/api/screens/52w-high")
    response = client.get("/api/screens/52w-high")
    assert response.headers["X-Cache"] == "HIT"

    # 2. Clear cache
    response = client.post("/api/screens/cache/clear")
    assert response.status_code == 200

    # 3. Verify MISS
    response = client.get("/api/screens/52w-high")
    assert response.headers["X-Cache"] == "MISS"


@patch("app.routers.dashboard.get_live_market_data")
def test_dashboard_live_market_caching(mock_get_market):
    mock_get_market.return_value = [
        {"symbol": "^NSEI", "close": 20000, "change_pct": 1.5}
    ]
    # 1. First request - MISS
    response = client.get("/api/dashboard/market/live")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"

    # 2. Second request - HIT
    response = client.get("/api/dashboard/market/live")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "HIT"


def test_dashboard_screener_results_caching():
    # 1. First request - MISS
    response = client.get("/api/dashboard/screener/results")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"

    # 2. Second request - HIT
    response = client.get("/api/dashboard/screener/results")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "HIT"


def test_dashboard_pipeline_status_caching():
    # 1. First request - MISS
    response = client.get("/api/dashboard/pipeline/latest")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"

    # 2. Second request - HIT
    response = client.get("/api/dashboard/pipeline/latest")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "HIT"
