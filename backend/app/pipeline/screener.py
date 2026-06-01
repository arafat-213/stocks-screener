import datetime
import logging

logger = logging.getLogger(__name__)

CURRENT_SCREENER_VERSION = 1

DE_LIMITS = {
    "Financial Services": 10,
    "Insurance": 8,
    "Real Estate": 4,
    "Utilities": 3,
    "default": 2,
}


def needs_cache_refresh(cache, seven_days_ago: datetime.datetime) -> bool:
    """Checks if FundamentalCache entry needs refreshing based on age, version or force flag."""
    if not cache:
        return True
    if getattr(cache, "force_refresh", False):
        return True

    # Version check
    if (getattr(cache, "cache_version", 0) or 0) < CURRENT_SCREENER_VERSION:
        return True

    # Backoff check (Takes precedence over age)
    retry_after = getattr(cache, "retry_after", None)
    if retry_after and datetime.datetime.now(datetime.timezone.utc) < retry_after:
        return False

    # Age check
    last_upd = getattr(cache, "last_updated", None)
    if not last_upd or last_upd < seven_days_ago:
        return True

    return False
