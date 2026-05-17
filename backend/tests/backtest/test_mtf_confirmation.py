import pytest
import pandas as pd
import datetime
import json
from app.backtest.engine import build_mtf_state_map, simulate_trades, BacktestConfig
from app.routers.backtest import BacktestRequest, _serialize_run
from app.db import models as db_models

def test_build_mtf_state_map_empty():
    """Test with empty dataframe."""
    assert build_mtf_state_map(None, 'W') == {}
    assert build_mtf_state_map(pd.DataFrame(), 'W') == {}

def test_build_mtf_state_map_insufficient_history():
    """Test with very little data (less than required for technical scoring)."""
    # Weekly needs 60 bars (approx 14 months of daily data)
    # Monthly needs 24 bars (approx 2 years of daily data)
    dates = pd.date_range(start='2023-01-01', periods=10, freq='D')
    df = pd.DataFrame({
        'Open': [100.0] * 10,
        'High': [105.0] * 10,
        'Low': [95.0] * 10,
        'Close': [102.0] * 10,
        'Volume': [1000] * 10
    }, index=dates)
    
    # After resampling 'W', we get 1 full week and maybe an incomplete one.
    # drop_incomplete=True will leave very few bars.
    assert build_mtf_state_map(df, 'W') == {}

def test_build_mtf_state_map_uptrend():
    """Test that an uptrend is correctly identified as bullish."""
    # We need 60 weekly bars + some buffer.
    # 60 * 7 = 420 days. Let's provide 500 days of data.
    dates = pd.date_range(start='2022-01-01', periods=500, freq='D')
    # Create a strong uptrend
    close_prices = [100.0 + i * 0.5 for i in range(500)]
    df = pd.DataFrame({
        'Open': [p - 1 for p in close_prices],
        'High': [p + 2 for p in close_prices],
        'Low': [p - 2 for p in close_prices],
        'Close': close_prices,
        'Volume': [1000] * 500
    }, index=dates)
    
    state_map = build_mtf_state_map(df, 'W')
    assert len(state_map) > 0
    # The last few bars should definitely be bullish in a strong uptrend
    last_date = sorted(state_map.keys())[-1]
    assert state_map[last_date] is True

def test_build_mtf_state_map_no_look_ahead_bias():
    """Test that scoring of a bar only depends on data up to that bar."""
    dates = pd.date_range(start='2022-01-01', periods=500, freq='D')
    close_prices = [100.0 + i * 0.5 for i in range(500)]
    df = pd.DataFrame({
        'Open': [p - 1 for p in close_prices],
        'High': [p + 2 for p in close_prices],
        'Low': [p - 2 for p in close_prices],
        'Close': close_prices,
        'Volume': [1000] * 500
    }, index=dates)
    
    state_map_full = build_mtf_state_map(df, 'W')
    
    # Now score only half the data
    df_half = df.iloc[:250]
    state_map_half = build_mtf_state_map(df_half, 'W')
    
    # Check that for all common dates, the results are identical
    for date in state_map_half:
        assert state_map_half[date] == state_map_full[date]

def test_build_mtf_state_map_downtrend():
    """Test that a downtrend is correctly identified as non-bullish."""
    dates = pd.date_range(start='2022-01-01', periods=500, freq='D')
    # Create a strong downtrend
    close_prices = [500.0 - i * 0.5 for i in range(500)]
    df = pd.DataFrame({
        'Open': [p + 1 for p in close_prices],
        'High': [p + 2 for p in close_prices],
        'Low': [p - 2 for p in close_prices],
        'Close': close_prices,
        'Volume': [1000] * 500
    }, index=dates)
    
    state_map = build_mtf_state_map(df, 'W')
    assert len(state_map) > 0
    # The last few bars should definitely be non-bullish in a strong downtrend
    last_date = sorted(state_map.keys())[-1]
    assert state_map[last_date] is False

