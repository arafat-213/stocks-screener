"""
test_v3tbe0_scaffolding.py — TBE0 done-criteria (specs/v3/04_TRACK_B_EXEC_TASKS.md §TBE0).

Tests encode WHY each constraint matters (Rule 9), not just WHAT it checks.

Done-criteria encoded here:
  [DC1] The 5 fundamental factor names validate in active_factors; unknown names
        are rejected with a loud error — so TBE1/2 can't silently use a misspelled name.
  [DC2] Price-factor floor + all locked V3Config defaults are unchanged after TBE0 —
        extending the valid name set must not silently move any construction knob.
  [DC3] TRACK_B_DISCOVERY added; validation.DISCOVERY and validation.FINAL_OOS are
        byte-for-byte untouched — Track-B runs on its own window without contaminating
        the Track-A canonical splits or the pristine OOS boundary.
  [DC4] Track-A baseline config recovered from 01's T4/T5 ledger (not invented) and
        the values match what the session logs recorded.
"""

from __future__ import annotations

from datetime import date

import pytest

# ---------------------------------------------------------------------------
# DC1 — fundamental factor names validate; bad names rejected
# ---------------------------------------------------------------------------


class TestFundamentalFactorNames:
    def test_earnings_yield_accepted(self):
        """earnings_yield must be a valid active_factor name — TBE1 will implement it."""
        from app.backtest_v2.v3_config import V3Config

        cfg = V3Config(active_factors=["mom_12_1", "earnings_yield"])
        assert "earnings_yield" in cfg.active_factors

    def test_book_to_price_accepted(self):
        from app.backtest_v2.v3_config import V3Config

        cfg = V3Config(active_factors=["book_to_price"])
        assert "book_to_price" in cfg.active_factors

    def test_roe_accepted(self):
        from app.backtest_v2.v3_config import V3Config

        cfg = V3Config(active_factors=["roe"])
        assert "roe" in cfg.active_factors

    def test_accruals_accepted(self):
        from app.backtest_v2.v3_config import V3Config

        cfg = V3Config(active_factors=["accruals"])
        assert "accruals" in cfg.active_factors

    def test_leverage_accepted(self):
        from app.backtest_v2.v3_config import V3Config

        cfg = V3Config(active_factors=["leverage"])
        assert "leverage" in cfg.active_factors

    def test_all_five_fundamental_factors_accepted_together(self):
        """All 5 fundamental factors can coexist with price factors — TBE4/TBE5 need this."""
        from app.backtest_v2.v3_config import V3Config

        cfg = V3Config(
            active_factors=[
                "mom_12_1",
                "earnings_yield",
                "book_to_price",
                "roe",
                "accruals",
                "leverage",
            ]
        )
        assert len(cfg.active_factors) == 6

    def test_unknown_factor_name_rejected_loudly(self):
        """A misspelled or invented name must raise immediately — silent acceptance would let
        a wrong factor silently drop from the composite with no error."""
        from app.backtest_v2.v3_config import V3Config

        with pytest.raises(ValueError, match="unknown"):
            V3Config(active_factors=["mom_12_1", "not_a_real_factor"])

    def test_empty_active_factors_rejected(self):
        from app.backtest_v2.v3_config import V3Config

        with pytest.raises(ValueError):
            V3Config(active_factors=[])

    def test_value_block_constant_contains_correct_members(self):
        """VALUE_BLOCK must match the 03_TRACK_B_PREREG §3 definition exactly."""
        from app.backtest_v2.v3_config import VALUE_BLOCK

        assert VALUE_BLOCK == frozenset({"earnings_yield", "book_to_price"})

    def test_quality_block_constant_contains_correct_members(self):
        """QUALITY_BLOCK must match the 03_TRACK_B_PREREG §3 definition exactly."""
        from app.backtest_v2.v3_config import QUALITY_BLOCK

        assert QUALITY_BLOCK == frozenset({"roe", "accruals", "leverage"})

    def test_blocks_are_disjoint(self):
        """Value and Quality blocks must not overlap — an ISIN can't be in both families."""
        from app.backtest_v2.v3_config import QUALITY_BLOCK, VALUE_BLOCK

        assert VALUE_BLOCK.isdisjoint(QUALITY_BLOCK)

    def test_fundamental_names_is_union_of_blocks(self):
        from app.backtest_v2.v3_config import (
            FUNDAMENTAL_FACTOR_NAMES,
            QUALITY_BLOCK,
            VALUE_BLOCK,
        )

        assert FUNDAMENTAL_FACTOR_NAMES == VALUE_BLOCK | QUALITY_BLOCK


# ---------------------------------------------------------------------------
# DC2 — price-factor floor + locked defaults unchanged
# ---------------------------------------------------------------------------


