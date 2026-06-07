# app/pipeline/trade_setup.py
from app.core.trading_config import UnifiedTradingConfig
from app.db.models import TechnicalSignal

# Default fallbacks if no config is passed
DEFAULT_ATR_STOP_MULTIPLIER = 2.0
DEFAULT_TARGET_R_LEVELS = (1.5, 2.5)


def compute_trade_setup(
    signal: TechnicalSignal,
    capital: float = 1_000_000.0,
    risk_pct: float = 3.0,
    config: UnifiedTradingConfig = None,
) -> dict | None:
    if not signal:
        return None

    price = signal.close_price
    atr = signal.atr

    if not price or not atr or atr <= 0:
        return None

    # Use config values or fallbacks
    atr_multiplier = config.atr_multiplier if config else DEFAULT_ATR_STOP_MULTIPLIER
    target_r_levels = config.target_r_levels if config else DEFAULT_TARGET_R_LEVELS

    ema_signal = signal.ema_signal or "neutral"
    ema20 = signal.ema20_level
    resistance = signal.resistance_level
    pct_from_res = signal.pct_from_resistance

    if ema_signal in ("bullish_cross",):
        setup_type = "ema_crossover"
        entry_low = price * 0.995
        entry_high = price * 1.005
    elif ema_signal in ("bullish_pullback",) and ema20:
        setup_type = "pullback_to_ema20"
        entry_low = ema20 * 0.99
        entry_high = ema20 * 1.01
    elif resistance and pct_from_res is not None and -3.0 <= pct_from_res <= 0.0:
        setup_type = "resistance_breakout"
        entry_low = resistance * 1.002
        entry_high = resistance * 1.010
    else:
        setup_type = "trend_continuation"
        entry_low = price * 0.990
        entry_high = price * 1.010

    entry_mid = (entry_low + entry_high) / 2
    stop = entry_mid - (atr_multiplier * atr)
    
    # Enforce hard cap based on config.stop_loss_pct
    if config:
        hard_stop = entry_mid * (1 - config.stop_loss_pct / 100)
        stop = max(stop, hard_stop)
    
    risk = entry_mid - stop

    if risk <= 0:
        return None

    setup = {
        "setup_type": setup_type,
        "entry_zone": {
            "low": round(entry_low, 2),
            "high": round(entry_high, 2),
        },
        "stop_loss": round(stop, 2),
        "stop_basis": f"{atr_multiplier}× ATR below entry",
        "targets": [
            {
                "level": round(entry_mid + r * risk, 2),
                "rr": r,
                "label": "partial" if r == target_r_levels[0] else "primary",
            }
            for r in target_r_levels
        ],
        "atr": round(atr, 2),
        "risk_per_share": round(risk, 2),
    }

    # Position sizing — computed from caller-supplied capital and risk %
    if risk > 0 and capital > 0:
        risk_amount = capital * (risk_pct / 100.0)
        shares = int(risk_amount / risk)  # floor — never size up
        position_val = round(shares * entry_mid, 2)
        setup["position_sizing"] = {
            "capital": capital,
            "risk_pct": risk_pct,
            "risk_amount": round(risk_amount, 2),
            "shares": shares,
            "position_value": position_val,
            "position_pct": round(position_val / capital * 100, 1),
            "formula": f"shares = floor({capital:,.0f} × {risk_pct}% / {risk:.2f})",
        }

    return setup
