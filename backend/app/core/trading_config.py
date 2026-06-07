import datetime
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass
class UnifiedTradingConfig:
    strategy_id: str = "default"
    rsi_min: float = 35.0
    rsi_max: float = 65.0
    score_threshold: float = 55.0
    holding_days: int = 50
    stop_loss_pct: float = 7.0
    target_pct: float = 0.0
    trailing_stop_pct: float = 0.0
    require_volume_breakout: bool = False
    use_regime_filter: bool = True
    require_weekly_confirmation: bool = False
    require_monthly_confirmation: bool = False
    atr_multiplier: float = 2.0
    risk_reward_ratio: float = 2.5
    use_atr_stops: bool = True
    min_adx: float = 25.0
    tier1_adx_threshold: float = (
        30.0  # ADX required for Tier 1 classification (independent of min_adx)
    )
    min_signal_tier: int = 2  # 1 = Strict (Both Vol + ADX), 2 = Relaxed (Either)
    timeframe: str = "D"
    date_from: datetime.date = None
    date_to: datetime.date = None
    symbol_limit: int = None
    screen_slug: Optional[str] = None
    starting_capital: float = 1000000.0
    position_size: float = 10000.0
    use_volatility_sizing: bool = True
    risk_per_trade_pct: float = 3.0
    max_position_pct: float = 20.0
    max_concurrent_positions: int = 0
    max_sector_positions: int = 3
    use_atr_trailing_stop: bool = True
    atr_trailing_multiplier: float = 1.0
    atr_trailing_activation: float = 2.5
    use_partial_exits: bool = False
    target_r_levels: Sequence[float] = (1.5, 2.5)
    use_signal_invalidation_exit: bool = False
    invalidation_threshold_pct: float = 3.0
    screen_signal_mode: bool = False  # When True, screen dates drive signals (Model B)
    screen_membership_window_days: int = 7
    screen_reentry_gap_days: int = 60
    screen_driven_rsi_max: float = 75.0
    require_consolidation: bool = True
    consolidation_bars: int = 15
    consolidation_max_range_pct: float = 12.0
    use_pullback_entry: bool = True
    pullback_max_wait_bars: int = 8
    pullback_tolerance_pct: float = 3.0

    # Indicator Weights (Phase 3 & 4 Architectural Unification)
    ema_weight: float = 28.5
    macd_weight: float = 21.5
    rsi_weight: float = 21.5
    volume_weight: float = 21.5
    trend_weight: float = 7.0
    ema200_weight: float = 7.0

    # State Engine Parameters (Phase 4)
    rsi_overbought_threshold: float = 80.0
    use_state_based_exits: bool = True
    rsi_recovery_lookback: int = 5

    use_regime_position_scaling: bool = True
    regime_bull_rsi_threshold: float = 60.0
    regime_bear_rsi_threshold: float = 45.0
    regime_adx_threshold: float = 20.0
    regime_adx_floor: float = 15.0
    min_market_breadth_pct: float = 40.0
    regime_bull_position_pct: float = 12.0
    regime_neutral_position_pct: float = 7.0
    regime_bear_position_pct: float = 0.0
    regime_confirmation_days: int = 5

    @classmethod
    def from_dict(cls, data: dict) -> "UnifiedTradingConfig":
        """Reconstruct config from a dictionary, handling date parsing."""
        d = data.copy()
        for field in ["date_from", "date_to"]:
            val = d.get(field)
            if isinstance(val, str) and val:
                try:
                    d[field] = datetime.date.fromisoformat(val)
                except ValueError:
                    d[field] = None
        return cls(**d)

    @property
    def effective_score_threshold(self) -> float:
        """
        Score threshold compared against TechnicalStrategy.evaluate() output.
        Practical score range: 0–100 (hard cap). Real ceiling ~97 due to
        MACD/EMA same-day correlation cap. Default 55.0 = roughly 56% of max.
        """
        return self.score_threshold


# Strategy Presets
TREND_INITIATION = UnifiedTradingConfig(
    strategy_id="initiation",
    rsi_min=35.0,
    rsi_max=65.0,
    require_consolidation=True,
    use_pullback_entry=True,
    holding_days=45,
    atr_multiplier=2.0,
    risk_reward_ratio=2.5,
)

TREND_CONTINUATION = UnifiedTradingConfig(
    strategy_id="continuation",
    rsi_min=50.0,
    rsi_max=78.0,
    require_consolidation=False,
    use_pullback_entry=False,
    holding_days=30,
    atr_multiplier=2.5,
    risk_reward_ratio=2.0,
    screen_signal_mode=True,
    screen_slug="momentum-monsters",
    screen_driven_rsi_max=78.0,
)
