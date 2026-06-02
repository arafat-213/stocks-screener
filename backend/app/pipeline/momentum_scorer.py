from typing import Any, Dict, Optional

import pandas as pd

from app.core.strategy import TechnicalStrategy
from app.core.trading_config import UnifiedTradingConfig


class MomentumScorer:
    """
    Deprecated: Use app.core.strategy.TechnicalStrategy directly.
    This class now acts as a shim for TechnicalStrategy to maintain backward compatibility
    during the Phase 3 transition.
    """

    def __init__(self, config: Optional[UnifiedTradingConfig] = None):
        self.strategy = TechnicalStrategy(config)

    def to_float(self, val) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Delegates to TechnicalStrategy.calculate_indicators
        """
        return self.strategy.calculate_indicators(df)

    def calculate_score(
        self, df: pd.DataFrame, timeframe: str = "D", i: int = -1, skip_ta: bool = False
    ) -> Dict[str, Any]:
        """
        Delegates to TechnicalStrategy.evaluate
        """
        return self.strategy.evaluate(df, timeframe=timeframe, i=i, skip_ta=skip_ta)
