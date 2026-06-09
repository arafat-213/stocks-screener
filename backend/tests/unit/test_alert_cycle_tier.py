import datetime
from unittest.mock import patch

from app.alerts.engine import run_alert_cycle
from app.core.trading_config import UnifiedTradingConfig
from app.db.models import FundamentalCache, Stock, TechnicalSignal


@patch("app.alerts.engine.send_alert_email")
@patch("app.alerts.engine.build_signal_email")
@patch("app.alerts.engine.get_market_regime")
def test_run_alert_cycle_tier_calculation(
    mock_regime, mock_build_email, mock_send_email, db
):
    # Setup
    mock_regime.return_value = True
    mock_send_email.return_value = "test-email-id"
    signal_date = datetime.date(2024, 1, 10)

    # Create test data
    stock = Stock(symbol="TIER.NS", name="Tier Test", sector="Tech")
    db.add(stock)

    # Tier 1 case: volume_breakout=True, adx >= tier1_adx_threshold(30)
    tech = TechnicalSignal(
        symbol="TIER.NS",
        date=datetime.datetime.combine(signal_date, datetime.time.min),
        timeframe="D",
        ema_signal="bullish_cross",
        above_200ema=True,
        rsi=50.0,
        momentum_12m=10.0,
        volume_breakout=True,
        adx=35.0,
        close_price=100.0,
        ema21_level=95.0,
        entry_score=85.0,
        is_consolidating=True,
    )
    db.add(tech)

    fund = FundamentalCache(
        symbol="TIER.NS",
        profitability_streak_passed=True,
        de_check_passed=True,
        fcf_positive=True,
    )
    db.add(fund)
    db.commit()

    config = UnifiedTradingConfig(
        strategy_id="test",
        rsi_min=30,
        rsi_max=70,
        min_adx=20,
        tier1_adx_threshold=30,
        require_consolidation=True,
    )

    # Run
    run_alert_cycle(db, signal_date=signal_date, config=config)

    # Verify
    args, _ = mock_build_email.call_args
    signals = args[0]

    assert len(signals) == 1
    assert signals[0]["symbol"] == "TIER.NS"
    assert signals[0]["signal_tier"] == 1
