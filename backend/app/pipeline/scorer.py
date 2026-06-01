from app.pipeline.momentum_scorer import MomentumScorer

_scorer = MomentumScorer()


def calculate_technical_indicators(df):
    """Compatibility shim for legacy scorer calls."""
    return _scorer.calculate_technical_indicators(df)


def calculate_technical_score(df, timeframe="D", i=-1, skip_ta=False):
    """Compatibility shim for legacy scorer calls."""
    return _scorer.calculate_score(df, timeframe=timeframe, i=i, skip_ta=skip_ta)
