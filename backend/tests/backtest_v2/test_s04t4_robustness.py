"""
test_s04t4_robustness.py — Spec 04 T4 done-criteria tests (offline, no live data).

Done-criteria (04_VALIDATION_FLOOR_TASKS T4):
  DC1  All five §6 checks implemented and runnable on the candidate.
  DC2  Each check reports explicit PASS/FAIL (Rule 12); a failure blocks T5.

Design:
  - Engine, metrics, and benchmark calls are mocked so tests stay offline.
  - Each test class covers one check function; cases verify PASS, FAIL, and the
    defining properties (ledger counting, DISCOVERY bounds, threshold arithmetic).
  - check_turnover_capacity is pure arithmetic — no mocking needed.

WHY offline mocks: the robustness logic and threshold arithmetic must be
auditable in isolation from real data.  A test that requires live parquet reads
cannot run in CI and cannot pinpoint whether a failure is in logic or data.
"""

from __future__ import annotations

import math
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.metrics import BacktestMetrics, BenchmarkMetrics, PerNameStats
from app.backtest_v2.robustness import (
    CANDIDATE_REGIME,
    DISCOVERY,
    GLITCH_PNL_RATIO_THRESHOLD,
    MAX_ADV_PARTICIPATION_PCT,
    N_TOP_CONTRIBUTORS,
    SUBPERIODS,
    UNIVERSE_PERTURB_THRESHOLD,
    CheckResult,
    check_cost_stress,
    check_neighborhood,
    check_subperiod_stability,
    check_turnover_capacity,
    check_universe_perturbation,
)
from app.backtest_v2.validation import ConfigLedger

# ---------------------------------------------------------------------------
# Helpers — fake engine results + metrics
# ---------------------------------------------------------------------------


def _fake_result(start: date = DISCOVERY[0], end: date = DISCOVERY[1]) -> MagicMock:
    """Minimal fake EngineResult with two snapshots (enough for compute_metrics)."""
    snap_start = MagicMock()
    snap_start.date = start
    snap_start.equity = 1_000_000.0
    snap_start.cash = 100_000.0
    snap_start.invested_value = 900_000.0
    snap_start.exposure = 0.9
    snap_start.n_positions = 10

    snap_end = MagicMock()
    snap_end.date = end
    snap_end.equity = 1_100_000.0
    snap_end.cash = 100_000.0
    snap_end.invested_value = 1_000_000.0
    snap_end.exposure = 0.9
    snap_end.n_positions = 10

    r = MagicMock()
    r.snapshots = [snap_start, snap_end]
    r.fills_log = []
    r.suspension_log = {}
    r.rebalance_dates_used = []
    r.per_rebalance_turnover = []
    r.total_cost_paid = 0.0
    return r


def _fake_base_metrics(
    calmar: float = 0.30,
    sharpe: float = 0.75,
    cagr: float = 0.12,
    max_dd: float = 0.40,
    n_fills: int = 120,
    ann_turnover: float = 9.0,
    n_calendar_days: int = int(5.4 * 365),
    per_name_stats: list | None = None,
) -> BacktestMetrics:
    """Build a minimal real BacktestMetrics for offline tests."""
    return BacktestMetrics(
        cagr=cagr,
        sharpe=sharpe,
        sortino=1.0,
        annualized_vol=0.18,
        max_drawdown=max_dd,
        max_dd_duration_days=180,
        calmar=calmar,
        avg_exposure=0.85,
        median_exposure=0.88,
        time_in_cash_pct=0.15,
        annualized_turnover=ann_turnover,
        per_rebalance_turnover=[],
        turnover_is_absurd=False,
        n_fills=n_fills,
        total_cost_paid=5000.0,
        per_name_stats=per_name_stats or [],
        hit_rate=0.55,
        start_date=DISCOVERY[0],
        end_date=DISCOVERY[1],
        n_calendar_days=n_calendar_days,
        n_trading_days=int(n_calendar_days * 252 / 365),
        start_equity=1_000_000.0,
        end_equity=1_300_000.0,
    )


