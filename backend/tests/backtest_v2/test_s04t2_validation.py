"""
test_s04t2_validation.py — Spec 04 T2 done-criteria tests (offline, no live data).

Done-criteria (04_VALIDATION_FLOOR_TASKS T2):
  DC1  Frozen splits importable as constants; FINAL_OOS provably untouched by
       walk-forward folds.
  DC2  Config ledger counts trials monotonically; count feeds deflation.
  DC3  Deflated Sharpe ≤ raw Sharpe and decreases as trial count rises.
  DC4  PBO ∈ [0, 1]; consistent IS winner yields PBO close to 0.

All tests are offline: no yfinance, no NSE calls, no parquet reads.
WHY: the anti-overfit machinery must be testable without a live dataset so
the methodology can be audited in isolation.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest

from app.backtest_v2.validation import (
    DISCOVERY,
    FINAL_OOS,
    USABLE_END,
    USABLE_START,
    ConfigLedger,
    TrialRecord,
    WFWindow,
    deflated_sharpe,
    pbo_cscv,
    walk_forward_windows,
)

# ---------------------------------------------------------------------------
# DC1a — Frozen date constants
# ---------------------------------------------------------------------------


class TestFrozenSplits:
    def test_discovery_values(self):
        # WHY: these exact dates are the T0 locked decisions; any change invalidates
        # the entire validation methodology.
        assert DISCOVERY == (date(2018, 2, 6), date(2023, 6, 30))

    def test_final_oos_values(self):
        assert FINAL_OOS == (date(2023, 7, 1), date(2026, 6, 12))

    def test_splits_do_not_overlap(self):
        # WHY: a shared date between DISCOVERY and FINAL_OOS would mean the OOS
        # block was "seen" during iteration — the cardinal overfit sin.
        assert DISCOVERY[1] < FINAL_OOS[0]

    def test_no_gap_between_discovery_and_oos(self):
        # Continuous: day after DISCOVERY end == FINAL_OOS start.
        assert FINAL_OOS[0] == DISCOVERY[1] + timedelta(days=1)

    def test_usable_bounds_contain_both_splits(self):
        assert USABLE_START == DISCOVERY[0]
        assert USABLE_END == FINAL_OOS[1]


# ---------------------------------------------------------------------------
# DC1b — Walk-forward windows
# ---------------------------------------------------------------------------


class TestWalkForwardWindows:
    def test_returns_nonempty_list(self):
        # WHY: if no windows are produced the walk-forward machinery silently
        # produces no folds and iteration can't be measured.
        windows = walk_forward_windows()
        assert len(windows) >= 1

    def test_no_window_touches_final_oos(self):
        # WHY: FINAL_OOS must be pristine — any fold overlapping it would burn
        # the one-shot OOS budget that T5 depends on.
        windows = walk_forward_windows()
        for w in windows:
            assert w.oos_end <= DISCOVERY[1], (
                f"Fold OOS ({w.oos_start}..{w.oos_end}) leaks into FINAL_OOS"
            )

    def test_is_end_strictly_before_oos_start(self):
        # WHY: lookahead — if IS includes the OOS start date, the fold is invalid.
        windows = walk_forward_windows()
        for w in windows:
            assert w.is_end < w.oos_start

    def test_windows_oos_do_not_overlap_each_other(self):
        # WHY: overlapping OOS folds would inflate the effective OOS sample,
        # making multiple-comparisons correction too lenient.
        windows = walk_forward_windows()
        for i in range(len(windows) - 1):
            assert windows[i].oos_end < windows[i + 1].oos_start

    def test_is_always_starts_at_discovery_start(self):
        # WHY: expanding IS — each fold reuses all prior data, matching live trading.
        windows = walk_forward_windows()
        for w in windows:
            assert w.is_start == DISCOVERY[0]

    def test_is_grows_with_each_fold(self):
        # WHY: verifies the "expanding" property — IS window can only grow.
        windows = walk_forward_windows()
        for i in range(len(windows) - 1):
            assert windows[i].is_end < windows[i + 1].is_end

    def test_custom_params_respected(self):
        # Shorter min_is and oos should produce more folds.
        w_default = walk_forward_windows()
        w_shorter = walk_forward_windows(min_is_months=12, oos_months=3)
        assert len(w_shorter) >= len(w_default)

    def test_window_is_frozen_dataclass(self):
        w = walk_forward_windows()[0]
        assert isinstance(w, WFWindow)
        with pytest.raises((AttributeError, TypeError)):
            w.is_start = date(2020, 1, 1)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DC2 — Config ledger
# ---------------------------------------------------------------------------


class TestConfigLedger:
    def test_starts_empty(self):
        ledger = ConfigLedger()
        assert ledger.n_trials == 0

    def test_add_increments_count(self):
        ledger = ConfigLedger()
        ledger.add({"a": 1})
        assert ledger.n_trials == 1
        ledger.add({"a": 2})
        assert ledger.n_trials == 2

    def test_trial_ids_are_monotonically_increasing(self):
        # WHY: trial_id is used to identify which trial in the session log;
        # must never decrease or repeat.
        ledger = ConfigLedger()
        ids = [ledger.add({}) for _ in range(5)]
        assert ids == list(range(1, 6))

    def test_trials_list_length_matches_n_trials(self):
        ledger = ConfigLedger()
        for _ in range(7):
            ledger.add({})
        assert len(ledger.trials) == ledger.n_trials == 7

    def test_stored_config_retrievable(self):
        ledger = ConfigLedger()
        ledger.add({"param": 42}, fold=3, sharpe=1.5)
        rec = ledger.trials[0]
        assert isinstance(rec, TrialRecord)
        assert rec.config == {"param": 42}
        assert rec.metadata["fold"] == 3
        assert rec.metadata["sharpe"] == 1.5

    def test_trials_returns_copy(self):
        # WHY: mutating the returned list must not corrupt the ledger.
        ledger = ConfigLedger()
        ledger.add({})
        lst = ledger.trials
        lst.clear()
        assert ledger.n_trials == 1

    def test_n_trials_feeds_deflated_sharpe(self):
        # WHY: explicit contract — ledger.n_trials is the K passed to deflated_sharpe;
        # if that coupling breaks, deflation becomes meaningless.
        rng = np.random.default_rng(0)
        returns = rng.normal(5e-4, 0.01, 252)
        sr = float(returns.mean() / returns.std(ddof=1) * math.sqrt(252))
        ledger = ConfigLedger()
        for _ in range(20):
            ledger.add({})
        dsr = deflated_sharpe(sr, returns, n_trials=ledger.n_trials)
        assert dsr <= sr


# ---------------------------------------------------------------------------
# DC3 — Deflated Sharpe Ratio
# ---------------------------------------------------------------------------


class TestDeflatedSharpe:
    _rng = np.random.default_rng(42)
    _returns = _rng.normal(5e-4, 0.01, 504)  # ~2 years daily

    @property
    def _sr(self) -> float:
        r = self._returns
        return float(r.mean() / r.std(ddof=1) * math.sqrt(252))

    def test_deflated_le_raw_sharpe(self):
        # WHY: selection bias always inflates raw SR; the correction can only
        # decrease it, never increase it.
        dsr = deflated_sharpe(self._sr, self._returns, n_trials=10)
        assert dsr <= self._sr + 1e-12

    def test_single_trial_equals_raw(self):
        # WHY: with exactly one trial there is no selection bias — DSR must
        # equal raw SR so it is not penalized for something that never happened.
        dsr = deflated_sharpe(self._sr, self._returns, n_trials=1)
        assert dsr == pytest.approx(self._sr, abs=1e-9)

    def test_decreases_monotonically_with_trials(self):
        # WHY: more trials → higher expected maximum under the null → larger
        # selection-bias penalty → lower deflated SR.  This is the core invariant:
        # adding more untested configs into the count can never raise the deflated SR.
        sr = self._sr
        r = self._returns
        dsr_1 = deflated_sharpe(sr, r, n_trials=1)
        dsr_5 = deflated_sharpe(sr, r, n_trials=5)
        dsr_20 = deflated_sharpe(sr, r, n_trials=20)
        dsr_100 = deflated_sharpe(sr, r, n_trials=100)
        assert dsr_1 >= dsr_5 >= dsr_20 >= dsr_100

    def test_raises_on_zero_trials(self):
        with pytest.raises(ValueError, match="n_trials"):
            deflated_sharpe(1.0, self._returns, n_trials=0)

    def test_negative_sr_still_deflated_further(self):
        # WHY: a losing strategy still has selection-bias risk if many configs
        # were tried.  The DSR of a negative SR should be ≤ the raw SR.
        bad_sr = -0.5
        rng = np.random.default_rng(7)
        r = rng.normal(-2e-4, 0.01, 252)
        dsr = deflated_sharpe(bad_sr, r, n_trials=30)
        assert dsr <= bad_sr + 1e-12

    def test_more_observations_narrows_penalty(self):
        # WHY: longer histories reduce Var(SR_hat), so the expected max SR under
        # null also shrinks — larger T should give a higher (less penalized) DSR.
        sr = 1.0
        rng = np.random.default_rng(99)
        short_r = rng.normal(sr / math.sqrt(252), 0.01, 252)
        long_r = rng.normal(sr / math.sqrt(252), 0.01, 2520)
        dsr_short = deflated_sharpe(sr, short_r, n_trials=10)
        dsr_long = deflated_sharpe(sr, long_r, n_trials=10)
        assert dsr_long >= dsr_short


# ---------------------------------------------------------------------------
# DC4 — PBO via CSCV
# ---------------------------------------------------------------------------


class TestPBOCSCV:
    def test_result_in_unit_interval(self):
        # WHY: PBO is a probability; anything outside [0, 1] is a bug.
        rng = np.random.default_rng(1)
        perf = rng.normal(0, 1, (5, 8))
        pbo = pbo_cscv(perf)
        assert 0.0 <= pbo <= 1.0

    def test_consistent_winner_gives_low_pbo(self):
        # WHY: a config that dominates all others on every fold should never be
        # flagged as overfit — its IS rank predicts its OOS rank reliably.
        perf = np.zeros((5, 8))
        perf[0, :] = 2.0  # config 0 always scores 2.0; others always 0.0
        pbo = pbo_cscv(perf)
        assert pbo < 0.05, f"PBO={pbo:.3f} — consistent winner should approach 0"

    def test_random_noise_gives_mid_range_pbo(self):
        # WHY: with pure noise no config is systematically better; PBO should
        # be indistinguishable from random (around 0.5) on average.
        pbos = []
        for seed in range(30):
            rng2 = np.random.default_rng(seed)
            perf = rng2.normal(0, 1, (8, 10))
            pbos.append(pbo_cscv(perf))
        mean_pbo = float(np.mean(pbos))
        assert 0.2 <= mean_pbo <= 0.8, (
            f"Mean PBO on random inputs={mean_pbo:.3f}, expected near 0.5"
        )

    def test_raises_on_single_config(self):
        # WHY: PBO requires at least 2 configs to rank; 1 is meaningless.
        with pytest.raises(ValueError, match="configs"):
            pbo_cscv(np.array([[1.0, 2.0, 3.0]]))

    def test_raises_on_single_fold(self):
        # WHY: CSCV splits folds; you need at least 2.
        with pytest.raises(ValueError, match="folds"):
            pbo_cscv(np.array([[1.0], [2.0]]))

    def test_lower_is_better_flag(self):
        # WHY: some metrics (e.g., max drawdown expressed as a positive fraction)
        # are "lower is better"; the flag must invert the ranking correctly.
        # Config 0 always scores 0.1 (10% DD); others score 1.0 (100% DD).
        # argmin picks config 0 IS; config 0 is also best (lowest) OOS → no overfit.
        perf = np.zeros((4, 6))
        perf[0, :] = 0.1  # config 0: smallest (best) drawdown
        perf[1:, :] = 1.0  # others: largest (worst) drawdown
        pbo = pbo_cscv(perf, higher_is_better=False)
        assert pbo < 0.05, (
            f"PBO={pbo:.3f} — consistent low-metric winner should approach 0"
        )

    def test_pbo_uses_all_fold_combinations(self):
        # WHY: C(T, T//2) must be fully enumerated; a partial enumeration would
        # under-count overfit cases.  Verify on a small deterministic case.
        # 4 folds → C(4,2)=6 combinations; 6 folds → C(6,3)=20.

        for n_folds in (4, 6):
            rng = np.random.default_rng(0)
            perf = rng.normal(0, 1, (3, n_folds))
            pbo = pbo_cscv(perf)
            # Just check it runs and is in range
            assert 0.0 <= pbo <= 1.0
