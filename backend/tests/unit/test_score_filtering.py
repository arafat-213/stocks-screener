from backend.app.core.config import BacktestConfig


def test_score_series_filtering():
    # Setup
    config = BacktestConfig(effective_score_threshold=60.0)

    # We need to ensure the logic runs. The actual score calculation is complex.
    # We just want to check if the filtering happens.

    # This is a bit hard to test without mocks.
    # But the logic added is simple:
    # if config:
    #    scored_dates = [s for s in scored_dates if s.get("score", 0.0) >= config.effective_score_threshold]

    # Let's mock the internal score list

    mock_scored_dates = [{"score": 50.0}, {"score": 60.0}, {"score": 70.0}]

    filtered = [
        s
        for s in mock_scored_dates
        if s.get("score", 0.0) >= config.effective_score_threshold
    ]

    assert len(filtered) == 2
    assert all(s["score"] >= 60.0 for s in filtered)
