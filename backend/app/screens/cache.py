from app.core.cache import ResponseCache

# We use a dedicated ResponseCache instance for screens
_screen_cache_store = ResponseCache()


class ScreenCache:
    def get(self, key: str) -> list[dict] | None:
        val, hit = _screen_cache_store.get(key)
        return val if hit else None

    def set(self, key: str, value: list[dict], ttl_seconds: int) -> None:
        _screen_cache_store.set(key, value, ttl_seconds)

    def invalidate(self, slug: str | None = None) -> None:
        if slug is None:
            _screen_cache_store.invalidate()
        else:
            _screen_cache_store.invalidate(f"screen:{slug}:False")
            _screen_cache_store.invalidate(f"screen:{slug}:True")

    def stats(self) -> dict:
        return _screen_cache_store.stats()


screen_cache = ScreenCache()
