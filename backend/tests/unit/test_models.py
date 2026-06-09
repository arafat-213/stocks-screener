from app.db.models import TechnicalSignal


def test_technical_signal_ema_fields():
    signal = TechnicalSignal(
        symbol="AAPL.NS",
        ema5_level=150.5,
        ema13_level=149.0,
        ema21_level=145.0,
    )
    assert signal.ema5_level == 150.5
    assert signal.ema13_level == 149.0
    assert signal.ema21_level == 145.0
