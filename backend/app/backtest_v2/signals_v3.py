"""
signals_v3.py — v3 multi-factor signal store wired through the engine seam (T2).

The v2 engine drives selection entirely off whatever object is passed as
`signal_store`, querying two methods (engine.py §5.v):

  - entry_gate(day, isin) -> bool                  (binary eligibility)
  - eligible_ranked(day, isins) -> [(isin, score)] (ordered membership)

So making the multi-factor composite runnable is a SIGNAL-layer change only —
no engine edit (01 §"What this reuses"). `V3SignalStore` implements that same
interface but orders eligible names by the T1 rank-blended composite
(factors.composite_rank) instead of v2's vol-adjusted `mom/vol` ranker.

Separation of concerns (mirrors signals.py):
  - entry_gate : binary. close > EMA_200, adv_20 floor, AND momentum_12_1 > 0
                 *only while momentum is an active factor* (prereg Erratum T1→T2 —
                 the absolute-momentum filter is meaningful only when momentum is
                 in the composite; a pure low-vol composite must not inherit it).
  - ranker     : continuous composite rank in [0, 1], higher = better.

Indicator inputs for the gate are reused verbatim from v2's precompute_signals
(Rule 3) so the gate is byte-identical to v2's for the momentum-only floor — the
load-bearing property behind the T2 parity check.
"""

from __future__ import annotations

import math
import warnings
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2 import factors
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.stable_universe import (
    StableUniverseMask,
    build_stable_universe_mask,
)
from app.backtest_v2.v3_config import V3Config


def _gate_config(cfg: V3Config) -> MomentumConfig:
    """
    Project the V3Config fields the v2 indicator precompute needs onto a
    MomentumConfig, so precompute_signals (EMA_200, momentum_12_1, adv_20,
    annualized_vol) is reused unchanged (Rule 3).

    Only gate/indicator-relevant fields matter here; cadence/sizing fields are
    carried for completeness but are not consulted by precompute_signals.
    """
    return MomentumConfig(
        target_positions=cfg.target_positions,
        sell_rank_buffer=cfg.sell_rank_buffer,
        liquidity_floor_cr=cfg.liquidity_floor_cr,
        momentum_lookback_days=cfg.momentum_lookback_days,
        momentum_skip_days=cfg.momentum_skip_days,
        vol_lookback_days=cfg.vol_lookback_days,
        trend_ma=cfg.trend_ma,
        max_position_pct=cfg.max_position_pct,
        starting_capital=cfg.starting_capital,
        use_regime_overlay=cfg.use_regime_overlay,
        catastrophic_stop_pct=cfg.catastrophic_stop_pct,
        rebalance=cfg.rebalance_cadence,
        date_from=cfg.date_from,
        date_to=cfg.date_to,
    )