class TestMTFGates:
    @pytest.fixture
    def setup_data(self):
        dates = pd.date_range(start='2023-01-01', periods=20, freq='D')
        df = pd.DataFrame({
            'Open': [100.0] * 20,
            'High': [105.0] * 20,
            'Low': [95.0] * 20,
            'Close': [102.0] * 20,
            'Volume': [1000] * 20
        }, index=dates)
        
        scored_dates = [
            {
                'date': dates[5],
                'score': 70.0,
                'is_bullish': True,
                'rsi': 50.0,
                'adx': 30.0,
                'ema_signal': 'bullish',
                'volume_breakout': True,
                'above_200ema': True,
            }
        ]
        
        config = BacktestConfig(
            score_threshold=60.0,
            require_volume_breakout=True,
            min_adx=25.0,
            require_weekly_confirmation=False,
            require_monthly_confirmation=False,
            use_regime_filter=False
        )
        
        return df, scored_dates, config

    def test_weekly_gate_bypassed_when_none(self, setup_data):
        """Should accept trade if weekly_state_map is None even if required."""
        df, scored_dates, config = setup_data
        config.require_weekly_confirmation = True
        
        trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config, weekly_state_map=None)
        assert len(trades) == 1

    def test_weekly_gate_rejects_false(self, setup_data):
        """Should reject trade if weekly state is False."""
        df, scored_dates, config = setup_data
        config.require_weekly_confirmation = True
        
        # Weekly bar date must be <= signal date (2023-01-06)
        weekly_state_map = {datetime.date(2023, 1, 1): False}
        
        trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config, weekly_state_map=weekly_state_map)
        assert len(trades) == 0

    def test_weekly_gate_accepts_true(self, setup_data):
        """Should accept trade if weekly state is True."""
        df, scored_dates, config = setup_data
        config.require_weekly_confirmation = True
        
        weekly_state_map = {datetime.date(2023, 1, 1): True}
        
        trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config, weekly_state_map=weekly_state_map)
        assert len(trades) == 1

    def test_monthly_gate_rejects_false(self, setup_data):
        """Should reject trade if monthly state is False."""
        df, scored_dates, config = setup_data
        config.require_monthly_confirmation = True
        
        monthly_state_map = {datetime.date(2023, 1, 1): False}
        
        trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config, monthly_state_map=monthly_state_map)
        assert len(trades) == 0

    def test_both_gates_active(self, setup_data):
        """Should accept only if both gates are True."""
        df, scored_dates, config = setup_data
        config.require_weekly_confirmation = True
        config.require_monthly_confirmation = True
        
        # 1. Weekly True, Monthly False -> Reject
        weekly_map = {datetime.date(2023, 1, 1): True}
        monthly_map = {datetime.date(2023, 1, 1): False}
        trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config, weekly_map, monthly_map)
        assert len(trades) == 0
        
        # 2. Both True -> Accept
        monthly_map = {datetime.date(2023, 1, 1): True}
        trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config, weekly_map, monthly_map)
        assert len(trades) == 1

    def test_gate_fail_closed_no_preceding_bar(self, setup_data):
        """Should reject if no bar in map predates the signal."""
        df, scored_dates, config = setup_data
        config.require_weekly_confirmation = True
        
        # Signal is 2023-01-06. Map only has later date.
        weekly_state_map = {datetime.date(2023, 1, 10): True}
        
        trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config, weekly_state_map=weekly_state_map)
        assert len(trades) == 0

class TestBacktestRequestDefaults:
    def test_defaults(self):
        r = BacktestRequest()
        assert r.require_weekly_confirmation is True
        assert r.require_monthly_confirmation is False

class TestSerializeRunConfigBlock:
    def test_serialization(self):
        config_dict = BacktestRequest(require_weekly_confirmation=False).model_dump()
        run = db_models.BacktestRun(config=json.dumps(config_dict))
        serialised = _serialize_run(run, include_curve=False)
        assert serialised["config"]["require_weekly_confirmation"] is False
        assert serialised["config"]["require_monthly_confirmation"] is False
