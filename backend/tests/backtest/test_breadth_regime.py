import pandas as pd
import pytest

from app.backtest.engine import _build_regime_map
from app.core.trading_config import UnifiedTradingConfig


def test_regime_map_breadth_overrides():
    # Mock benchmark data: Low ADX (10), RSI Neutral (50), Price > EMA200
    dates = pd.date_range("2023-01-01", periods=10)
    bench_df = pd.DataFrame(
        {
            "Close": [100.0] * 10,
            "RSI_14": [50.0] * 10,
            "ADX_14": [10.0] * 10,
            "EMA_200": [90.0] * 10,
        },
        index=dates,
    )

    config = UnifiedTradingConfig(
        regime_adx_floor=15.0,
        min_market_breadth_pct=40.0,
        regime_bull_position_pct=12.0,
        regime_neutral_position_pct=7.0,
        regime_bear_position_pct=0.0,
        regime_confirmation_days=1,  # Set to 1 for immediate switch in test
    )

    # Case 1: Low ADX + High Breadth (70) -> BULL (12%)
    breadth_map = {d.date(): 70.0 for d in dates}
    rmap = _build_regime_map(bench_df, config, breadth_map=breadth_map)
    # Check index 1 because index 0 might still be the start state
    assert rmap[dates[1].date()] == 12.0

    # Case 2: Low ADX + Low Breadth (30) -> BEAR (0%)
    breadth_map = {d.date(): 30.0 for d in dates}
    rmap = _build_regime_map(bench_df, config, breadth_map=breadth_map)
    assert rmap[dates[1].date()] == 0.0

    # Case 3: Low ADX + Mid Breadth (50) -> NEUTRAL (7%)
    breadth_map = {d.date(): 50.0 for d in dates}
    rmap = _build_regime_map(bench_df, config, breadth_map=breadth_map)
    assert rmap[dates[1].date()] == 7.0


if __name__ == "__main__":
    pytest.main([__file__])
