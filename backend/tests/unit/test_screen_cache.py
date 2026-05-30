from app.screens.cache import ScreenCache


def test_screen_cache():
    cache = ScreenCache()
    cache.invalidate()  # clean start

    val = cache.get("screen:momentum:False")
    assert val is None

    cache.set("screen:momentum:False", [{"symbol": "RELIANCE"}], 300)
    val = cache.get("screen:momentum:False")
    assert val == [{"symbol": "RELIANCE"}]

    cache.invalidate()
    assert cache.get("screen:momentum:False") is None
