from app.db.models import TechnicalSignal
from app.pipeline.trade_setup import compute_trade_setup

def test_compute_trade_setup_pullback():
    signal = TechnicalSignal(
        close_price=100.0,
        atr=2.5,
        ema_signal="bullish_pullback",
        ema20_level=98.0,
        resistance_level=105.0,
        pct_from_resistance=-4.7
    )
    
    setup = compute_trade_setup(signal)
    
    assert setup["setup_type"] == "pullback_to_ema20"
    assert setup["entry_zone"]["low"] == 97.02  # 98.0 * 0.99
    assert setup["entry_zone"]["high"] == 98.98 # 98.0 * 1.01
    assert setup["stop_loss"] == 93.00          # 98.0 - (2.0 * 2.5)
    assert setup["stop_basis"] == "2.0× ATR below entry"
    assert setup["atr"] == 2.5
    assert setup["risk_per_share"] == 5.0       # 98.0 - 93.0
    assert setup["targets"][0]["level"] == 105.5  # 98.0 + (1.5 * 5.0)
    assert setup["targets"][0]["rr"] == 1.5
