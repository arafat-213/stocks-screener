def to_float(val, default=None):
    """Safely converts a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
