"""§5e — corporate-action portfolio-state reconciliation (v3/11).

The gotcha
----------
Back-adjustment pins the **latest** date to ``adj_factor = 1.0`` and rescales all
earlier dates (adjust.py convention). In a single-anchor backtest the whole price
series is adjusted **once**, so a split is invisible: ``cost_basis``, ``shares``
and ``close`` all live in one frozen adjusted space and the catastrophic stop
(``engine.py`` §5.iii: ``stop_level = cost_basis × 0.75``) stays comparable to
``close``.

**Live, the anchor moves every day.** ``incremental_append`` re-adjusts the stored
series to byte-match a full rebuild, so a new CA on ex-date D **retroactively
rescales the entire prior adjusted series** — but the *persisted* live position's
``cost_basis``/``shares`` were recorded against the **old** anchor and are NOT
rescaled by the data pipeline. Unreconciled:

  * a clean 2:1 split prints ``close ≈ 500`` against a ``cost_basis = 1000``
    (``stop_level = 750``) → ``500 ≤ 750`` ⇒ the daily catastrophic stop **falsely
    fires** (a healthy position read as a −50% crash); and
  * MTM (``shares × close_tr``) halves silently.

The fix (deterministic — Rule 5)
--------------------------------
On each daily append, for every **held** ISIN whose stored ``adj_factor`` changed
versus the prior series, compute the factor ratio ``r = new_factor / old_factor``
and rescale the persisted position **before** the §3e step-3 stop check::

    cost_basis *= r        # price space   (×0.5 for a 2:1 split)
    shares     /= r        # share space   (×2)  → shares × cost_basis invariant

This puts the live state back in the **same anchor** as the freshly-adjusted price
series — reproducing what the single-fixed-anchor backtest gets for free. Because a
from-scratch shadow backtest re-derives ``cost_basis`` in the current anchor as
``raw_entry_price × new_factor = old_cost_basis × r``, the reconciled live
``cost_basis`` must byte-match the shadow's — so this reconciliation is a
*precondition* of monthly parity (§2), not a substitute for it.
"""

from __future__ import annotations

from dataclasses import dataclass

# Treat factor ratios within this of 1.0 as "no CA today" (float noise guard).
_FACTOR_EPS = 1e-12


class UnreconcilableCorporateActionError(RuntimeError):
    """A held-name CA whose factor ratio is missing/ambiguous (≤ 0) → halt (§8)."""


@dataclass(frozen=True)
class ReconciledState:
    """Result of rescaling one held position for a moving back-adjustment anchor."""

    cost_basis: float
    shares: float
    new_adj_factor: float
    factor_ratio: float
    rescaled: bool  # False when no CA hit this ISIN today (factor unchanged)


def reconcile_position(
    cost_basis: float,
    shares: float,
    old_adj_factor: float,
    new_adj_factor: float,
) -> ReconciledState:
    """Rescale one held position into the new back-adjustment anchor (§5e).

    ``old_adj_factor`` is the factor last persisted for this ISIN; ``new_adj_factor``
    is the factor in the freshly-appended series for the same (latest) row. When they
    match (no CA today), the position is returned unchanged. Otherwise both
    ``cost_basis`` and ``shares`` are rescaled by ``r = new / old`` so that:

      * ``shares × cost_basis`` is invariant (position value preserved), and
      * the reconciled ``cost_basis`` lands in the same anchor as ``close`` — making
        the daily ``cost_basis × 0.75`` stop comparable again (no false trip).

    Raises ``UnreconcilableCorporateActionError`` if either factor is non-positive
    (a missing/ambiguous ratio the run cannot resolve — §8 halt).
    """
    if old_adj_factor <= 0 or new_adj_factor <= 0:
        raise UnreconcilableCorporateActionError(
            f"non-positive adj_factor (old={old_adj_factor}, new={new_adj_factor}); "
            "cannot reconcile held position — halt (11 §8)"
        )

    r = new_adj_factor / old_adj_factor
    if abs(r - 1.0) <= _FACTOR_EPS:
        return ReconciledState(
            cost_basis=cost_basis,
            shares=shares,
            new_adj_factor=new_adj_factor,
            factor_ratio=1.0,
            rescaled=False,
        )

    return ReconciledState(
        cost_basis=cost_basis * r,
        shares=shares / r,
        new_adj_factor=new_adj_factor,
        factor_ratio=r,
        rescaled=True,
    )


def would_stop_fire(
    close: float, cost_basis: float, catastrophic_stop_pct: float
) -> bool:
    """Mirror of ``engine.py`` §5.iii: True iff ``close ≤ cost_basis × (1 − pct/100)``.

    Used by the §5e regression test to prove the rescale removes the false split-stop.
    """
    stop_level = cost_basis * (1.0 - catastrophic_stop_pct / 100.0)
    return close <= stop_level
