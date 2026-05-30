import datetime

from app.db.models import FundamentalCache
from app.pipeline.screener import needs_cache_refresh


def test_needs_cache_refresh():
    seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)

    # Case 1: No cache
    assert needs_cache_refresh(None, seven_days_ago)

    # Case 2: Force refresh
    cache = FundamentalCache(symbol="TEST", force_refresh=True)
    assert needs_cache_refresh(cache, seven_days_ago)

    # Case 3: Old cache
    cache = FundamentalCache(
        symbol="TEST", last_updated=seven_days_ago - datetime.timedelta(days=1)
    )
    assert needs_cache_refresh(cache, seven_days_ago)

    # Case 4: Recent cache, no backoff
    cache = FundamentalCache(
        symbol="TEST",
        last_updated=datetime.datetime.utcnow() - datetime.timedelta(days=1),
        cache_version=1,
    )
    # Ensure cache_version matches CURRENT_SCREENER_VERSION in screener.py (which is 1)
    assert not needs_cache_refresh(cache, seven_days_ago)

    # Case 5: Recent cache, but in backoff
    cache = FundamentalCache(
        symbol="TEST",
        last_updated=datetime.datetime.utcnow()
        - datetime.timedelta(days=8),  # Age says YES
        retry_after=datetime.datetime.utcnow()
        + datetime.timedelta(hours=1),  # Backoff says NO
        cache_version=1,
    )
    assert not needs_cache_refresh(cache, seven_days_ago)

    # Case 6: Backoff expired
    cache = FundamentalCache(
        symbol="TEST",
        last_updated=seven_days_ago - datetime.timedelta(days=1),
        retry_after=datetime.datetime.utcnow() - datetime.timedelta(hours=1),
    )
    assert needs_cache_refresh(cache, seven_days_ago)

    print("All tests passed!")


if __name__ == "__main__":
    test_needs_cache_refresh()
