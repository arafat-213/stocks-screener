"""
validation.py — Spec 04 T2: walk-forward scaffolding, config ledger,
deflated Sharpe (Bailey & LdP 2016), and PBO via CSCV (Bailey & LdP 2014).

Exports
-------
DISCOVERY, FINAL_OOS   — T0 frozen date constants
WFWindow               — named tuple for one walk-forward fold
walk_forward_windows   — expanding-IS folds within DISCOVERY
ConfigLedger           — monotonic trial counter and ledger
deflated_sharpe        — SR corrected for K-trial selection bias
pbo_cscv               — Probability of Backtest Overfitting via CSCV

No engine calls. Pure offline infrastructure for T3 / T4 / T5.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
from dateutil.relativedelta import relativedelta
from scipy import stats

# ---------------------------------------------------------------------------
# T0 frozen date splits — do NOT move to make a config pass (Rule 12)
# ---------------------------------------------------------------------------

USABLE_START = date(2018, 2, 6)  # first post-warmup decision date
USABLE_END = date(2026, 6, 12)  # last date on disk (T0 probe 2026-06-15)

# All §4 iteration lives inside DISCOVERY. FINAL_OOS is touched exactly once (T5).
DISCOVERY = (date(2018, 2, 6), date(2023, 6, 30))
FINAL_OOS = (date(2023, 7, 1), date(2026, 6, 12))

_EULER_MASCHERONI = 0.5772156649015328  # γ — Euler–Mascheroni constant

# ---------------------------------------------------------------------------
# Walk-forward windows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WFWindow:
    """One expanding-IS walk-forward fold."""

    is_start: date
    is_end: date
    oos_start: date
    oos_end: date


def walk_forward_windows(
    discovery_start: date = DISCOVERY[0],
    discovery_end: date = DISCOVERY[1],
    min_is_months: int = 24,
    oos_months: int = 6,
) -> list[WFWindow]:
    """
    Return expanding-IS walk-forward folds, all contained within
    [discovery_start, discovery_end].

    IS starts at discovery_start and grows with each fold (expanding window).
    OOS is a fixed-length block stepping forward by oos_months each fold.
    No fold ever reaches FINAL_OOS.

    WHY: expanding IS mirrors live trading (you always have all past data),
    and hard-bounding by discovery_end keeps FINAL_OOS untouched.
    """
    windows: list[WFWindow] = []
    oos_start = discovery_start + relativedelta(months=min_is_months)
    while True:
        oos_end = oos_start + relativedelta(months=oos_months) - timedelta(days=1)
        if oos_end > discovery_end:
            break
        windows.append(
            WFWindow(
                is_start=discovery_start,
                is_end=oos_start - timedelta(days=1),
                oos_start=oos_start,
                oos_end=oos_end,
            )
        )
        oos_start += relativedelta(months=oos_months)
    return windows


# ---------------------------------------------------------------------------
# Config ledger
# ---------------------------------------------------------------------------


@dataclass
class TrialRecord:
    trial_id: int
    config: Any
    metadata: dict = field(default_factory=dict)


class ConfigLedger:
    """
    Records every config evaluated during iteration.

    The trial count K feeds into deflated_sharpe: without tracking K,
    a Sharpe that looks significant might just be the expected maximum
    of K random draws — claiming K=1 when K=100 would be fraudulent.

    WHY this must be used every time a config is evaluated: spec 04 §5
    says "track how many configs you tried and discount accordingly."
    Skipping the ledger defeats the entire anti-overfit methodology.
    """

    def __init__(self) -> None:
        self._trials: list[TrialRecord] = []

    def add(self, config: Any, **metadata: Any) -> int:
        """Record a config and return its 1-indexed trial_id."""
        trial_id = len(self._trials) + 1
        self._trials.append(
            TrialRecord(trial_id=trial_id, config=config, metadata=dict(metadata))
        )
        return trial_id

    @property
    def n_trials(self) -> int:
        return len(self._trials)

    @property
    def trials(self) -> list[TrialRecord]:
        return list(self._trials)


# ---------------------------------------------------------------------------
# Deflated Sharpe Ratio — Bailey & López de Prado (2016)
# ---------------------------------------------------------------------------


def deflated_sharpe(
    sr_annualized: float,
    returns: np.ndarray,
    n_trials: int,
) -> float:
    """
    Deflated Sharpe Ratio adjusted for K-trial selection bias and non-normality.

    DSR = SR* − E[max_SR_null(K, T)]

    E[max_SR_null] is the expected maximum annualized Sharpe when K strategies
    with true SR=0 are each estimated on T observations, so it is the amount
    of spurious SR you can expect by selecting the best of K random series.
    DSR > 0 means the observed edge exceeds what selection alone explains.
    DSR ≤ SR* always; DSR decreases monotonically as K grows.

    Non-normality (skewness and excess kurtosis of the return distribution)
    is incorporated into the variance of the sample SR per the Bailey & LdP
    (2016) formula, giving a tighter correction when returns are fat-tailed.

    Reference: Bailey & López de Prado (2016), "The Deflated Sharpe Ratio:
    Correcting for Selection Bias, Backtest Overfitting, and Non-Normality,"
    Journal of Portfolio Management.

    Parameters
    ----------
    sr_annualized : float
        Observed annualized Sharpe ratio of the selected strategy.
    returns : np.ndarray
        Daily return series used for sample size T and non-normality moments.
    n_trials : int
        K — number of configs evaluated before selecting this one (>= 1).
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    if n_trials == 1:
        # No selection bias with a single trial.
        return sr_annualized

    t = len(returns)
    if t < 2:
        return sr_annualized

    mu = float(np.mean(returns))
    sigma = float(np.std(returns, ddof=1))
    if sigma == 0.0:
        return sr_annualized

    sr_daily = sr_annualized / math.sqrt(252.0)

    # Non-normality correction on Var(sample SR).
    skew = float(np.mean((returns - mu) ** 3) / sigma**3)
    kurt_excess = float(np.mean((returns - mu) ** 4) / sigma**4) - 3.0
    var_sr = (1.0 - skew * sr_daily + (kurt_excess / 4.0) * sr_daily**2) / (t - 1)
    std_sr = math.sqrt(max(var_sr, 1e-12))

    # Expected maximum of K iid standard normals, Euler–Mascheroni approximation
    # (Eq. 8 in Bailey & LdP 2016).
    k = float(n_trials)
    e_max_z = (1.0 - _EULER_MASCHERONI) * stats.norm.ppf(
        1.0 - 1.0 / k
    ) + _EULER_MASCHERONI * stats.norm.ppf(1.0 - 1.0 / (k * math.e))

    # Scale to annualized Sharpe units and subtract.
    e_max_sr_annual = e_max_z * std_sr * math.sqrt(252.0)
    return sr_annualized - e_max_sr_annual


