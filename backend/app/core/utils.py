import math
from typing import Any


def sanitize_for_json(data: Any) -> Any:
    """
    Recursively replaces non-JSON compliant float values (NaN, Inf, -Inf)
    with None. This ensures the API doesn't crash during serialization.
    """
    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_for_json(i) for i in data]
    elif isinstance(data, float):
        if not math.isfinite(data):
            return None
    return data
