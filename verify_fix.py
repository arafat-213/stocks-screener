
import pandas as pd
import datetime
from app.backtest.engine import simulate_trades, BacktestConfig, _compute_all_indicators
from app.core.strategy import TechnicalStrategy

def test_fix():
    dates = pd.date_range(start="2023-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "Open": [100.0] * 100,
        "High": [105.0] * 100,
        "Low": [95.0] * 100,
        "Close": [102.0] * 100,
        "Volume": [1000] * 100,
    }, index=dates)

    config = BacktestConfig(
        use_state_based_exits=True,
        require_weekly_confirmation=False,
        require_monthly_confirmation=False
    )
    strategy = TechnicalStrategy(config)

    # Mimic the fix in run_backtest
    print("Enriching DF...")
    df = _compute_all_indicators(df, strategy)

    scored_dates = [{
        "date": dates[50],
        "score": 80.0,
        "is_bullish": True,
        "rsi": 50.0,
        "adx": 30.0,
        "ema_signal": "bullish",
        "volume_breakout": True,
        "above_200ema": True,
        "is_consolidating": True,
        "atr": 5.0
    }]

    print("Starting simulate_trades with enriched DF...")
    try:
        trades = simulate_trades(
            "TEST.NS", "Tech", df, scored_dates, config, strategy
        )
        print("Success! Trades found:", len(trades))
    except Exception as e:
        print("CRASHED!")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fix()