# ---------------------------------------------------------------------------
# PBO via CSCV — Bailey & López de Prado (2014)
# ---------------------------------------------------------------------------


def pbo_cscv(
    performance_matrix: np.ndarray,
    higher_is_better: bool = True,
) -> float:
    """
    Probability of Backtest Overfitting via Combinatorially Symmetric CV.

    Partitions the T walk-forward folds into all C(T, T//2) IS/OOS halves.
    For each partition the IS-optimal config is identified, then its normalized
    OOS rank ω ∈ [0,1] is computed (1 = best, 0 = worst OOS performer).
    PBO = fraction of partitions where the IS winner falls below the OOS
    median (ω < 0.5).

    PBO ∈ [0, 1].  Values > 0.5 indicate near-certain overfitting.
    A config that is consistently best in-sample and best out-of-sample
    should produce PBO close to 0.

    Reference: Bailey & López de Prado (2014), "The Probability of Backtest
    Overfitting," Journal of Computational Finance.

    Parameters
    ----------
    performance_matrix : np.ndarray
        Shape (n_configs, n_folds).  performance_matrix[j, k] is the metric
        (e.g., Sharpe, Calmar) of config j on walk-forward fold k.
    higher_is_better : bool
        True (default) → higher metric = better IS rank.
    """
    perf = np.asarray(performance_matrix, dtype=float)
    n_configs, n_folds = perf.shape
    if n_configs < 2:
        raise ValueError("Need at least 2 configs for PBO.")
    if n_folds < 2:
        raise ValueError("Need at least 2 folds for PBO.")

    half = n_folds // 2
    all_idx = list(range(n_folds))

    overfit_count = 0
    total_count = 0

    for is_tuple in itertools.combinations(all_idx, half):
        is_idx = list(is_tuple)
        oos_idx = [i for i in all_idx if i not in is_tuple]
        if not oos_idx:
            continue

        is_scores = perf[:, is_idx].mean(axis=1)  # (n_configs,)
        oos_scores = perf[:, oos_idx].mean(axis=1)

        if higher_is_better:
            best_is = int(np.argmax(is_scores))
        else:
            best_is = int(np.argmin(is_scores))

        # ω = fraction of configs the IS winner beats out-of-sample.
        # ω > 0.5 → IS winner is in the top half OOS → not overfit.
        # ω < 0.5 → IS winner is in the bottom half OOS → overfit.
        if higher_is_better:
            omega = float(np.mean(oos_scores < oos_scores[best_is]))
        else:
            omega = float(np.mean(oos_scores > oos_scores[best_is]))

        if omega < 0.5:
            overfit_count += 1
        total_count += 1

    if total_count == 0:
        return float("nan")

    return overfit_count / total_count
