"""
v3 / T6 acceptance test — the HARDENED §6.4 concentration gate.

All offline: pure predicate logic, no network / DB / engine runs (Rule 5).

WHY this test exists:
  v2's coded §6.4 check tested ONLY subperiod-positivity (>= 2/3 periods with
  positive Calmar) and therefore PASSED a candidate whose entire edge lived in a
  single regime — the prereg-documented failure: post-COVID bull Calmar +7.68 vs a
  near-flat pre-COVID chop. T6 hardens §6.4 by adding `passes_concentration_hard`
  as a second, hard gate: no single positive subperiod may exceed 5x the mean of
  the other positive periods. These tests pin that gate's intent — they fail if the
  threshold, the strictness of the comparison, or the "ignore negatives / need >= 2
  positives" handling is ever changed without a new pre-registration.
"""

from __future__ import annotations

from app.backtest_v2.v3_config import passes_concentration_hard


def test_balanced_positives_pass():
    """Comparable positive Calmars across regimes → not single-regime → PASS."""
    assert passes_concentration_hard([0.30, 0.28, 0.34]) is True


def test_single_regime_dominance_fails():
    """The v2 gap: one regime's Calmar dwarfs the others (post-COVID bull trap).
    7.68 vs a mean of ~0.10 is ~75x → must FAIL, where the v2 check wrongly passed."""
    assert passes_concentration_hard([0.05, 7.68, 0.15]) is False


def test_just_over_5x_fails():
    """Strictly greater than 5x the mean of the others trips the gate."""
    # others mean = 1.0; 5.01 > 5*1.0 → FAIL
    assert passes_concentration_hard([1.0, 1.0, 5.01]) is False


def test_exactly_5x_passes():
    """The comparison is strict (>), so the 5x boundary itself is allowed."""
    # others mean = 1.0; 5.0 is NOT > 5*1.0 → PASS
    assert passes_concentration_hard([1.0, 1.0, 5.0]) is True


def test_negatives_are_ignored_in_concentration():
    """Only positive periods count toward concentration; a single positive among
    negatives leaves < 2 positives → untestable → conservative PASS (the
    positivity gate, not this one, is responsible for catching that case)."""
    assert passes_concentration_hard([2.0, -0.5, -0.3]) is True


def test_fewer_than_two_positives_passes():
    """With < 2 positive periods there is nothing to compare → PASS (don't
    manufacture a concentration failure out of insufficient data)."""
    assert passes_concentration_hard([0.4]) is True
    assert passes_concentration_hard([-0.1, -0.2, -0.3]) is True
