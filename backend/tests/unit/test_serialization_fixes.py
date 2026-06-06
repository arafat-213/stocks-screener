from app.core.utils import sanitize_for_json
from app.pipeline.utils import to_float


def test_sanitize_for_json():
    data = {
        "nan": float("nan"),
        "inf": float("inf"),
        "ninf": float("-inf"),
        "list": [1.0, float("nan"), {"x": float("inf")}],
        "ok": 1.23,
    }
    sanitized = sanitize_for_json(data)
    assert sanitized["nan"] is None
    assert sanitized["inf"] is None
    assert sanitized["ninf"] is None
    assert sanitized["list"][1] is None
    assert sanitized["list"][2]["x"] is None
    assert sanitized["ok"] == 1.23


def test_to_float_robustness():
    # Regular values
    assert to_float(1.5) == 1.5
    assert to_float("1.5") == 1.5
    assert to_float(None) is None

    # Non-compliant values should return default (None)
    assert to_float(float("nan")) is None
    assert to_float(float("inf")) is None
    assert to_float(float("-inf")) is None

    # Custom default
    assert to_float("abc", default=0.0) == 0.0
    assert to_float(float("nan"), default=0.0) == 0.0
