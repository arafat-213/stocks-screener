from app.core.trading_config import UnifiedTradingConfig


def test_unified_trading_config_defaults():
    config = UnifiedTradingConfig()

    # New requirements
    assert config.max_sector_positions == 3
    assert config.regime_adx_floor == 15.0
    assert config.min_market_breadth_pct == 40.0
