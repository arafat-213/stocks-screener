"""
T4 acceptance tests — regime overlay (regime.py).

All offline: synthetic index series only — no network, no DB, no parquet.

WHY each test group exists:
  risk_on        — uptrend and DMA-warmup must always yield 1.0; missing dates
                   fall back to 1.0 (conservative default).
  risk_off       — state flips to floor only after debounce_days consecutive
                   days below DMA; 1 or 2 days must not flip (anti-whipsaw).
  recovery       — symmetric debounce on the upside: N consecutive days above
                   DMA required to recover from risk-off.
  no_lookahead   — corrupting future data must leave past decisions unchanged
                   (02 §10.1 applied at the regime layer).
  injection      — overlay runs offline with a synthetic series; proves spec 03
                   wires the real benchmark rather than regime.py fetching it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.backtest_v2.regime import RegimeConfig, RegimeOverlay

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_series(prices: list[float], start: str = "2020-01-01") -> pd.Series:
    dates = pd.date_range(start=start, periods=len(prices), freq="B")
    return pd.Series(prices, index=dates, dtype=float)


def _uptrend(n: int = 300, base: float = 100.0, step: float = 0.5) -> pd.Series:
    """Steady uptrend: stays well above its 200-DMA after warmup."""
    return _make_series([base + step * i for i in range(n)])


def _build_dip_series(
    n_warmup: int = 250,
    dip_prices: list[float] | None = None,
    recover_prices: list[float] | None = None,
) -> pd.Series:
    """Uptrend warmup followed by optional dip and optional recovery."""
    base = [100 + 0.5 * i for i in range(n_warmup)]
    tail = (dip_prices or []) + (recover_prices or [])
    return _make_series(base + tail)


# ---------------------------------------------------------------------------
# Risk-on
# ---------------------------------------------------------------------------


class TestRiskOn:
    def test_steady_uptrend_is_risk_on_after_warmup(self):
        """After DMA warmup, a steady uptrend must always yield 1.0."""
        prices = _uptrend(n=300)
        overlay = RegimeOverlay(prices)
        fracs = [overlay.deployable_fraction(d) for d in prices.index[250:]]
        assert all(f == pytest.approx(1.0) for f in fracs)

    def test_dma_warmup_period_is_risk_on(self):
        """First dma_period-1 days have no DMA → must default to risk-on."""
        prices = _uptrend(n=300)
        overlay = RegimeOverlay(prices, RegimeConfig(dma_period=200))
        # Days 0-198: DMA window not yet full → above treated as True → risk-on
        fracs = [overlay.deployable_fraction(d) for d in prices.index[:199]]
        assert all(f == pytest.approx(1.0) for f in fracs)

    def test_missing_date_defaults_to_risk_on(self):
        """Date absent from the injected series falls back to 1.0."""
        prices = _uptrend(n=250)
        overlay = RegimeOverlay(prices)
        assert overlay.deployable_fraction(pd.Timestamp("1990-01-01")) == pytest.approx(
            1.0
        )


# ---------------------------------------------------------------------------
# Risk-off (debounce)
# ---------------------------------------------------------------------------


class TestRiskOff:
    def test_debounce_3_flips_on_third_consecutive_day(self):
        """
        With debounce=3: day 1 and day 2 below DMA stay risk-on; day 3 flips.

        Setup: 250-day uptrend (DMA ≈ 175) then price drops to 50.
        Days below: n_warmup+0, n_warmup+1, n_warmup+2.
        Expected: 1.0, 1.0, floor.
        """
        cfg = RegimeConfig(debounce_days=3)
        prices = _build_dip_series(n_warmup=250, dip_prices=[50.0] * 10)
        overlay = RegimeOverlay(prices, cfg)
        n = 250
        assert overlay.deployable_fraction(prices.index[n]) == pytest.approx(1.0)
        assert overlay.deployable_fraction(prices.index[n + 1]) == pytest.approx(1.0)
        assert overlay.deployable_fraction(prices.index[n + 2]) == pytest.approx(0.0)

    def test_single_day_below_dma_does_not_flip(self):
        """1 day below DMA with debounce=3 must not trigger risk-off."""
        cfg = RegimeConfig(debounce_days=3)
        prices = _build_dip_series(
            n_warmup=250,
            dip_prices=[50.0],
            recover_prices=[300.0, 300.0, 300.0],
        )
        overlay = RegimeOverlay(prices, cfg)
        assert overlay.deployable_fraction(prices.index[250]) == pytest.approx(1.0)

    def test_two_days_below_dma_does_not_flip(self):
        """2 days below DMA with debounce=3 must not trigger risk-off."""
        cfg = RegimeConfig(debounce_days=3)
        prices = _build_dip_series(
            n_warmup=250,
            dip_prices=[50.0, 50.0],
            recover_prices=[300.0, 300.0],
        )
        overlay = RegimeOverlay(prices, cfg)
        n = 250
        assert overlay.deployable_fraction(prices.index[n]) == pytest.approx(1.0)
        assert overlay.deployable_fraction(prices.index[n + 1]) == pytest.approx(1.0)
        # recovery day: still risk-on (never flipped)
        assert overlay.deployable_fraction(prices.index[n + 2]) == pytest.approx(1.0)

    def test_custom_risk_off_floor(self):
        """risk_off_floor=0.3 → risk-off returns 0.3, not 0.0."""
        cfg = RegimeConfig(risk_off_floor=0.3, debounce_days=3)
        prices = _build_dip_series(n_warmup=250, dip_prices=[50.0] * 10)
        overlay = RegimeOverlay(prices, cfg)
        # 3rd consecutive day below DMA
        assert overlay.deployable_fraction(prices.index[252]) == pytest.approx(0.3)

    def test_debounce_1_flips_immediately(self):
        """debounce=1 means any single day below DMA triggers risk-off."""
        cfg = RegimeConfig(debounce_days=1)
        prices = _build_dip_series(n_warmup=250, dip_prices=[50.0] * 5)
        overlay = RegimeOverlay(prices, cfg)
        # First day below DMA → immediate flip
        assert overlay.deployable_fraction(prices.index[250]) == pytest.approx(0.0)

    def test_sustained_downtrend_stays_risk_off(self):
        """Once risk-off is triggered, sustained below-DMA days stay at floor."""
        cfg = RegimeConfig(debounce_days=3)
        prices = _build_dip_series(n_warmup=250, dip_prices=[50.0] * 20)
        overlay = RegimeOverlay(prices, cfg)
        # All days from the 3rd below-DMA onward should be floor
        fracs = [overlay.deployable_fraction(prices.index[i]) for i in range(252, 270)]
        assert all(f == pytest.approx(0.0) for f in fracs)


# ---------------------------------------------------------------------------
# Recovery (symmetric debounce on the upside)
# ---------------------------------------------------------------------------


class TestRecovery:
    def test_recovery_requires_n_consecutive_days_above(self):
        """
        After risk-off, recovery needs debounce_days consecutive above-DMA days.

        Days 0-1 of recovery: still risk-off; day 2 (3rd): risk-on restored.
        """
        cfg = RegimeConfig(debounce_days=3)
        prices = _build_dip_series(
            n_warmup=250,
            dip_prices=[50.0] * 10,  # trigger risk-off at day 252
            recover_prices=[300.0] * 10,  # recovery — well above DMA
        )
        overlay = RegimeOverlay(prices, cfg)

        # Confirm risk-off is active
        assert overlay.deployable_fraction(prices.index[252]) == pytest.approx(0.0)

        recovery_start = 260  # first day of recover_prices
        assert overlay.deployable_fraction(
            prices.index[recovery_start]
        ) == pytest.approx(0.0)
        assert overlay.deployable_fraction(
            prices.index[recovery_start + 1]
        ) == pytest.approx(0.0)
        assert overlay.deployable_fraction(
            prices.index[recovery_start + 2]
        ) == pytest.approx(1.0)

    def test_partial_recovery_does_not_flip(self):
        """1-day recovery attempt followed by another dip stays risk-off."""
        cfg = RegimeConfig(debounce_days=3)
        prices = _build_dip_series(
            n_warmup=250,
            dip_prices=[50.0] * 10,
            recover_prices=[300.0, 50.0, 50.0, 50.0],  # interrupted recovery
        )
        overlay = RegimeOverlay(prices, cfg)
        recovery_start = 260
        # Brief spike above DMA — should not flip back to risk-on
        assert overlay.deployable_fraction(
            prices.index[recovery_start]
        ) == pytest.approx(0.0)
        assert overlay.deployable_fraction(
            prices.index[recovery_start + 1]
        ) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# No-lookahead
# ---------------------------------------------------------------------------


class TestNoLookahead:
    def test_corrupting_future_data_leaves_past_decisions_unchanged(self):
        """
        No-lookahead (02 §10.1 at the regime layer): overlay for day D must
        depend only on index data ≤ D.  Corrupting all days > cutoff must leave
        fractions for days ≤ cutoff byte-identical.
        """
        cfg = RegimeConfig(debounce_days=3)
        n = 300
        prices_orig = _uptrend(n=n)
        overlay_orig = RegimeOverlay(prices_orig, cfg)

        cutoff = 260
        fracs_orig = [
            overlay_orig.deployable_fraction(prices_orig.index[i])
            for i in range(cutoff)
        ]

        # Corrupt all data after cutoff
        prices_corrupt = prices_orig.copy()
        prices_corrupt.iloc[cutoff:] = 9_999.0
        overlay_corrupt = RegimeOverlay(prices_corrupt, cfg)

        fracs_corrupt = [
            overlay_corrupt.deployable_fraction(prices_orig.index[i])
            for i in range(cutoff)
        ]

        assert fracs_orig == pytest.approx(fracs_corrupt)

    def test_fraction_for_day_d_uses_data_leq_d_only(self):
        """
        Debounce triggers on day D only using closes ≤ D.

        With n_warmup=250 days of uptrend then 3 days at 50:
          - DMA at day 252 still >> 50 (only 3 of 200 window days are at 50).
          - close[252] = 50 < DMA → below; 3 consecutive → risk-off on day 252.
        This confirms the 200-DMA roll at day 252 includes no data beyond day 252.
        """
        cfg = RegimeConfig(debounce_days=3)
        prices = _build_dip_series(n_warmup=250, dip_prices=[50.0] * 5)
        overlay = RegimeOverlay(prices, cfg)
        # Day 252 = index 252 → 3rd consecutive day below DMA → risk-off
        assert overlay.deployable_fraction(prices.index[252]) == pytest.approx(0.0)
        # Day 251 → only 2 consecutive days below → still risk-on
        assert overlay.deployable_fraction(prices.index[251]) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Injected series / offline contract
# ---------------------------------------------------------------------------


class TestInjection:
    def test_runs_offline_with_synthetic_series(self):
        """Overlay accepts a synthetic series with no network I/O (spec 03 wires the real one)."""
        synthetic = _uptrend(n=250)
        overlay = RegimeOverlay(index_prices=synthetic)
        assert isinstance(overlay.deployable_fraction(synthetic.index[-1]), float)

    def test_accepts_date_and_timestamp(self):
        """deployable_fraction accepts both datetime.date and pd.Timestamp."""
        prices = _uptrend(n=250)
        overlay = RegimeOverlay(prices)
        ts = prices.index[240]
        dt = ts.date()
        assert overlay.deployable_fraction(ts) == overlay.deployable_fraction(dt)

    def test_unsorted_input_is_handled(self):
        """Unsorted index_prices must be sorted internally — result equals sorted version."""
        prices_sorted = _uptrend(n=250)
        prices_shuffled = prices_sorted.sample(frac=1, random_state=42)
        overlay_sorted = RegimeOverlay(prices_sorted)
        overlay_shuffled = RegimeOverlay(prices_shuffled)
        for ts in prices_sorted.index[240:]:
            assert overlay_sorted.deployable_fraction(ts) == pytest.approx(
                overlay_shuffled.deployable_fraction(ts)
            )