def _fake_benchmark_metrics(calmar_ratio: float = 1.2) -> BenchmarkMetrics:
    return BenchmarkMetrics(
        calmar_ratio=calmar_ratio,
        max_dd_ratio=0.65,
        excess_cagr=0.02,
        strategy_cagr=0.12,
        benchmark_cagr=0.10,
        strategy_calmar=0.30,
        benchmark_calmar=0.25,
        strategy_max_dd=0.38,
        benchmark_max_dd=0.40,
        information_ratio=0.15,
        up_capture=0.95,
        down_capture=0.60,
        correlation=0.75,
        beta=0.80,
        n_overlap_days=1300,
    )


def _fake_per_name_stats(n: int = 15) -> list[PerNameStats]:
    """Create n fake PerNameStats entries with distinct realized P&L values."""
    result = []
    for i in range(n):
        pnl = float((n - i) * 10_000)  # descending: highest first
        buy_not = 50_000.0 + i * 1_000
        result.append(
            PerNameStats(
                isin=f"INE{i:06d}",
                symbol=f"STOCK{i:02d}",
                buy_notional=buy_not,
                sell_notional=buy_not + pnl,
                cost_paid=500.0,
                realized_pnl=pnl,
                n_buys=2,
                n_sells=2,
                hold_days=180.0,
                is_closed=True,
            )
        )
    return result


# ---------------------------------------------------------------------------
# §6.1 Cost stress
# ---------------------------------------------------------------------------


class TestCheckCostStress:
    @pytest.fixture()
    def _mocks(self):
        """Patch engine.run, metrics.compute_metrics, benchmark.load_tri,
        benchmark.align_benchmark, and metrics.compute_benchmark_metrics."""
        with (
            patch("app.backtest_v2.robustness.engine.run") as mock_run,
            patch("app.backtest_v2.robustness.metrics.compute_metrics") as mock_metrics,
            patch("app.backtest_v2.robustness.benchmark.load_tri") as mock_tri,
            patch("app.backtest_v2.robustness.benchmark.align_benchmark") as mock_align,
            patch(
                "app.backtest_v2.robustness.metrics.compute_benchmark_metrics"
            ) as mock_bm,
        ):
            mock_run.return_value = _fake_result()
            mock_metrics.return_value = _fake_base_metrics()
            mock_tri.return_value = MagicMock()
            mock_align.return_value = MagicMock()
            yield mock_run, mock_metrics, mock_tri, mock_align, mock_bm

    def test_pass_when_calmar_ratio_above_one(self, _mocks):
        # WHY: §6.1 PASS requires calmar_ratio >= 1.0 at pessimistic cost.
        mock_run, _, _, _, mock_bm = _mocks
        mock_bm.return_value = _fake_benchmark_metrics(calmar_ratio=1.05)

        result = check_cost_stress(MagicMock(), MagicMock(), ConfigLedger())
        assert result.passed
        assert "PASS" in result.summary
        assert result.name == "§6.1 Cost stress"

    def test_fail_when_calmar_ratio_below_one(self, _mocks):
        # WHY: strategy that can't beat Nifty50 at pessimistic cost fails §6.1.
        _, _, _, _, mock_bm = _mocks
        mock_bm.return_value = _fake_benchmark_metrics(calmar_ratio=0.90)

        result = check_cost_stress(MagicMock(), MagicMock(), ConfigLedger())
        assert not result.passed
        assert "FAIL" in result.summary

    def test_engine_called_with_pessimistic_cost(self, _mocks):
        # WHY: cost stress must use pessimistic, not base — wrong level = invalid check.
        mock_run, _, _, _, mock_bm = _mocks
        mock_bm.return_value = _fake_benchmark_metrics(calmar_ratio=1.1)

        check_cost_stress(MagicMock(), MagicMock(), ConfigLedger())
        _, kwargs = mock_run.call_args
        assert kwargs.get("cost_level") == "pessimistic"

    def test_engine_called_with_discovery_bounds(self, _mocks):
        # WHY: FINAL_OOS must stay pristine — only DISCOVERY is allowed here.
        mock_run, _, _, _, mock_bm = _mocks
        mock_bm.return_value = _fake_benchmark_metrics(calmar_ratio=1.1)

        check_cost_stress(MagicMock(), MagicMock(), ConfigLedger())
        positional, _ = mock_run.call_args
        config: MomentumConfig = positional[1]
        assert config.date_from == DISCOVERY[0]
        assert config.date_to == DISCOVERY[1]

    def test_ledger_records_one_trial(self, _mocks):
        # WHY: every engine call must be logged to keep K accurate.
        _, _, _, _, mock_bm = _mocks
        mock_bm.return_value = _fake_benchmark_metrics(calmar_ratio=1.1)

        ledger = ConfigLedger()
        check_cost_stress(MagicMock(), MagicMock(), ledger)
        assert ledger.n_trials == 1

    def test_exactly_one_is_not_pass(self, _mocks):
        # WHY: calmar_ratio=1.0 is the boundary — check passes at >= 1.0.
        _, _, _, _, mock_bm = _mocks
        mock_bm.return_value = _fake_benchmark_metrics(calmar_ratio=1.0)

        result = check_cost_stress(MagicMock(), MagicMock(), ConfigLedger())
        assert result.passed  # >= 1.0 → pass


