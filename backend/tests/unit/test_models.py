from app.db.models import TechnicalSignal

def test_technical_signal_ema_fields():
    signal = TechnicalSignal(
        symbol="AAPL",
        ema5_level=150.5,
        ema13_level=149.0,
        ema20_level=145.0,
        ema26_level=142.5
    )
    assert signal.ema5_level == 150.5
    assert signal.ema13_level == 149.0
    assert signal.ema20_level == 145.0
    assert signal.ema26_level == 142.5
