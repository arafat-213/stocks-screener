import time
import threading
from typing import Any
from collections import OrderedDict

class ResponseCache:
    """Thread-safe in-process TTL cache with LRU eviction."""
    
    def __init__(self, max_size: int = 500):
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
    
    def get(self, key: str) -> tuple[Any, bool]:
        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None, False
                
            value, expires_at = self._store[key]
            if time.time() > expires_at:
                del self._store[key]
                self._misses += 1
                return None, False
                
            self._store.move_to_end(key)
            self._hits += 1
            return value, True
    
    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, time.time() + ttl)
            
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)
                self._evictions += 1
    
    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            elif key in self._store:
                del self._store[key]
    
    def stats(self) -> dict:
        with self._lock:
            return {
                "hits": self._hits, 
                "misses": self._misses, 
                "evictions": self._evictions,
                "keys": len(self._store),
                "max_size": self._max_size
            }

response_cache = ResponseCache(max_size=500)