# ---------------------------------------------------------------------------
# §6.2 Universe perturbation
# ---------------------------------------------------------------------------


class TestCheckUniversePerturbation:
    @pytest.fixture()
    def _mocks(self):
        """Patch engine.run and metrics.compute_metrics."""
        with (
            patch("app.backtest_v2.robustness.engine.run") as mock_run,
            patch("app.backtest_v2.robustness.metrics.compute_metrics") as mock_metrics,
        ):
            mock_run.return_value = _fake_result()
            yield mock_run, mock_metrics

    def test_pass_when_retention_above_threshold(self, _mocks):
        # WHY: retention >= 0.70 means the edge survives removing top contributors.
        _, mock_metrics = _mocks
        base_m = _fake_base_metrics(calmar=0.30, per_name_stats=_fake_per_name_stats())
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)  # 0.25/0.30 = 83%

        result = check_universe_perturbation(
            MagicMock(), MagicMock(), ConfigLedger(), base_m
        )
        assert result.passed

    def test_fail_when_retention_below_threshold(self, _mocks):
        # WHY: calmar collapses after dropping top names → edge was concentrated.
        _, mock_metrics = _mocks
        base_m = _fake_base_metrics(calmar=0.30, per_name_stats=_fake_per_name_stats())
        mock_metrics.return_value = _fake_base_metrics(calmar=0.10)  # 0.10/0.30 = 33%

        result = check_universe_perturbation(
            MagicMock(), MagicMock(), ConfigLedger(), base_m
        )
        assert not result.passed
        assert "FAIL" in result.summary

    def test_drops_exactly_n_top_contributors(self, _mocks):
        # WHY: dropping more or fewer names changes what the check measures.
        mock_run, mock_metrics = _mocks
        per_name = _fake_per_name_stats(20)  # 20 names, sorted by P&L desc
        base_m = _fake_base_metrics(calmar=0.30, per_name_stats=per_name)
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        prices_mock = MagicMock()
        prices_mock.__getitem__ = MagicMock(return_value=prices_mock)
        prices_mock.__invert__ = MagicMock(return_value=prices_mock)
        prices_mock.isin = MagicMock()
        # Use a real pandas DataFrame to verify ISIN filtering
        import pandas as pd

        prices_df = pd.DataFrame(
            {
                "isin": [f"INE{i:06d}" for i in range(20)] + ["INE999999"],
                "date": ["2020-01-01"] * 21,
                "close": [100.0] * 21,
            }
        )
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)
        check_universe_perturbation(prices_df, MagicMock(), ConfigLedger(), base_m)
        # prices passed to engine.run after dropping should have 20-10+1=11 ISINs
        engine_prices_arg = mock_run.call_args[0][0]
        remaining_isins = engine_prices_arg["isin"].nunique()
        assert (
            remaining_isins == 20 - N_TOP_CONTRIBUTORS + 1
        )  # 11 (non-top + one extra)

    def test_ledger_records_one_trial(self, _mocks):
        # WHY: every engine call must be logged.
        _, mock_metrics = _mocks
        base_m = _fake_base_metrics(calmar=0.30, per_name_stats=_fake_per_name_stats())
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        ledger = ConfigLedger()
        check_universe_perturbation(MagicMock(), MagicMock(), ledger, base_m)
        assert ledger.n_trials == 1

    def test_glitch_flag_raised_for_extreme_pnl_ratio(self, _mocks):
        # WHY: a realized_pnl/buy_notional > threshold signals a possible data glitch
        # (e.g., a missed split adjustment inflating the reported return).
        _, mock_metrics = _mocks
        suspicious_name = PerNameStats(
            isin="INE000001",
            symbol="SUSPICIOUS",
            buy_notional=10_000.0,
            sell_notional=70_000.0,
            cost_paid=100.0,
            realized_pnl=60_000.0,  # 6x on 10K buy = suspicious
            n_buys=1,
            n_sells=1,
            hold_days=300.0,
            is_closed=True,
        )
        base_m = _fake_base_metrics(
            calmar=0.30, per_name_stats=[suspicious_name] + _fake_per_name_stats(9)
        )
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        result = check_universe_perturbation(
            MagicMock(), MagicMock(), ConfigLedger(), base_m
        )
        pnl_ratio = 60_000.0 / 10_000.0  # = 6.0
        assert pnl_ratio > GLITCH_PNL_RATIO_THRESHOLD
        assert len(result.details.get("glitch_flags", [])) >= 1

    def test_discovery_bounds_respected(self, _mocks):
        # WHY: FINAL_OOS must remain pristine.
        mock_run, mock_metrics = _mocks
        base_m = _fake_base_metrics(calmar=0.30, per_name_stats=_fake_per_name_stats())
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        check_universe_perturbation(MagicMock(), MagicMock(), ConfigLedger(), base_m)
        positional, _ = mock_run.call_args
        cfg: MomentumConfig = positional[1]
        assert cfg.date_from == DISCOVERY[0]
        assert cfg.date_to == DISCOVERY[1]

    def test_threshold_exactly_at_boundary(self, _mocks):
        # WHY: 70% retention exactly → PASS (boundary is inclusive).
        _, mock_metrics = _mocks
        base_m = _fake_base_metrics(calmar=0.30, per_name_stats=_fake_per_name_stats())
        mock_metrics.return_value = _fake_base_metrics(
            calmar=0.30 * UNIVERSE_PERTURB_THRESHOLD  # = 0.21
        )

        result = check_universe_perturbation(
            MagicMock(), MagicMock(), ConfigLedger(), base_m
        )
        assert result.passed


