from app.pipeline.scorer import calculate_fundamental_score


def test_roe_normalization():
    # Test ROE as decimal (0.15)
    info_decimal = {"returnOnEquity": 0.20}
    score_decimal = calculate_fundamental_score(info_decimal)
    # Expected: ROE > 0.15 gives 5 pts. PE/Pledge/ROCE/DE are 0.
    assert score_decimal == 5.0

    # Test ROE as percentage (20.0)
    info_percent = {"returnOnEquity": 20.0}
    score_percent = calculate_fundamental_score(info_percent)
    # Expected: 20.0 / 100 = 0.20, which gives 5 pts.
    assert score_percent == 5.0


def test_roce_normalization():
    # Test ROCE as decimal (0.20)
    class MockCache:
        def __init__(self, roce):
            self.roce = roce
            self.roe = None
            self.de_ratio = None

    cache_decimal = MockCache(0.20)
    score_decimal = calculate_fundamental_score({}, fund_cache=cache_decimal)
    assert score_decimal == 5.0

    # Test ROCE as percentage (20.0)
    cache_percent = MockCache(20.0)
    score_percent = calculate_fundamental_score({}, fund_cache=cache_percent)
    assert score_percent == 5.0


def test_de_normalization_check():
    # Test DE as percentage (50.0)
    info = {"debtToEquity": 40.0}
    score = calculate_fundamental_score(info)
    # 40.0 / 100 = 0.4. D/E < 0.5 gives 5 pts.
    assert score == 5.0

    info_high = {"debtToEquity": 80.0}
    score_high = calculate_fundamental_score(info_high)
    # 80.0 / 100 = 0.8. 0.5 < D/E < 1.0 gives 2 pts.
    assert score_high == 2.0
