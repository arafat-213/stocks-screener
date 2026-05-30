import sqlalchemy.exc


def classify_error(exc: Exception) -> str:
    """Returns one of: 'rate_limit', 'empty_data', 'db_write', 'timeout', 'unknown'"""
    msg = str(exc).lower()
    if "429" in msg or "too many requests" in msg or "rate limit" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if isinstance(exc, sqlalchemy.exc.SQLAlchemyError):
        return "db_write"
    if "empty data" in msg or "no data found" in msg:
        return "empty_data"
    return "unknown"