# ---------------------------------------------------------------------------
# §6.3 Parameter neighborhood
# ---------------------------------------------------------------------------


class TestCheckNeighborhood:
    _N_COMBOS = len([1, 3]) * len([0.0, 0.25, 0.50])  # = 6

    @pytest.fixture()
    def _mocks(self):
        with (
            patch("app.backtest_v2.robustness.engine.run") as mock_run,
            patch("app.backtest_v2.robustness.metrics.compute_metrics") as mock_metrics,
            patch("app.backtest_v2.robustness.precompute_signals") as mock_signals,
        ):
            mock_run.return_value = _fake_result()
            mock_signals.return_value = MagicMock()
            yield mock_run, mock_metrics, mock_signals

    def test_pass_when_plateau_found(self, _mocks):
        # WHY: all neighbors within 85% of winner → genuine robustness.
        _, mock_metrics, _ = _mocks
        # winner calmar=0.265; all neighbors >= 0.85 × 0.265 = 0.225
        calmars = [0.265, 0.260, 0.246, 0.231, 0.250, 0.255]  # all >= 0.225
        mock_metrics.side_effect = [_fake_base_metrics(calmar=c) for c in calmars]

        result = check_neighborhood(MagicMock(), MagicMock(), ConfigLedger())
        assert result.passed
        assert "PASS" in result.summary

    def test_fail_when_spike_found(self, _mocks):
        # WHY: candidate is a lone spike → overfitting artifact → must be rejected.
        _, mock_metrics, _ = _mocks
        # winner calmar=0.265; some neighbor at 0.1 < 0.85 × 0.265 = 0.225
        calmars = [0.265, 0.100, 0.246, 0.231, 0.250, 0.255]
        mock_metrics.side_effect = [_fake_base_metrics(calmar=c) for c in calmars]

        result = check_neighborhood(MagicMock(), MagicMock(), ConfigLedger())
        assert not result.passed
        assert "FAIL" in result.summary

    def test_ledger_counts_all_combos(self, _mocks):
        # WHY: all neighborhood combos must be logged for accurate K count.
        _, mock_metrics, _ = _mocks
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        ledger = ConfigLedger()
        check_neighborhood(MagicMock(), MagicMock(), ledger)
        assert ledger.n_trials == self._N_COMBOS

    def test_discovery_bounds_on_all_engine_calls(self, _mocks):
        # WHY: neighborhood runs must stay inside DISCOVERY.
        mock_run, mock_metrics, _ = _mocks
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        check_neighborhood(MagicMock(), MagicMock(), ConfigLedger())
        for call in mock_run.call_args_list:
            positional, _ = call
            cfg: MomentumConfig = positional[1]
            assert cfg.date_from == DISCOVERY[0]
            assert cfg.date_to == DISCOVERY[1]

    def test_candidate_regime_is_evaluated(self, _mocks):
        # WHY: the candidate (debounce=1, rof=0.25) must be in the neighborhood grid.
        mock_run, mock_metrics, _ = _mocks
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        check_neighborhood(MagicMock(), MagicMock(), ConfigLedger())
        regime_cfgs = [call[1].get("regime_config") for call in mock_run.call_args_list]
        candidate_run = any(
            rc is not None
            and rc.debounce_days == CANDIDATE_REGIME.debounce_days
            and rc.risk_off_floor == CANDIDATE_REGIME.risk_off_floor
            for rc in regime_cfgs
        )
        assert candidate_run, "Candidate regime must be in the neighborhood grid"

    def test_provided_signal_store_reused(self, _mocks):
        # WHY: caller may pre-build signals; the check must not recompute.
        mock_run, mock_metrics, mock_precompute = _mocks
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        fake_ss = MagicMock()
        check_neighborhood(
            MagicMock(), MagicMock(), ConfigLedger(), signal_store=fake_ss
        )
        mock_precompute.assert_not_called()
        for call in mock_run.call_args_list:
            _, kwargs = call
            assert kwargs.get("signal_store") is fake_ss


