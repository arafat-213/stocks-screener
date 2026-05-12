from dataclasses import dataclass
import datetime

@dataclass
class BacktestConfig:
    score_threshold: float = 60.0      # minimum score to trigger a trade
    holding_days: int = 20             # trading days to hold
    stop_loss_pct: float = 7.0         # exit if price drops this % (0 = disabled)
    target_pct: float = 0.0            # exit if price rises this % (0 = disabled)
    include_fundamentals: bool = False  # use current fundamental data
    timeframe: str = 'D'               # 'D' only for now
    date_from: datetime.date = None    # filter signals after this date
    date_to: datetime.date = None      # filter signals before this date
    symbol_limit: int = None           # limit number of symbols to process

@dataclass
class TradeResult:
    symbol: str
    sector: str
    signal_date: datetime.date
    entry_date: datetime.date
    exit_date: datetime.date
    exit_reason: str          # 'holding_period' | 'stop_loss' | 'target'
    signal_score: float
    entry_price: float
    exit_price: float
    return_pct: float
    rsi_at_signal: float
    adx_at_signal: float
    ema_signal: str
