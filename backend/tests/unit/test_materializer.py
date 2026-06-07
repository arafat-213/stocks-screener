import pytest
from unittest.mock import MagicMock, patch

from app.db.models import ScreenResult
from app.screens.materializer import materialize_all_screens


def test_materialize_all_screens_handles_various_types():
    db = MagicMock()

    # Mock data for different screens
    mock_results = {
        "tuple-screen": [("RELIANCE.NS", 85.5)],
        "dict-screen": [{"symbol": "TCS.NS", "score": 90.0, "timeframe": "W"}],
        "obj-screen": [MagicMock(symbol="INFY.NS", entry_score=95.0, timeframe="D")],
    }

    # Mock registry
    mock_registry = {
        slug: {"fn": lambda db, target_date=None, s=slug: mock_results[s]}
        for slug in mock_results
    }

    with patch("app.screens.materializer.SCREEN_REGISTRY", mock_registry):
        materialize_all_screens(db)

    # Check if delete was called (truncation)
    db.query.assert_any_call(ScreenResult)

    # Check if add was called for each result
    # We expect 3 additions
    assert db.add.call_count == 3

    added_objs = [call.args[0] for call in db.add.call_args_list]

    # Find results by slug
    tuple_res = next(r for r in added_objs if r.screen_slug == "tuple-screen")
    assert tuple_res.symbol == "RELIANCE.NS"
    assert tuple_res.score_used == 85.5
    assert tuple_res.timeframe == "D"

    dict_res = next(r for r in added_objs if r.screen_slug == "dict-screen")
    assert dict_res.symbol == "TCS.NS"
    assert dict_res.score_used == 90.0
    assert dict_res.timeframe == "W"

    obj_res = next(r for r in added_objs if r.screen_slug == "obj-screen")
    assert obj_res.symbol == "INFY.NS"
    assert obj_res.score_used == 95.0
    assert obj_res.timeframe == "D"


def test_materialize_all_screens_default_score():
    db = MagicMock()

    mock_results = {
        "no-score-tuple": [("TATASTEEL.NS",)],
        "no-score-dict": [{"symbol": "HDFCBANK.NS"}],
        "no-score-obj": [MagicMock(symbol="SBIN.NS")],
    }

    # Mock registry
    mock_registry = {
        slug: {"fn": lambda db, target_date=None, s=slug: mock_results[s]}
        for slug in mock_results
    }

    # Ensure MagicMock(symbol="SBIN.NS") doesn't have entry_score
    del mock_results["no-score-obj"][0].entry_score

    with patch("app.screens.materializer.SCREEN_REGISTRY", mock_registry):
        materialize_all_screens(db)

    added_objs = [call.args[0] for call in db.add.call_args_list]

    for res in added_objs:
        assert res.score_used == 0.0

def test_materialize_all_screens_transaction_safety():
    """
    Verifies that the materializer behaves atomically.
    If any screen fails, the entire day's materialization (including delete) is rolled back.
    """
    db = MagicMock()
    
    # Mock registry with two screens, the second one will fail
    mock_results = {
        "success-screen": [("RELIANCE.NS", 85.5)],
    }
    
    def fail_fn(db, target_date=None):
        raise Exception("Boom!")

    mock_registry = {
        "success-screen": {"fn": lambda db, target_date=None: mock_results["success-screen"]},
        "fail-screen": {"fn": fail_fn},
    }

    with patch("app.screens.materializer.SCREEN_REGISTRY", mock_registry):
        with pytest.raises(Exception, match="Boom!"):
            materialize_all_screens(db)

    # Atomic behavior check:
    # 1. No commits occurred
    # 2. Rollback occurred once for the entire batch
    assert db.commit.call_count == 0
    assert db.rollback.call_count == 1
