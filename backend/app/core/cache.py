import time
from typing import Any

class ResponseCache:
    """Thread-safe in-process TTL cache. No external dependencies."""
    
    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> tuple[Any, bool]:
        """Returns (value, is_hit). is_hit=False means expired or absent."""
        if key not in self._store:
            self._misses += 1
            return None, False
            
        value, expires_at = self._store[key]
        if time.time() > expires_at:
            del self._store[key]
            self._misses += 1
            return None, False
            
        self._hits += 1
        return value, True
    
    def set(self, key: str, value: Any, ttl: int) -> None:
        self._store[key] = (value, time.time() + ttl)
    
    def invalidate(self, key: str | None = None) -> None:
        """key=None clears everything."""
        if key is None:
            self._store.clear()
        elif key in self._store:
            del self._store[key]
    
    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses, "keys": len(self._store)}

response_cache = ResponseCache()
