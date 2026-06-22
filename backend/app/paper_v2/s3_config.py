"""Frozen S3 candidate construction for the v3/11 forward paper probation (§1).

Single source of truth for the byte-for-byte S3 config locked in `10` R10.3. The
constants and the build sequence (stable mask → gate cache → composite → V3SignalStore)
MIRROR `app.backtest_v2.r10_oos` exactly — the FINAL_OOS run that consumed the candidate.
No knob here may move during the probation (`11` §1 / `00` §1); changing any of these is
a new prereg.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.backtest_v2 import factors
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.stable_universe import build_stable_universe_mask
from app.backtest_v2.v3_config import TRACK_A_BASELINE, V3Config

# Frozen S3 construction (`10` §3 / r10_oos) — byte-for-byte the R10.2 / SU2 candidate.
S3_U, S3_B, S3_M = 350, 1.25, 130
S3_SMOOTHING = 0
S3_CADENCE = "monthly"
S3_CATASTROPHIC_STOP_PCT = 25.0
S3_LIQUIDITY_FLOOR_CR = 5.0


def make_s3_v3config(
    date_from: date | None = None, date_to: date | None = None
) -> V3Config:
    """The frozen S3 V3Config (5-factor Track-A blend on the stable universe)."""
    return V3Config(
        active_factors=list(TRACK_A_BASELINE.active_factors),
        rebalance_cadence=S3_CADENCE,
        sell_rank_buffer=S3_M,
        rank_smoothing_months=S3_SMOOTHING,
        target_positions=TRACK_A_BASELINE.target_positions,
        use_regime_overlay=True,
        catastrophic_stop_pct=S3_CATASTROPHIC_STOP_PCT,
        liquidity_floor_cr=S3_LIQUIDITY_FLOOR_CR,
        universe_mode="stable",
        universe_size_U=S3_U,
        universe_buffer_B=S3_B,
        date_from=date_from,
        date_to=date_to,
    )


def make_s3_engine_cfg(
    v3cfg: V3Config, date_from: date | None = None, date_to: date | None = None
) -> MomentumConfig:
    """The MomentumConfig the engine consumes, derived from the S3 V3Config (r10_oos)."""
    return MomentumConfig(
        target_positions=v3cfg.target_positions,
        sell_rank_buffer=v3cfg.sell_rank_buffer,
        liquidity_floor_cr=v3cfg.liquidity_floor_cr,
        momentum_lookback_days=v3cfg.momentum_lookback_days,
        momentum_skip_days=v3cfg.momentum_skip_days,
        vol_lookback_days=v3cfg.vol_lookback_days,
        trend_ma=v3cfg.trend_ma,
        max_position_pct=v3cfg.max_position_pct,
        starting_capital=v3cfg.starting_capital,
        use_regime_overlay=v3cfg.use_regime_overlay,
        catastrophic_stop_pct=v3cfg.catastrophic_stop_pct,
        rebalance=v3cfg.rebalance_cadence,
        date_from=date_from,
        date_to=date_to,
    )


def build_s3_signal_store(prices: pd.DataFrame, v3cfg: V3Config) -> V3SignalStore:
    """Build the S3 V3SignalStore over `prices` (stable mask + gate cache + composite).

    Mirrors r10_oos's construction so the live shell ranks/gates identically to the
    consumed FINAL_OOS run. The store is point-in-time/causal (no lookahead) and is the
    `signal_store` injected into `engine.build_context`.
    """
    eng = make_s3_engine_cfg(v3cfg, v3cfg.date_from, v3cfg.date_to)
    mask = build_stable_universe_mask(
        prices,
        v3cfg.universe_size_U,
        v3cfg.universe_buffer_B,
        v3cfg.universe_rank_lookback_td,
        v3cfg.universe_review_cadence,
    )
    gate_store = precompute_signals(prices, eng)
    composite = factors.composite_rank(prices, v3cfg)
    return V3SignalStore(gate_store._data, composite, v3cfg, universe_mask=mask)
