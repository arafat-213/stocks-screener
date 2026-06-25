"""regime.py — the v4 0–5 regime score → deployable fraction f (v4/02 §3, 00 §4).

`RegimeScore` is a collaborator built once over the run window. For each day D it
returns an integer score 0–5 and the deployable fraction f ∈ {0.0, 0.5, 1.0}:

  | # | Condition (+1)                        | Source                      |
  |---|---------------------------------------|-----------------------------|
  | 1 | Nifty 50 close > 200-DMA              | Nifty 50 price series       |
  | 2 | Nifty 50 50-DMA > 200-DMA             | same                        |
  | 3 | liq_breadth_pct > 60                  | market_internals (liquid)   |
  | 4 | liq_ad_ratio > 1                      | market_internals (liquid)   |
  | 5 | india_vix < 20                        | market_internals.india_vix  |

Buckets (frozen): 0–1 → 0.0 (Bear); 2–3 → 0.5 (Neutral); 4–5 → 1.0 (Bull).

Causality (00 §4 / §9): DMAs use trailing windows (`min_periods = window`); a
missing-VIX day scores condition 5 = **0** (no forward-fill, no rescale — score
caps at 4, biasing toward *less* deployment). The Nifty 50 price series is
**injected** (fixture in tests; one-off cache-miss fetch wired by the caller, not
here) — this module is purely functional and touches no network.

3-factor ablation: pass ``n_factors=3`` for the reported-only V4.2 ablation
(conditions 1–3, rescaled 0→0.0 / 1–2→0.5 / 3→1.0). It is NOT a separate
selection trial (00 §4) — never run it as a candidate.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.swing_v4.config import SwingConfig
from app.swing_v4.indicators import sma


class RegimeScore:
    """Precompute the daily 0–5 (or 0–3 ablation) regime score and fraction f.

    Args:
        nifty50_price: DatetimeIndex → Nifty 50 CLOSE float (price, not TRI).
        market_internals: the ``read_market_internals`` frame (needs columns
            ``date``, ``liq_breadth_pct``, ``liq_ad_ratio``, ``india_vix``).
        cfg: SwingConfig — thresholds and DMA windows (frozen 00 §4 defaults).
        n_factors: 5 (frozen) or 3 (reported ablation only).
    """

    def __init__(
        self,
        nifty50_price: pd.Series,
        market_internals: pd.DataFrame,
        cfg: SwingConfig | None = None,
        n_factors: int | None = None,
        neutral_fraction: float = 0.5,
    ) -> None:
        self._cfg = cfg or SwingConfig()
        self._n_factors = (
            n_factors if n_factors is not None else self._cfg.regime_factors
        )
        if self._n_factors not in (3, 5):
            raise ValueError(f"regime n_factors must be 3 or 5, got {self._n_factors}")
        # `04` §5 deployment diagnostic ONLY: the Neutral bucket (score 2–3) deployable
        # fraction. Frozen 0.5 for the candidate (default ⇒ byte-identical); the `D_more`
        # diagnostic lifts it to 0.75 to bound the "deploy more capital" question. NON-GATING,
        # adds 0 to K — never used by the locked OOS candidate (04 §5). Bear/Bull stay 0/1.
        self._neutral_fraction = neutral_fraction
        self._score, self._frac = _precompute(
            nifty50_price,
            market_internals,
            self._cfg,
            self._n_factors,
            neutral_fraction,
        )

    def score(self, day: date | pd.Timestamp) -> int:
        """Integer regime score for D. Unknown days → 0 (conservative: no deploy)."""
        ts = pd.Timestamp(day)
        if ts not in self._score.index:
            return 0
        return int(self._score[ts])

    def deployable_fraction(self, day: date | pd.Timestamp) -> float:
        """Deployable gross fraction f for D. Unknown days → 0.0 (conservative)."""
        ts = pd.Timestamp(day)
        if ts not in self._frac.index:
            return 0.0
        return float(self._frac[ts])


def _precompute(
    nifty50_price: pd.Series,
    market_internals: pd.DataFrame,
    cfg: SwingConfig,
    n_factors: int,
    neutral_fraction: float = 0.5,
) -> tuple[pd.Series, pd.Series]:
    """Vectorized precompute on the market_internals trading calendar.

    Nifty 50 DMAs are computed on the index's own calendar, then **as-of** ffilled
    onto the market_internals dates (a daily date D takes the last Nifty value ≤ D
    — causal across index/equity holiday mismatches). All comparisons treat NaN
    (DMA warmup, missing VIX) as False ⇒ the condition simply does not score.
    """
    mi = market_internals.copy()
    mi = mi.sort_values("date").set_index(pd.to_datetime(mi["date"]))
    idx = mi.index

    price = nifty50_price.sort_index()
    dma_long = sma(price, cfg.regime_dma_long)
    dma_short = sma(price, cfg.regime_dma_short)

    a_price = price.reindex(idx, method="ffill")
    a_dma_long = dma_long.reindex(idx, method="ffill")
    a_dma_short = dma_short.reindex(idx, method="ffill")

    c1 = (a_price > a_dma_long).fillna(False)
    c2 = (a_dma_short > a_dma_long).fillna(False)
    c3 = (mi["liq_breadth_pct"] > cfg.regime_breadth_min).fillna(False)

    if n_factors == 3:
        # Reported ablation only (00 §4): 0 → 0.0, 1–2 → neutral, 3 → 1.0.
        score = (c1.astype(int) + c2.astype(int) + c3.astype(int)).astype(int)
        frac = score.map(
            lambda s: 0.0 if s == 0 else (1.0 if s == 3 else neutral_fraction)
        )
        return score, frac

    c4 = (mi["liq_ad_ratio"] > cfg.regime_ad_min).fillna(False)
    # Missing VIX → NaN < 20 → False ⇒ condition 5 scores 0 (00 §4; no ffill).
    c5 = (mi["india_vix"] < cfg.regime_vix_max).fillna(False)

    score = (
        c1.astype(int)
        + c2.astype(int)
        + c3.astype(int)
        + c4.astype(int)
        + c5.astype(int)
    ).astype(int)
    # Buckets (frozen): 0–1 → 0.0, 2–3 → neutral (0.5 default; 04 §5 D_more lifts to 0.75),
    # 4–5 → 1.0.
    frac = score.map(lambda s: 0.0 if s <= 1 else (neutral_fraction if s <= 3 else 1.0))
    return score, frac