class V3SignalStore:
    """
    Precomputed multi-factor signal cache for one v3 backtest run.

    Built once by precompute_v3_signals(); queried O(1) per (day, isin) by the
    engine loop. Holds two things:
      - `_ind`: {isin → DataFrame} v2 indicator cache (gate inputs).
      - `_composite`: wide (date × isin) composite rank frame (ordering).
    """

    def __init__(
        self,
        ind: dict[str, pd.DataFrame],
        composite: pd.DataFrame,
        cfg: V3Config,
        universe_mask: StableUniverseMask | None = None,
    ) -> None:
        self._ind = ind
        self._composite = composite
        self._cfg = cfg
        self._liq_floor_rupees: float = cfg.liquidity_floor_cr * 1e7
        # Absolute-momentum filter applies only when momentum is in the blend.
        self._momentum_active: bool = "mom_12_1" in cfg.active_factors
        # Stable-universe mask (08 §3). None == 'floor' mode → byte-identical to
        # every pre-08 run (no membership constraint AND-ed into the gate).
        self._universe_mask: StableUniverseMask | None = universe_mask

    # ------------------------------------------------------------------
    # Public query interface (matches SignalStore — the engine seam)
    # ------------------------------------------------------------------

    def entry_gate(self, day: pd.Timestamp | date, isin: str) -> bool:
        """
        True iff `isin` is eligible to be held on `day`.

        Conditions (prereg Erratum T1→T2):
          0. isin in the stable universe on `day`  (ONLY in 'stable' mode — 08 §3)
          1. close > EMA_200            (long-term uptrend)
          2. adv_20 >= liquidity_floor  (decision-date, no lookahead)
          3. momentum_12_1 > 0          (ONLY while momentum is an active factor)

        Condition 0 is AND-ed in only when a stable-universe mask is present; in
        'floor' mode (mask is None) the gate is byte-identical to every pre-08 run.

        Returns False for missing data or NaN in any consulted field.
        """
        if self._universe_mask is not None and not self._universe_mask.is_member(
            day, isin
        ):
            return False
        row = self._ind_row(day, isin)
        if row is None:
            return False
        close = row["close"]
        ema200 = row["EMA_200"]
        adv = row["adv_20"]
        consulted = [close, ema200, adv]
        if self._momentum_active:
            consulted.append(row["momentum_12_1"])
        if any(math.isnan(v) for v in consulted):
            return False
        ok = (close > ema200) and (adv >= self._liq_floor_rupees)
        if self._momentum_active:
            ok = ok and (row["momentum_12_1"] > 0.0)
        return bool(ok)

    def ranker(self, day: pd.Timestamp | date, isin: str) -> float:
        """
        Composite rank in [0, 1] for (day, isin); higher → better rank.

        Returns NaN if the name has no composite value on `day` (e.g. any active
        factor is in warmup), so eligible_ranked can drop it deterministically.
        """
        ts = pd.Timestamp(day)
        try:
            val = self._composite.at[ts, isin]
        except KeyError:
            return float("nan")
        if val is None or pd.isna(val):
            return float("nan")
        return float(val)

    def eligible_ranked(
        self,
        day: pd.Timestamp | date,
        isins: list[str],
    ) -> list[tuple[str, float]]:
        """
        Filter `isins` through entry_gate, then sort by composite rank descending.

        Names that pass the gate but have no composite value (NaN — a factor in
        warmup) are dropped, so the engine never selects an unranked name.
        """
        scored = [
            (isin, self.ranker(day, isin))
            for isin in isins
            if self.entry_gate(day, isin)
        ]
        scored = [(isin, s) for isin, s in scored if not math.isnan(s)]
        return sorted(scored, key=lambda x: x[1], reverse=True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ind_row(self, day: pd.Timestamp | date, isin: str) -> pd.Series | None:
        df = self._ind.get(isin)
        if df is None:
            return None
        ts = pd.Timestamp(day)
        if ts not in df.index:
            return None
        return df.loc[ts]


def build_value_rank(value_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Equal-weight cross-sectional percentile of the value block (E/P + B/P) (09 §3).

    Each raw value frame (date × isin, oriented higher = cheaper = better — the
    fundamental_factors.py sign convention) is percentile-ranked cross-sectionally
    (`rank(axis=1, pct=True)`), then averaged over the factors PRESENT for each
    cell (nanmean), so a name with only one of E/P or B/P still ranks on what it
    has (mirrors composite_rank's Track-B nanmean, 03 §5). Cells where NO value
    factor is present stay NaN — the tilt is neutral there (handled at combine
    time, _apply_value_tilt), never zero-filled (TB4 invariant).

    Returns a wide (date × isin) frame of value ranks in [0, 1]; frames may be
    sparse (rebalance dates only) — alignment to the daily momentum grid happens
    in _apply_value_tilt.
    """
    if not value_frames:
        raise ValueError("build_value_rank requires at least one value frame")
    rank_frames = [f.rank(axis=1, pct=True) for f in value_frames.values()]
    all_idx = rank_frames[0].index
    all_cols = rank_frames[0].columns
    for f in rank_frames[1:]:
        all_idx = all_idx.union(f.index)
        all_cols = all_cols.union(f.columns)
    aligned = [f.reindex(index=all_idx, columns=all_cols) for f in rank_frames]
    stacked = np.stack([f.values for f in aligned], axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        result = np.nanmean(stacked, axis=0)
    result[np.all(np.isnan(stacked), axis=0)] = np.nan
    return pd.DataFrame(result, index=all_idx, columns=all_cols)


def _apply_value_tilt(
    momentum: pd.DataFrame,
    value_rank: pd.DataFrame | None,
    lam: float,
) -> pd.DataFrame:
    """
    final_rank = momentum + lam * value_rank  (the 09 §3 tilt overlay).

    λ = 0 (or no value frame) ⇒ returns the momentum frame UNCHANGED — the
    pure-momentum base byte-for-byte (09 VT0 done-criterion). For λ > 0:
      - value_rank is reindexed onto the momentum daily grid and forward-filled
        (value frames are sparse — rebalance dates only — so each value rank
        carries until the next review);
      - names with no value data are NEUTRAL-FILLED to the median rank 0.5, so the
        tilt only RE-ORDERS momentum-eligible names and never NULLs (drops) a name
        that merely lacks fundamentals. (Construction decision flagged for 09 VT0:
        neutral-fill, not NaN-propagate — a tilt must not shrink the momentum
        universe.) Where momentum itself is NaN (factor warmup) the result stays
        NaN, so warmup exclusion is preserved.
    """
    if lam == 0.0 or value_rank is None:
        return momentum
    aligned = value_rank.reindex(index=momentum.index, columns=momentum.columns)
    aligned = aligned.ffill().fillna(0.5)
    return momentum + lam * aligned


def precompute_v3_signals(
    prices: pd.DataFrame,
    cfg: V3Config,
    value_frames: dict[str, pd.DataFrame] | None = None,
) -> V3SignalStore:
    """
    Precompute the v3 signal store: v2 indicator cache (gate inputs) reused
    verbatim from precompute_signals, plus the T1 composite rank frame for
    ordering. Built once so sweeps (T4/T5) don't recompute (mirrors v2).

    `prices` is the long-format multi-ISIN frame from store.read_prices_adjusted
    (isin, date, open, high, low, close, volume, adv_20).

    `value_frames` (09 §3): {factor_name → raw wide frame} for the value tilt
    (E/P, B/P). Required when cfg.value_tilt_lambda > 0; ignored otherwise. The
    momentum composite (price-only active_factors) is built first, then the value
    tilt is layered on top (_apply_value_tilt) — value never enters active_factors
    (that would route it through the closed Track-B co-equal blend, 07).
    """
    gate_store = precompute_signals(prices, _gate_config(cfg))
    # Reach into the v2 store's indicator cache once, at construction, to reuse
    # its gate inputs (close, EMA_200, momentum_12_1, adv_20) byte-for-byte.
    ind = gate_store._data
    composite = factors.composite_rank(prices, cfg)
    # Value tilt (09 §3): only when λ > 0; λ = 0 leaves composite byte-identical.
    if cfg.value_tilt_lambda > 0.0:
        if not value_frames:
            raise ValueError(
                "cfg.value_tilt_lambda > 0 requires value_frames (E/P, B/P); "
                "none provided."
            )
        value_rank = build_value_rank(value_frames)
        composite = _apply_value_tilt(composite, value_rank, cfg.value_tilt_lambda)
    # Stable-universe mask only in 'stable' mode (08 §3); 'floor' stays mask-free
    # so the C0 control is byte-identical to every pre-08 run.
    universe_mask = None
    if cfg.universe_mode == "stable":
        universe_mask = build_stable_universe_mask(
            prices,
            cfg.universe_size_U,
            cfg.universe_buffer_B,
            cfg.universe_rank_lookback_td,
            cfg.universe_review_cadence,
        )
    return V3SignalStore(ind, composite, cfg, universe_mask=universe_mask)