# ---------------------------------------------------------------------------
# §6.4 Subperiod stability
# ---------------------------------------------------------------------------


class TestCheckSubperiodStability:
    @pytest.fixture()
    def _mocks(self):
        with (
            patch("app.backtest_v2.robustness.engine.run") as mock_run,
            patch("app.backtest_v2.robustness.metrics.compute_metrics") as mock_metrics,
        ):
            mock_run.return_value = _fake_result()
            yield mock_run, mock_metrics

    def test_pass_when_all_subperiods_positive(self, _mocks):
        # WHY: 3/3 positive → clear stability across all market cycles.
        _, mock_metrics = _mocks
        mock_metrics.side_effect = [
            _fake_base_metrics(calmar=0.25),
            _fake_base_metrics(calmar=0.40),
            _fake_base_metrics(calmar=0.18),
        ]
        result = check_subperiod_stability(MagicMock(), MagicMock(), ConfigLedger())
        assert result.passed
        assert result.details["n_positive"] == 3

    def test_pass_when_exactly_two_positive(self, _mocks):
        # WHY: 2/3 meets SUBPERIOD_MIN_POSITIVE — one bad period is acceptable.
        _, mock_metrics = _mocks
        mock_metrics.side_effect = [
            _fake_base_metrics(calmar=0.25),
            _fake_base_metrics(calmar=0.40),
            _fake_base_metrics(calmar=-0.10),  # one negative
        ]
        result = check_subperiod_stability(MagicMock(), MagicMock(), ConfigLedger())
        assert result.passed
        assert result.details["n_positive"] == 2

    def test_fail_when_only_one_positive(self, _mocks):
        # WHY: 1/3 is the single-regime-carrying-everything failure (v1 trap).
        _, mock_metrics = _mocks
        mock_metrics.side_effect = [
            _fake_base_metrics(calmar=-0.05),
            _fake_base_metrics(calmar=0.50),  # only one positive
            _fake_base_metrics(calmar=-0.10),
        ]
        result = check_subperiod_stability(MagicMock(), MagicMock(), ConfigLedger())
        assert not result.passed
        assert "FAIL" in result.summary
        assert result.details["n_positive"] == 1

    def test_fail_when_zero_positive(self, _mocks):
        # WHY: nothing works in any subperiod → fundamental failure.
        _, mock_metrics = _mocks
        mock_metrics.side_effect = [
            _fake_base_metrics(calmar=-0.05),
            _fake_base_metrics(calmar=-0.10),
            _fake_base_metrics(calmar=-0.08),
        ]
        result = check_subperiod_stability(MagicMock(), MagicMock(), ConfigLedger())
        assert not result.passed
        assert result.details["n_positive"] == 0

    def test_nan_calmar_not_counted_as_positive(self, _mocks):
        # WHY: NaN Calmar (zero drawdown edge case) must not count as positive.
        _, mock_metrics = _mocks
        mock_metrics.side_effect = [
            _fake_base_metrics(calmar=float("nan")),
            _fake_base_metrics(calmar=0.40),
            _fake_base_metrics(calmar=float("nan")),
        ]
        result = check_subperiod_stability(MagicMock(), MagicMock(), ConfigLedger())
        assert result.details["n_positive"] == 1
        assert not result.passed

    def test_ledger_counts_one_entry_per_subperiod(self, _mocks):
        # WHY: every engine call must be logged for accurate K.
        _, mock_metrics = _mocks
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        ledger = ConfigLedger()
        check_subperiod_stability(MagicMock(), MagicMock(), ledger)
        assert ledger.n_trials == len(SUBPERIODS)

    def test_discovery_dates_not_exceeded(self, _mocks):
        # WHY: subperiods are within DISCOVERY; none may touch FINAL_OOS.
        mock_run, mock_metrics = _mocks
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        check_subperiod_stability(MagicMock(), MagicMock(), ConfigLedger())
        from app.backtest_v2.validation import FINAL_OOS

        for call in mock_run.call_args_list:
            positional, _ = call
            cfg: MomentumConfig = positional[1]
            assert cfg.date_from >= DISCOVERY[0]
            assert cfg.date_to <= DISCOVERY[1]
            assert cfg.date_to < FINAL_OOS[0]

    def test_all_subperiod_labels_in_details(self, _mocks):
        # WHY: the report must cover all three market cycles.
        _, mock_metrics = _mocks
        mock_metrics.return_value = _fake_base_metrics(calmar=0.25)

        result = check_subperiod_stability(MagicMock(), MagicMock(), ConfigLedger())
        calmar_keys = set(result.details["calmar_per_subperiod"].keys())
        expected = {lbl for lbl, _, _ in SUBPERIODS}
        assert calmar_keys == expected


