import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.cache import response_cache
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

def test_dashboard_live_market_caching():
    # 1. First request - MISS
    response = client.get("/api/market/live")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"
    
    # 2. Second request - HIT
    response = client.get("/api/market/live")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "HIT"

def test_dashboard_screener_results_caching():
    # 1. First request - MISS
    response = client.get("/api/screener/results")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"
    
    # 2. Second request - HIT
    response = client.get("/api/screener/results")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "HIT"

def test_dashboard_pipeline_status_caching():
    # 1. First request - MISS
    response = client.get("/api/pipeline/latest")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"
    
    # 2. Second request - HIT
    response = client.get("/api/pipeline/latest")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "HIT"