class TestLockedDefaultsUnchanged:
    """
    TBE0 must NOT silently shift any construction knob.  These tests lock the
    floor defaults so any drift (even a rounding change) becomes a test failure.
    """

    def test_floor_active_factors_is_mom_12_1_only(self):
        from app.backtest_v2.v3_config import V3Config

        cfg = V3Config()
        assert cfg.active_factors == ["mom_12_1"]

    def test_factor_weights_default_is_none_equal_weight(self):
        from app.backtest_v2.v3_config import V3Config

        cfg = V3Config()
        assert cfg.factor_weights is None  # None → equal-weight, must not be changed

    def test_target_positions_default_is_20(self):
        from app.backtest_v2.v3_config import V3Config

        assert V3Config().target_positions == 20

    def test_sell_rank_buffer_default_is_35(self):
        from app.backtest_v2.v3_config import V3Config

        assert V3Config().sell_rank_buffer == 35

    def test_liquidity_floor_default_is_5cr(self):
        from app.backtest_v2.v3_config import V3Config

        assert V3Config().liquidity_floor_cr == 5.0

    def test_rebalance_cadence_default_is_monthly(self):
        from app.backtest_v2.v3_config import V3Config

        assert V3Config().rebalance_cadence == "monthly"

    def test_rank_smoothing_default_is_zero(self):
        from app.backtest_v2.v3_config import V3Config

        assert V3Config().rank_smoothing_months == 0

    def test_price_factor_names_set_unchanged(self):
        """PRICE_FACTOR_NAMES must be the same 5 Track-A names from T0/T1 — no additions."""
        from app.backtest_v2.v3_config import PRICE_FACTOR_NAMES

        assert PRICE_FACTOR_NAMES == frozenset(
            {"mom_12_1", "mom_6_1", "low_vol", "trend_quality", "reversal"}
        )

    def test_price_factors_still_validate(self):
        """All pre-existing Track-A factor names must still be accepted (regression)."""
        from app.backtest_v2.v3_config import PRICE_FACTOR_NAMES, V3Config

        cfg = V3Config(active_factors=list(PRICE_FACTOR_NAMES))
        assert set(cfg.active_factors) == PRICE_FACTOR_NAMES


# ---------------------------------------------------------------------------
# DC3 — TRACK_B_DISCOVERY added; validation splits untouched
# ---------------------------------------------------------------------------


class TestTrackBDiscovery:
    def test_track_b_discovery_constant_exists(self):
        from app.backtest_v2.v3_config import TRACK_B_DISCOVERY

        assert TRACK_B_DISCOVERY is not None

    def test_track_b_discovery_start_is_2020_01_31(self):
        """Start date pinned by TB8 ingest run (03_TRACK_B_PREREG §10)."""
        from app.backtest_v2.v3_config import TRACK_B_DISCOVERY

        assert TRACK_B_DISCOVERY[0] == date(2020, 1, 31)

    def test_track_b_discovery_end_is_2023_06_30(self):
        """End date is the DISCOVERY boundary shared with Track-A (2023-06-30)."""
        from app.backtest_v2.v3_config import TRACK_B_DISCOVERY

        assert TRACK_B_DISCOVERY[1] == date(2023, 6, 30)

    def test_validation_discovery_unchanged(self):
        """validation.DISCOVERY is Track-A's canonical split; TBE0 must not touch it."""
        from app.backtest_v2.validation import DISCOVERY

        assert DISCOVERY == (date(2018, 2, 6), date(2023, 6, 30))

    def test_validation_final_oos_unchanged(self):
        """FINAL_OOS stays pristine; consumed exactly once at TBE8 only."""
        from app.backtest_v2.validation import FINAL_OOS

        assert FINAL_OOS == (date(2023, 7, 1), date(2026, 6, 12))

    def test_track_b_discovery_differs_from_track_a_discovery(self):
        """Track-B starts 2020 (window rescope); Track-A starts 2018. They must not collide."""
        from app.backtest_v2.v3_config import TRACK_B_DISCOVERY
        from app.backtest_v2.validation import DISCOVERY

        assert TRACK_B_DISCOVERY[0] != DISCOVERY[0]
        assert TRACK_B_DISCOVERY[1] == DISCOVERY[1]  # same end date


# ---------------------------------------------------------------------------
# DC4 — Track-A baseline recovered (not invented) from 01's T4/T5 ledger
# ---------------------------------------------------------------------------


class TestTrackABaseline:
    """
    The TRACK_A_BASELINE must match EXACTLY what the 01_TRACK_A_TASKS.md T4/T5
    session logs record.  Any drift means TBE3 is not using the correct anchor.
    """

    def test_baseline_active_factors(self):
        """T5 log: accepted all 5 price factors via greedy Calmar-plateau gate."""
        from app.backtest_v2.v3_config import TRACK_A_BASELINE

        assert set(TRACK_A_BASELINE.active_factors) == {
            "mom_12_1",
            "low_vol",
            "trend_quality",
            "mom_6_1",
            "reversal",
        }

    def test_baseline_cadence_is_monthly(self):
        """T4 L1: cadence coarsening collapsed Calmar → rejected; stays monthly."""
        from app.backtest_v2.v3_config import TRACK_A_BASELINE

        assert TRACK_A_BASELINE.rebalance_cadence == "monthly"

    def test_baseline_sell_buffer_is_70(self):
        """T4 L2 plateau: M=70 selected (lowest-turnover within plateau tolerance)."""
        from app.backtest_v2.v3_config import TRACK_A_BASELINE

        assert TRACK_A_BASELINE.sell_rank_buffer == 70

    def test_baseline_smoothing_is_zero(self):
        """T4 L3: smoothing cut Calmar with minimal turnover benefit → rejected."""
        from app.backtest_v2.v3_config import TRACK_A_BASELINE

        assert TRACK_A_BASELINE.rank_smoothing_months == 0

    def test_baseline_target_positions_is_20(self):
        """N=20 is the locked V3Config default; must not have shifted."""
        from app.backtest_v2.v3_config import TRACK_A_BASELINE

        assert TRACK_A_BASELINE.target_positions == 20

    def test_baseline_equal_weight(self):
        """Factor weights None → equal-weight; the §11 item 3 rule must hold for baseline."""
        from app.backtest_v2.v3_config import TRACK_A_BASELINE

        assert TRACK_A_BASELINE.factor_weights is None