# ---------------------------------------------------------------------------
# §6.5 Turnover / capacity (pure arithmetic — no mocking)
# ---------------------------------------------------------------------------


class TestCheckTurnoverCapacity:
    def _metrics(
        self, ann_turnover: float, n_fills: int, n_cal_days: int
    ) -> BacktestMetrics:
        return _fake_base_metrics(
            ann_turnover=ann_turnover, n_fills=n_fills, n_calendar_days=n_cal_days
        )

    def test_pass_when_participation_below_threshold(self):
        # 972% turnover, 120 fills, 5.4-year DISCOVERY, ₹10L capital
        # = total_one_way = 1e6 × 9.72 × 5.4 / 2 ≈ 26.2M ₹
        # = avg_trade = 26.2M / 120 ≈ 218K ₹
        # = participation = 218K / 50M = 0.44% << 5%
        m = self._metrics(ann_turnover=9.72, n_fills=120, n_cal_days=int(5.4 * 365))
        result = check_turnover_capacity(m)
        assert result.passed
        assert result.details["participation_%"] < MAX_ADV_PARTICIPATION_PCT

    def test_fail_when_participation_above_threshold(self):
        # Artificially extreme: 5000% turnover, only 5 fills, 1 year → huge avg trade.
        # total_one_way = 1e6 × 50 × 1 / 2 = 25M ₹
        # avg_trade = 25M / 5 = 5M ₹  (= 10% of 50M ADV floor — above threshold)
        m = self._metrics(ann_turnover=50.0, n_fills=5, n_cal_days=365)
        result = check_turnover_capacity(m)
        assert not result.passed
        assert "FAIL" in result.summary

    def test_participation_scales_with_capital(self):
        # Doubling capital doubles participation.
        m = _fake_base_metrics(
            ann_turnover=9.72, n_fills=120, n_calendar_days=int(5.4 * 365)
        )
        r1 = check_turnover_capacity(m, capital=1_000_000.0)
        r2 = check_turnover_capacity(m, capital=2_000_000.0)
        assert math.isclose(
            r2.details["participation_%"],
            2 * r1.details["participation_%"],
            rel_tol=1e-6,
        )

    def test_larger_adv_floor_reduces_participation(self):
        # Higher ADV floor → same trade is a smaller fraction.
        m = _fake_base_metrics(
            ann_turnover=9.72, n_fills=120, n_calendar_days=int(5.4 * 365)
        )
        r1 = check_turnover_capacity(m, liquidity_floor_cr=5.0)
        r2 = check_turnover_capacity(m, liquidity_floor_cr=10.0)
        assert r2.details["participation_%"] < r1.details["participation_%"]

    def test_result_name_is_correct(self):
        m = _fake_base_metrics(
            ann_turnover=9.72, n_fills=120, n_calendar_days=int(5.4 * 365)
        )
        result = check_turnover_capacity(m)
        assert result.name == "§6.5 Turnover / capacity"

    def test_details_include_all_key_fields(self):
        m = _fake_base_metrics(
            ann_turnover=9.72, n_fills=120, n_calendar_days=int(5.4 * 365)
        )
        result = check_turnover_capacity(m)
        for key in ("ann_turnover_%", "n_fills", "avg_trade_inr", "participation_%"):
            assert key in result.details, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# CheckResult dataclass
# ---------------------------------------------------------------------------


class TestCheckResult:
    def test_passed_true_on_pass(self):
        cr = CheckResult(name="test", passed=True, summary="PASS ok")
        assert cr.passed

    def test_details_defaults_to_empty_dict(self):
        cr = CheckResult(name="test", passed=False, summary="FAIL")
        assert cr.details == {}

    def test_details_stored_correctly(self):
        cr = CheckResult(
            name="§6.1",
            passed=True,
            summary="PASS",
            details={"calmar_ratio": 1.2},
        )
        assert cr.details["calmar_ratio"] == 1.2
