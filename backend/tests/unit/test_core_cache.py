import time
import pytest
from app.core.cache import ResponseCache

def test_response_cache_basic_operations():
    cache = ResponseCache()
    # Initial get
    val, hit = cache.get("test_key")
    assert hit is False
    assert val is None
    
    # Set and get
    cache.set("test_key", {"data": 123}, 1) # 1 second TTL
    val, hit = cache.get("test_key")
    assert hit is True
    assert val == {"data": 123}
    
    # Expiration
    time.sleep(1.1)
    val, hit = cache.get("test_key")
    assert hit is False
    
    # Invalidation
    cache.set("key2", 456, 10)
    cache.invalidate("key2")
    _, hit = cache.get("key2")
    assert hit is False
    
    # Stats
    cache.set("key3", 789, 10)
    stats = cache.stats()
    assert stats["keys"] == 1
    assert stats["hits"] >= 1
