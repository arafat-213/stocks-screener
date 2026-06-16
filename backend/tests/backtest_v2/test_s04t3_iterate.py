"""
test_s04t3_iterate.py — Spec 04 T3 done-criteria tests (offline, no live data).

Done-criteria (04_VALIDATION_FLOOR_TASKS T3):
  DC1  Harness runs a coarse single-layer grid on DISCOVERY only; every config
       hits the ledger.
  DC2  Plateau detector implemented and unit-tested: spiky optimum is rejected,
       genuine plateau is accepted.
  DC3  Layer 1 (regime) runner pins date_from/date_to to DISCOVERY on every
       config; FINAL_OOS is never touched.

All tests are offline: engine.run, metrics.compute_metrics, and
precompute_signals are mocked so no parquet reads or network calls occur.
WHY: the iteration harness and plateau logic must be auditable in isolation
from the real dataset; test failures must point to logic bugs, not data gaps.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.iterate import (
    GridPoint,
    PlateauVerdict,
    plateau_check,
    run_regime_layer,
)
from app.backtest_v2.regime import RegimeConfig
from app.backtest_v2.validation import DISCOVERY, FINAL_OOS, ConfigLedger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pt(
    params: dict[str, Any],
    calmar: float,
    trial_id: int = 1,
    sharpe: float = 0.5,
    cagr: float = 0.10,
    max_dd: float = 0.35,
) -> GridPoint:
    return GridPoint(
        params=params,
        trial_id=trial_id,
        calmar=calmar,
        sharpe=sharpe,
        cagr=cagr,
        max_dd=max_dd,
    )


# Shared 1-D axis for most plateau tests
_AX1D: list[tuple[str, list]] = [("debounce_days", [1, 3, 5, 7, 10])]


def _grid1d(calmars: dict[int, float]) -> list[GridPoint]:
    """Build a 1-D grid: debounce_days → calmar."""
    return [
        _pt({"debounce_days": d}, c, trial_id=i + 1)
        for i, (d, c) in enumerate(calmars.items())
    ]


# ---------------------------------------------------------------------------
# DC2 — plateau_check (pure function, no mocking needed)
# ---------------------------------------------------------------------------


class TestPlateauCheckEmptyAndEdge:
    def test_raises_on_empty_points(self):
        # WHY: empty input is always a caller bug; fail loud (Rule 12).
        with pytest.raises(ValueError, match="empty"):
            plateau_check([], _AX1D)

    def test_single_point_no_neighbors_is_not_plateau(self):
        # WHY: with only one grid point there are no neighbors to prove the
        # result generalises.  Conservative treatment: not a plateau.
        pts = [_pt({"debounce_days": 5}, calmar=1.0)]
        v = plateau_check(pts, _AX1D)
        assert not v.has_plateau

    def test_non_positive_winner_calmar_is_not_plateau(self):
        # WHY: a "winner" that loses money has no meaningful plateau —
        # accepting it would pass a guaranteed loser.
        pts = _grid1d({1: -0.5, 3: -0.3, 5: -0.1})
        v = plateau_check(pts, _AX1D)
        assert not v.has_plateau


class TestPlateauCheck1D:
    def test_spike_is_rejected(self):
        # Winner at 5 (calmar=1.0); neighbors at 3 and 7 both have calmar=0.1.
        # 0.1 < 0.85 × 1.0 → SPIKE.
        # WHY: the defining overfit pattern — exactly one parameter value works,
        # everything adjacent collapses.  Must be rejected (04 §4).
        pts = _grid1d({1: 0.3, 3: 0.1, 5: 1.0, 7: 0.1, 10: 0.2})
        v = plateau_check(pts, _AX1D, tolerance=0.85)
        assert not v.has_plateau
        assert v.winner.params["debounce_days"] == 5

    def test_plateau_is_accepted(self):
        # All debounce values produce calmar >= 0.85 of the winner.
        # WHY: a robust parameter is one where nearby values also perform well.
        pts = _grid1d({1: 0.88, 3: 0.92, 5: 1.0, 7: 0.95, 10: 0.90})
        v = plateau_check(pts, _AX1D, tolerance=0.85)
        assert v.has_plateau
        assert v.winner.params["debounce_days"] == 5

    def test_left_boundary_winner_only_right_neighbor_checked(self):
        # Winner at debounce=1 (leftmost); only one neighbor (debounce=3).
        # If that neighbor is good → plateau (conservative in the right direction:
        # we accept it because the available evidence shows robustness).
        pts = _grid1d({1: 1.0, 3: 0.9, 5: 0.5})
        v = plateau_check(pts, _AX1D, tolerance=0.85)
        assert v.has_plateau
        assert v.winner.params["debounce_days"] == 1
        assert len(v.neighbors) == 1  # only right neighbor

    def test_right_boundary_winner_only_left_neighbor_checked(self):
        # Winner at rightmost value; bad left neighbor → spike.
        pts = _grid1d({1: 0.3, 3: 0.3, 5: 0.1, 7: 0.3, 10: 1.0})
        v = plateau_check(pts, _AX1D, tolerance=0.85)
        # Winner at 10; only neighbor is 7 (calmar=0.3 < 0.85).
        assert not v.has_plateau

    def test_tolerance_boundary_exactly_at_threshold(self):
        # Neighbor exactly at tolerance * winner: should pass (>= not >).
        # WHY: the predicate is >=; a neighbor sitting exactly on the line
        # should be treated as passing, not failing.
        pts = _grid1d({1: 0.5, 3: 1.0, 5: 0.85})  # 0.85 == 0.85 × 1.0
        v = plateau_check(pts, _AX1D, tolerance=0.85)
        # Winner at 3; neighbors at 1 (0.5 < 0.85 × 1.0) and 5 (0.85 >= 0.85).
        # Neighbor at 1 fails → spike.
        assert not v.has_plateau

    def test_custom_tolerance_zero_always_passes(self):
        # tolerance=0.0: any positive neighbor calmar passes.
        pts = _grid1d({1: 0.01, 3: 1.0, 5: 0.001})
        v = plateau_check(pts, _AX1D, tolerance=0.0)
        # 0.001 >= 0.0 × 1.0 = 0 → True; 0.01 >= 0 → True → plateau.
        assert v.has_plateau


class TestPlateauCheck2D:
    _AX2D: list[tuple[str, list]] = [
        ("debounce_days", [1, 3, 5]),
        ("risk_off_floor", [0.0, 0.25, 0.50]),
    ]

    def _grid2d(self, calmar_map: dict[tuple, float]) -> list[GridPoint]:
        pts = []
        for i, (params_tuple, calmar) in enumerate(calmar_map.items()):
            d, r = params_tuple
            pts.append(
                _pt({"debounce_days": d, "risk_off_floor": r}, calmar, trial_id=i + 1)
            )
        return pts

    def test_2d_interior_plateau_all_neighbors_pass(self):
        # Winner at (3, 0.25) with 4 neighbors all close to winner calmar.
        # WHY: confirms the 2-D neighbor lookup works correctly — a genuine
        # plateau in both parameter dimensions is accepted.
        cmap = {
            (1, 0.0): 0.90,
            (1, 0.25): 0.91,
            (1, 0.50): 0.88,
            (3, 0.0): 0.92,
            (3, 0.25): 1.00,
            (3, 0.50): 0.93,
            (5, 0.0): 0.89,
            (5, 0.25): 0.90,
            (5, 0.50): 0.87,
        }
        pts = self._grid2d(cmap)
        v = plateau_check(pts, self._AX2D, tolerance=0.85)
        assert v.has_plateau
        assert v.winner.params == {"debounce_days": 3, "risk_off_floor": 0.25}
        # Interior winner has 4 immediate neighbors.
        assert len(v.neighbors) == 4

    def test_2d_spike_one_bad_neighbor_rejects(self):
        # Winner at (3, 0.25); neighbor (3, 0.50) has terrible calmar.
        # WHY: even a single failing neighbor means the optimum is not robust
        # to small parameter changes — reject the configuration.
        cmap = {
            (1, 0.0): 0.90,
            (1, 0.25): 0.90,
            (1, 0.50): 0.88,
            (3, 0.0): 0.92,
            (3, 0.25): 1.00,
            (3, 0.50): 0.10,  # ← bad
            (5, 0.0): 0.88,
            (5, 0.25): 0.90,
            (5, 0.50): 0.87,
        }
        pts = self._grid2d(cmap)
        v = plateau_check(pts, self._AX2D, tolerance=0.85)
        assert not v.has_plateau

    def test_2d_corner_winner_two_neighbors(self):
        # Winner at corner (1, 0.0): neighbors are (3, 0.0) and (1, 0.25) only.
        # Both passing → plateau.
        cmap = {
            (1, 0.0): 1.00,
            (1, 0.25): 0.90,
            (1, 0.50): 0.40,
            (3, 0.0): 0.92,
            (3, 0.25): 0.50,
            (3, 0.50): 0.30,
            (5, 0.0): 0.60,
            (5, 0.25): 0.40,
            (5, 0.50): 0.30,
        }
        pts = self._grid2d(cmap)
        v = plateau_check(pts, self._AX2D, tolerance=0.85)
        # Neighbors: (3, 0.0)=0.92 ✓ and (1, 0.25)=0.90 ✓
        assert v.has_plateau
        assert len(v.neighbors) == 2


class TestPlateauCheckReturnTypes:
    def test_returns_plateau_verdict_instance(self):
        pts = _grid1d({1: 0.9, 3: 1.0, 5: 0.92})
        v = plateau_check(pts, _AX1D)
        assert isinstance(v, PlateauVerdict)

    def test_winner_is_max_calmar(self):
        pts = _grid1d({1: 0.5, 3: 0.8, 5: 1.2, 7: 0.7, 10: 0.6})
        v = plateau_check(pts, _AX1D)
        assert v.winner.calmar == 1.2
        assert v.winner.params["debounce_days"] == 5

    def test_explanation_is_nonempty_string(self):
        pts = _grid1d({1: 0.9, 3: 1.0, 5: 0.92})
        v = plateau_check(pts, _AX1D)
        assert isinstance(v.explanation, str)
        assert len(v.explanation) > 0


# ---------------------------------------------------------------------------
# DC1 + DC3 — run_regime_layer (mocked engine/metrics)
# ---------------------------------------------------------------------------


def _make_fake_engine_result(config: MomentumConfig) -> MagicMock:
    """Minimal fake EngineResult with one snapshot (enough for compute_metrics)."""
    snap = MagicMock()
    snap.date = DISCOVERY[1]
    snap.equity = 1_100_000.0
    snap.cash = 100_000.0
    snap.invested_value = 1_000_000.0
    snap.exposure = 0.9
    snap.n_positions = 10

    result = MagicMock()
    result.snapshots = [snap]
    result.fills_log = []
    result.suspension_log = {}
    result.rebalance_dates_used = []
    result.per_rebalance_turnover = []
    result.config = config
    result.total_cost_paid = 0.0
    return result


def _make_fake_metrics(calmar: float = 0.30, sharpe: float = 0.75) -> MagicMock:
    m = MagicMock()
    m.calmar = calmar
    m.sharpe = sharpe
    m.cagr = 0.12
    m.max_drawdown = 0.40
    return m


class TestRunRegimeLayer:
    """Tests for run_regime_layer — all mocked to stay offline."""

    _SMALL_DEBOUNCE = [3, 5]
    _SMALL_RISK_OFF = [0.0, 0.25]

    @pytest.fixture()
    def mock_dependencies(self):
        """Patch engine.run, metrics.compute_metrics, and precompute_signals."""
        with (
            patch("app.backtest_v2.iterate.engine.run") as mock_run,
            patch("app.backtest_v2.iterate.metrics.compute_metrics") as mock_metrics,
            patch("app.backtest_v2.iterate.precompute_signals") as mock_signals,
        ):
            mock_run.side_effect = lambda prices, cfg, **kw: _make_fake_engine_result(
                cfg
            )
            mock_metrics.return_value = _make_fake_metrics()
            mock_signals.return_value = MagicMock()
            yield mock_run, mock_metrics, mock_signals

    def test_ledger_counts_every_combo(self, mock_dependencies):
        # WHY: if any combo is run without being logged to the ledger, the K count
        # fed to deflated_sharpe will be wrong — the core anti-overfit invariant.
        mock_run, _, _ = mock_dependencies
        prices = MagicMock()
        prices.__len__ = lambda s: 1
        index_prices = MagicMock()
        ledger = ConfigLedger()

        run_regime_layer(
            prices,
            index_prices,
            ledger,
            debounce_grid=self._SMALL_DEBOUNCE,
            risk_off_grid=self._SMALL_RISK_OFF,
        )

        expected = len(self._SMALL_DEBOUNCE) * len(self._SMALL_RISK_OFF)
        assert ledger.n_trials == expected

    def test_results_length_matches_combos(self, mock_dependencies):
        prices = MagicMock()
        index_prices = MagicMock()
        ledger = ConfigLedger()

        points = run_regime_layer(
            prices,
            index_prices,
            ledger,
            debounce_grid=self._SMALL_DEBOUNCE,
            risk_off_grid=self._SMALL_RISK_OFF,
        )

        expected = len(self._SMALL_DEBOUNCE) * len(self._SMALL_RISK_OFF)
        assert len(points) == expected

    def test_trial_ids_are_sequential_from_one(self, mock_dependencies):
        # WHY: trial IDs uniquely identify configs in the session log;
        # gaps or duplicates make the ledger untrustworthy.
        prices = MagicMock()
        index_prices = MagicMock()
        ledger = ConfigLedger()

        points = run_regime_layer(
            prices,
            index_prices,
            ledger,
            debounce_grid=self._SMALL_DEBOUNCE,
            risk_off_grid=self._SMALL_RISK_OFF,
        )

        ids = sorted(p.trial_id for p in points)
        assert ids == list(range(1, len(points) + 1))

    def test_discovery_bounds_pinned_on_all_configs(self, mock_dependencies):
        # WHY: if any config uses date_from / date_to outside DISCOVERY, it
        # might consume FINAL_OOS data — the cardinal overfit violation (04 §5).
        mock_run, _, _ = mock_dependencies
        prices = MagicMock()
        index_prices = MagicMock()
        ledger = ConfigLedger()

        run_regime_layer(
            prices,
            index_prices,
            ledger,
            debounce_grid=self._SMALL_DEBOUNCE,
            risk_off_grid=self._SMALL_RISK_OFF,
        )

        for engine_call in mock_run.call_args_list:
            cfg: MomentumConfig = engine_call.args[1]
            assert cfg.date_from == DISCOVERY[0], (
                f"date_from={cfg.date_from!r} != DISCOVERY[0]={DISCOVERY[0]!r}"
            )
            assert cfg.date_to == DISCOVERY[1], (
                f"date_to={cfg.date_to!r} != DISCOVERY[1]={DISCOVERY[1]!r}"
            )

    def test_final_oos_never_touched(self, mock_dependencies):
        # WHY: a config with date_from or date_to inside FINAL_OOS would burn
        # the one-shot OOS block that T5 depends on.
        mock_run, _, _ = mock_dependencies
        prices = MagicMock()
        index_prices = MagicMock()
        ledger = ConfigLedger()

        run_regime_layer(
            prices,
            index_prices,
            ledger,
            debounce_grid=self._SMALL_DEBOUNCE,
            risk_off_grid=self._SMALL_RISK_OFF,
        )

        for engine_call in mock_run.call_args_list:
            cfg: MomentumConfig = engine_call.args[1]
            # date_from and date_to must both be strictly within DISCOVERY.
            assert cfg.date_from < FINAL_OOS[0], (
                f"date_from={cfg.date_from} touches FINAL_OOS"
            )
            assert cfg.date_to < FINAL_OOS[0], (
                f"date_to={cfg.date_to} touches FINAL_OOS"
            )

    def test_each_combo_uses_distinct_regime_config(self, mock_dependencies):
        # WHY: if regime_config is shared (same object) across calls, all runs
        # would use the same debounce/risk_off — the sweep would be meaningless.
        mock_run, _, _ = mock_dependencies
        prices = MagicMock()
        index_prices = MagicMock()
        ledger = ConfigLedger()

        run_regime_layer(
            prices,
            index_prices,
            ledger,
            debounce_grid=self._SMALL_DEBOUNCE,
            risk_off_grid=self._SMALL_RISK_OFF,
        )

        regime_configs = [
            engine_call.kwargs["regime_config"]
            for engine_call in mock_run.call_args_list
        ]
        # Each call should have a distinct (debounce, risk_off) pair.
        pairs = {(rc.debounce_days, rc.risk_off_floor) for rc in regime_configs}
        expected_pairs = len(self._SMALL_DEBOUNCE) * len(self._SMALL_RISK_OFF)
        assert len(pairs) == expected_pairs

    def test_grid_point_params_match_regime_config(self, mock_dependencies):
        # WHY: the GridPoint.params dict must faithfully record what was passed
        # to the engine; discrepancies would corrupt the session log.
        mock_run, _, _ = mock_dependencies
        prices = MagicMock()
        index_prices = MagicMock()
        ledger = ConfigLedger()

        points = run_regime_layer(
            prices,
            index_prices,
            ledger,
            debounce_grid=self._SMALL_DEBOUNCE,
            risk_off_grid=self._SMALL_RISK_OFF,
        )

        for engine_call, gp in zip(mock_run.call_args_list, points):
            rc: RegimeConfig = engine_call.kwargs["regime_config"]
            assert gp.params["debounce_days"] == rc.debounce_days
            assert gp.params["risk_off_floor"] == rc.risk_off_floor

    def test_floor_config_knobs_unchanged(self, mock_dependencies):
        # WHY: layer 1 sweeps ONLY regime params; all MomentumConfig fields
        # must stay at floor values (04 §4 — one layer at a time).
        mock_run, _, _ = mock_dependencies
        floor = MomentumConfig()
        prices = MagicMock()
        index_prices = MagicMock()
        ledger = ConfigLedger()

        run_regime_layer(
            prices,
            index_prices,
            ledger,
            debounce_grid=self._SMALL_DEBOUNCE,
            risk_off_grid=self._SMALL_RISK_OFF,
            floor_config=floor,
        )

        for engine_call in mock_run.call_args_list:
            cfg: MomentumConfig = engine_call.args[1]
            assert cfg.target_positions == floor.target_positions
            assert cfg.sell_rank_buffer == floor.sell_rank_buffer
            assert cfg.liquidity_floor_cr == floor.liquidity_floor_cr
            assert cfg.rebalance == floor.rebalance

    def test_signals_precomputed_once_not_per_combo(self, mock_dependencies):
        # WHY: recomputing signals once per combo would multiply the wall-clock
        # time by K without changing results — only the regime overlay changes.
        _, _, mock_signals = mock_dependencies
        prices = MagicMock()
        index_prices = MagicMock()
        ledger = ConfigLedger()

        run_regime_layer(
            prices,
            index_prices,
            ledger,
            debounce_grid=self._SMALL_DEBOUNCE,
            risk_off_grid=self._SMALL_RISK_OFF,
        )

        assert mock_signals.call_count == 1, (
            f"precompute_signals called {mock_signals.call_count}× "
            f"but should be called exactly once"
        )

    def test_cost_level_is_base_for_all_runs(self, mock_dependencies):
        # WHY: comparison across combos is only valid if cost_level is constant;
        # mixing optimistic vs pessimistic would confound the regime-parameter effect.
        mock_run, _, _ = mock_dependencies
        prices = MagicMock()
        index_prices = MagicMock()
        ledger = ConfigLedger()

        run_regime_layer(
            prices,
            index_prices,
            ledger,
            debounce_grid=self._SMALL_DEBOUNCE,
            risk_off_grid=self._SMALL_RISK_OFF,
        )

        for engine_call in mock_run.call_args_list:
            assert engine_call.kwargs.get("cost_level") == "base"
