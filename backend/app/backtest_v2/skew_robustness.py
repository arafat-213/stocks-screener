"""
skew_robustness.py — 09 §2c/§6.2: skew-aware universe-perturbation test.

WHY this exists (09 §2c): the classic §6.2 "drop the top-10 *realized*-P&L names"
(robustness.check_universe_perturbation) is an ex-post, look-ahead-flavoured
perturbation — you only know those were the winners because you saw the whole
sample, and that is structurally hostile to a positively-skewed momentum strategy.
This module asks the distribution-aware question instead, on first principles of
skewed-strategy statistics:

  (a) random-subset retention — is the edge BROAD-BASED? Over many draws that each
      drop a RANDOM subset of the held names (NOT the realized winners — no
      lookahead), does Calmar retention hold up in the MEDIAN *and* in the lower
      tail (5th percentile)?
  (b) contributor rotation — is the edge a PROCESS, not a single story? Do the
      top P&L contributors ROTATE across calendar years (a large union of distinct
      names), rather than the same few names carrying every year?

Thresholds are LOCKED by 09 §6 before any run (the median retention bar is NOT
relaxed vs the classic §6.2 — only the operationalisation is upgraded; the classic
drop-top-10 is still reported alongside as the §2c contamination guard).

Design (CLAUDE.md §5 — inject seams, no engine import here):
  - `random_subset_retention` takes a `run_perturbed(frozenset[isin]) -> calmar`
    callable. The caller wires it to the real engine (VT2); unit tests pass a fake.
    This keeps the routine pure, deterministic (seeded RNG), and engine-free.
  - `contributor_rotation` takes the per-calendar-year top-contributor name lists
    (derived from metrics.per_name_stats by the caller).

No-lookahead is STRUCTURAL: which names are dropped is chosen by a seeded RNG over
the held-name list only — realized P&L is never consulted to pick the drops.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------
# Locked thresholds (09 §6 item 2) — named so tests verify logic, not magic nums
# ---------------------------------------------------------------------------
N_DRAWS: int = 200  # random subsets drawn
DROP_K: int = 10  # names dropped per draw
MEDIAN_RETENTION_THRESHOLD: float = (
    0.70  # median perturbed/base Calmar bar (NOT relaxed)
)
P5_RETENTION_THRESHOLD: float = 0.50  # 5th-percentile retention bar (tail guard)
MIN_DISTINCT_CONTRIBUTORS: int = 25  # union of per-year top-10 across DISCOVERY
DEFAULT_SEED: int = 20260620  # determinism anchor (09 lock date)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class RandomSubsetResult:
    """Outcome of the random-subset retention test (09 §6.2a)."""

    passed: bool
    median_retention: float
    p5_retention: float
    base_calmar: float
    n_draws: int
    drop_k: int
    seed: int
    retentions: list[float] = field(default_factory=list)  # full distribution
    summary: str = ""


@dataclass
class ContributorRotationResult:
    """Outcome of the contributor-rotation test (09 §6.2b)."""

    passed: bool
    n_distinct: int
    min_required: int
    distinct_contributors: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class SkewAwareResult:
    """Combined skew-aware §6.2 verdict (both sub-tests must pass)."""

    passed: bool
    random_subset: RandomSubsetResult
    rotation: ContributorRotationResult
    summary: str = ""


# ---------------------------------------------------------------------------
# (a) random-subset retention
# ---------------------------------------------------------------------------


def random_subset_retention(
    held_isins: Sequence[str],
    base_calmar: float,
    run_perturbed: Callable[[frozenset[str]], float],
    *,
    n_draws: int = N_DRAWS,
    drop_k: int = DROP_K,
    seed: int = DEFAULT_SEED,
    median_threshold: float = MEDIAN_RETENTION_THRESHOLD,
    p5_threshold: float = P5_RETENTION_THRESHOLD,
) -> RandomSubsetResult:
    """
    Drop a RANDOM `drop_k` of the held names `n_draws` times; require the MEDIAN
    Calmar retention >= `median_threshold` AND the 5th-percentile retention >=
    `p5_threshold` (09 §6.2a). Retention = perturbed_calmar / base_calmar.

    No-lookahead: drops are chosen by a seeded RNG over `held_isins` only — never
    by realized P&L. Determinism: identical (seed, held_isins, n_draws, drop_k)
    ⇒ identical draws ⇒ identical retentions (the RNG is the sole source of
    randomness; `run_perturbed` is assumed pure in its argument).

    Fails loud (ValueError) on a non-positive / NaN base Calmar (retention is
    undefined) rather than silently returning a pass.
    """
    if not (base_calmar > 0.0) or base_calmar != base_calmar:  # <=0 or NaN
        raise ValueError(
            f"random_subset_retention needs a positive base Calmar; got {base_calmar!r}"
        )
    names = list(held_isins)
    if len(names) < drop_k:
        raise ValueError(
            f"held set has {len(names)} names < drop_k={drop_k}; cannot draw subsets"
        )

    rng = np.random.default_rng(seed)
    retentions: list[float] = []
    for _ in range(n_draws):
        drop_idx = rng.choice(len(names), size=drop_k, replace=False)
        drop_set = frozenset(names[i] for i in drop_idx)
        perturbed_calmar = run_perturbed(drop_set)
        retentions.append(perturbed_calmar / base_calmar)

    arr = np.asarray(retentions, dtype=float)
    median_ret = float(np.median(arr))
    p5_ret = float(np.percentile(arr, 5))
    passed = median_ret >= median_threshold and p5_ret >= p5_threshold
    summary = (
        f"{'PASS' if passed else 'FAIL'} — median retention {median_ret:.0%} "
        f"(bar {median_threshold:.0%}), p5 {p5_ret:.0%} (bar {p5_threshold:.0%}) "
        f"over {n_draws} random-{drop_k} drops"
    )
    return RandomSubsetResult(
        passed=passed,
        median_retention=median_ret,
        p5_retention=p5_ret,
        base_calmar=base_calmar,
        n_draws=n_draws,
        drop_k=drop_k,
        seed=seed,
        retentions=retentions,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# (b) contributor rotation
# ---------------------------------------------------------------------------


def contributor_rotation(
    per_year_top_contributors: Mapping[int, Iterable[str]],
    *,
    min_distinct: int = MIN_DISTINCT_CONTRIBUTORS,
) -> ContributorRotationResult:
    """
    Union of the per-calendar-year top-10 P&L contributors must span at least
    `min_distinct` distinct names across DISCOVERY (09 §6.2b) — winners ROTATE,
    so the edge is a process, not a handful of names repeating every year.

    `per_year_top_contributors`: {year → iterable of contributor names (symbols
    or ISINs) for that year}. Identity is by string; the caller decides ISIN vs
    symbol (consistently).
    """
    distinct: set[str] = set()
    for names in per_year_top_contributors.values():
        distinct.update(names)
    n_distinct = len(distinct)
    passed = n_distinct >= min_distinct
    summary = (
        f"{'PASS' if passed else 'FAIL'} — {n_distinct} distinct top contributors "
        f"across {len(per_year_top_contributors)} years (bar >= {min_distinct})"
    )
    return ContributorRotationResult(
        passed=passed,
        n_distinct=n_distinct,
        min_required=min_distinct,
        distinct_contributors=sorted(distinct),
        summary=summary,
    )


def skew_aware_universe_perturbation(
    held_isins: Sequence[str],
    base_calmar: float,
    run_perturbed: Callable[[frozenset[str]], float],
    per_year_top_contributors: Mapping[int, Iterable[str]],
    *,
    n_draws: int = N_DRAWS,
    drop_k: int = DROP_K,
    seed: int = DEFAULT_SEED,
    median_threshold: float = MEDIAN_RETENTION_THRESHOLD,
    p5_threshold: float = P5_RETENTION_THRESHOLD,
    min_distinct: int = MIN_DISTINCT_CONTRIBUTORS,
) -> SkewAwareResult:
    """Run both skew-aware sub-tests; PASS iff BOTH pass (09 §6 item 2)."""
    rs = random_subset_retention(
        held_isins,
        base_calmar,
        run_perturbed,
        n_draws=n_draws,
        drop_k=drop_k,
        seed=seed,
        median_threshold=median_threshold,
        p5_threshold=p5_threshold,
    )
    rot = contributor_rotation(per_year_top_contributors, min_distinct=min_distinct)
    passed = rs.passed and rot.passed
    summary = (
        f"{'PASS' if passed else 'FAIL'} — skew-aware §6.2 "
        f"[random-subset: {'PASS' if rs.passed else 'FAIL'}, "
        f"rotation: {'PASS' if rot.passed else 'FAIL'}]"
    )
    return SkewAwareResult(
        passed=passed, random_subset=rs, rotation=rot, summary=summary
    )
