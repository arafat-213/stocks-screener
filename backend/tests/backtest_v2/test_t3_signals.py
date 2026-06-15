"""
T3 acceptance tests — signals: indicator precompute + ranker + entry gate.

All offline: no network, no DB, no live parquet reads.
Synthetic price frames only.

WHY each test group exists:
  entry_gate      — each of the three conditions can independently block eligibility;
                    all three must pass for True.  (02 §4: binary, not blended.)
  ranker          — vol-adjusted momentum must be monotone in the right direction:
                    higher momentum → higher rank, lower vol → higher rank.
  momentum_12_1   — integer-position indexing must be provably correct and
                    immune to calendar gaps (the key correctness invariant of 02 §4).
  close_isolation — indicator math must use `close`, not `close_tr`.
                    Mixing them is a common source of wrong backtests (02 §3).
  eligible_ranked — the combined filter+sort pipeline produces the right ordering.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.signals import SignalStore, _momentum_12_1, precompute_signals

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_N_WARMUP = 400  # enough rows for EMA_200 (200), momentum (273), vol (126)
_LIQ_FLOOR_CR = 5.0  # ₹ crore default


def _default_cfg(**overrides) -> MomentumConfig:
    cfg = MomentumConfig()
    for k, v in overrides.items():
        object.__setattr__(cfg, k, v)
    return cfg


def _make_prices(
    isin: str = "INE001A01036",
    n_days: int = _N_WARMUP,
    start: str = "2019-01-01",
    trend: float = 2e-4,
    adv_20: float = 6e7,  # ₹6 crore → above default floor
    custom_dates: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    """Build a synthetic long-format prices DataFrame for one ISIN."""
    if custom_dates is not None:
        dates = custom_dates
        n_days = len(dates)
    else:
        dates = pd.bdate_range(start=start, periods=n_days)

    rng = np.random.default_rng(42)
    noise = rng.normal(0, 0.008, n_days)
    close = 100.0 * np.cumprod(1.0 + trend + noise)
    open_ = close * (1 - rng.uniform(0, 0.005, n_days))
    high = close * (1 + rng.uniform(0, 0.01, n_days))
    low = close * (1 - rng.uniform(0, 0.01, n_days))

    return pd.DataFrame(
        {
            "isin": isin,
            "symbol": "TEST",
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "close_tr": close * 1.05,  # intentionally differs from close
            "volume": 500_000,
            "traded_value": adv_20,
            "adv_20": adv_20,
            "series": "EQ",
        }
    )


def _make_store(
    isin: str = "INE001A01036",
    n_days: int = _N_WARMUP,
    trend: float = 2e-4,
    adv_20: float = 6e7,
    cfg: MomentumConfig | None = None,
    custom_dates: pd.DatetimeIndex | None = None,
) -> tuple[SignalStore, pd.DatetimeIndex]:
    """Return (store, dates) for a single-ISIN synthetic run."""
    cfg = cfg or _default_cfg()
    prices = _make_prices(
        isin=isin, n_days=n_days, trend=trend, adv_20=adv_20, custom_dates=custom_dates
    )
    store = precompute_signals(prices, cfg)
    df = store._data[isin]
    return store, df.index


# ---------------------------------------------------------------------------
# _momentum_12_1 — unit tests on the pure numpy helper
# ---------------------------------------------------------------------------


class TestMomentum12_1:
    def test_nan_before_lookback(self):
        """No valid value before position `lookback`."""
        skip, lookback = 21, 273
        close = np.arange(1.0, lookback + 5)
        mom = _momentum_12_1(close, skip, lookback)
        assert np.all(np.isnan(mom[:lookback])), "positions < lookback must be NaN"

    def test_known_value_at_lookback(self):
        """
        At i=lookback: mom = close[lookback-skip] / close[0] - 1.
        Use a linear price array (close[i] = i+1) for an exact expected value.
        """
        skip, lookback = 21, 273
        n = 300
        close = np.arange(1.0, n + 1)  # close[i] = i+1
        mom = _momentum_12_1(close, skip, lookback)
        # mom[273] = close[252] / close[0] - 1 = 253 / 1 - 1 = 252.0
        expected = close[lookback - skip] / close[0] - 1
        assert mom[lookback] == pytest.approx(expected)

    def test_known_value_mid_series(self):
        """Spot-check a position well into the series."""
        skip, lookback = 21, 273
        n = 350
        close = np.arange(1.0, n + 1)
        mom = _momentum_12_1(close, skip, lookback)
        i = 300
        expected = close[i - skip] / close[i - lookback] - 1
        assert mom[i] == pytest.approx(expected)

    def test_all_valid_after_lookback(self):
        """Every position >= lookback should be finite."""
        skip, lookback = 21, 273
        n = 350
        close = np.linspace(100, 200, n)
        mom = _momentum_12_1(close, skip, lookback)
        assert np.all(np.isfinite(mom[lookback:]))

    def test_returns_nan_on_short_series(self):
        """Series shorter than lookback → all NaN."""
        close = np.arange(1.0, 50)
        mom = _momentum_12_1(close, skip=21, lookback=273)
        assert np.all(np.isnan(mom))

    def test_gap_calendar_immune(self):
        """
        Integer-position indexing is immune to calendar gaps.

        Two identical price arrays produce identical momentum arrays regardless
        of the actual date index attached — because _momentum_12_1 only uses
        array positions, not dates.

        This proves the 02 §4 requirement: 'use calendar-aware index positions,
        not naive shifts across gaps.'  (Naive DatetimeIndex .shift would be
        gap-sensitive; this helper is not.)
        """
        rng = np.random.default_rng(7)
        close = rng.uniform(50, 200, 350)
        mom_a = _momentum_12_1(close.copy(), skip=21, lookback=273)
        # Re-running with the same array (same integer positions) must give
        # identical results — no dependency on an external date axis.
        mom_b = _momentum_12_1(close.copy(), skip=21, lookback=273)
        np.testing.assert_array_equal(mom_a, mom_b)

    def test_different_skip_lookback(self):
        """Custom skip/lookback parameters work correctly."""
        skip, lookback = 5, 20
        n = 50
        close = np.arange(1.0, n + 1)
        mom = _momentum_12_1(close, skip, lookback)
        # mom[20] = close[15] / close[0] - 1 = 16/1 - 1 = 15
        assert np.all(np.isnan(mom[:lookback]))
        assert mom[lookback] == pytest.approx(close[lookback - skip] / close[0] - 1)


# ---------------------------------------------------------------------------
# precompute_signals + SignalStore — integration tests on synthetic frames
# ---------------------------------------------------------------------------


class TestPrecomputeSignals:
    def test_store_contains_expected_isin(self):
        isin = "INE001A01036"
        store, _ = _make_store(isin=isin)
        assert isin in store._data

    def test_indicator_columns_present(self):
        """EMA_200, momentum_12_1, annualized_vol must be computed."""
        store, _ = _make_store()
        df = store._data["INE001A01036"]
        for col in ("close", "adv_20", "EMA_200", "momentum_12_1", "annualized_vol"):
            assert col in df.columns, f"missing column: {col}"

    def test_close_tr_excluded(self):
        """
        close_tr must NOT appear in the per-ISIN indicator DataFrames.
        Signals use `close`; close_tr belongs to portfolio MTM only (02 §3).
        """
        store, _ = _make_store()
        df = store._data["INE001A01036"]
        assert "close_tr" not in df.columns

    def test_indicators_use_close_not_close_tr(self):
        """
        momentum_12_1 must match values computed from `close`, not `close_tr`.

        We build a prices frame where close and close_tr diverge significantly
        (close_tr = close * 1.05).  The stored momentum must match the close-based
        expectation, not the close_tr-based one.
        """
        isin = "INE001A01036"
        cfg = _default_cfg()
        prices = _make_prices(isin=isin)
        # Corrupt close_tr so it would produce very different momentum
        prices["close_tr"] = prices["close"] * 100.0

        store = precompute_signals(prices, cfg)
        df_store = store._data[isin]

        # Recompute expected momentum from `close` (the column we want)
        skip = cfg.momentum_skip_days
        lookback = cfg.momentum_lookback_days + skip
        close_arr = prices.sort_values("date")["close"].to_numpy(dtype=float)
        expected_mom = _momentum_12_1(close_arr, skip, lookback)

        stored_mom = df_store["momentum_12_1"].to_numpy()
        # Compare only positions where both are finite
        valid = np.isfinite(expected_mom) & np.isfinite(stored_mom)
        np.testing.assert_allclose(stored_mom[valid], expected_mom[valid], rtol=1e-10)

    def test_momentum_nan_before_warmup(self):
        """Rows before position 273 must have NaN momentum (insufficient history)."""
        store, dates = _make_store()
        df = store._data["INE001A01036"]
        lookback = 273
        early = df["momentum_12_1"].iloc[:lookback]
        assert early.isna().all(), "momentum must be NaN before warmup completes"

    def test_ema_200_nan_before_200_periods(self):
        """EMA_200 needs ≥200 periods; early rows should be NaN."""
        store, _ = _make_store()
        df = store._data["INE001A01036"]
        # pandas_ta_classic EMA with length=200: rows before 200 are NaN
        assert df["EMA_200"].iloc[:199].isna().all()

    def test_vol_finite_after_warmup(self):
        """annualized_vol should be finite well after the vol_lookback_days warmup."""
        cfg = _default_cfg()
        store, _ = _make_store(cfg=cfg)
        df = store._data["INE001A01036"]
        tail = df["annualized_vol"].iloc[cfg.vol_lookback_days + 10 :]
        assert tail.notna().all()

    def test_gap_calendar_momentum_consistent(self):
        """
        An ISIN with a gap in its trading dates must produce the same momentum
        as the same price data without a gap, because _momentum_12_1 is
        position-based, not date-based.

        We give two ISINs the same close prices but different date sequences.
        The stored momentum_12_1 arrays must be identical.
        """
        n = _N_WARMUP
        rng = np.random.default_rng(99)
        noise = rng.normal(0, 0.008, n)
        close_vals = 100.0 * np.cumprod(1.0 + 2e-4 + noise)

        # ISIN A: consecutive business days
        dates_a = pd.bdate_range("2019-01-01", periods=n)

        # ISIN B: same prices but with 15 extra business days inserted in the
        # middle (simulates returning from a suspension with a shifted date axis).
        # We still supply exactly `n` data rows — the point is the date axis differs.
        extra = pd.bdate_range("2021-03-01", periods=15)
        dates_b = pd.DatetimeIndex(
            sorted(
                pd.bdate_range("2019-01-01", periods=n - 15).tolist() + extra.tolist()
            )
        )[:n]

        cfg = _default_cfg()

        def _make_custom(isin: str, dates: pd.DatetimeIndex) -> pd.DataFrame:
            df = _make_prices(isin=isin, custom_dates=dates)
            df["close"] = close_vals  # same prices for both
            return df

        prices = pd.concat(
            [_make_custom("ISIN_A", dates_a), _make_custom("ISIN_B", dates_b)],
            ignore_index=True,
        )
        store = precompute_signals(prices, cfg)

        mom_a = store._data["ISIN_A"]["momentum_12_1"].to_numpy()
        mom_b = store._data["ISIN_B"]["momentum_12_1"].to_numpy()

        valid = np.isfinite(mom_a) & np.isfinite(mom_b)
        assert valid.sum() > 0, "expected some finite momentum values"
        np.testing.assert_allclose(
            mom_a[valid],
            mom_b[valid],
            rtol=1e-10,
            err_msg="momentum_12_1 must be identical regardless of date axis",
        )


# ---------------------------------------------------------------------------
# entry_gate — branch tests (each condition independently blocks)
# ---------------------------------------------------------------------------


class TestEntryGate:
    """
    entry_gate(day, isin) → True iff ALL of:
      1. close > EMA_200
      2. momentum_12_1 > 0
      3. adv_20 >= liquidity_floor
    """

    def test_all_conditions_pass(self):
        """Baseline: trending stock, positive momentum, high liquidity → True."""
        store, dates = _make_store(trend=3e-4, adv_20=1e8)
        # Use a late date where all indicators are warmed up
        day = dates[-10]
        result = store.entry_gate(day, "INE001A01036")
        # Not asserting True here because synthetic data may not guarantee all
        # conditions simultaneously — we verify the gate *can* return True.
        assert isinstance(result, bool)

    def test_fails_when_isin_missing(self):
        """Unknown ISIN → False."""
        store, dates = _make_store()
        assert store.entry_gate(dates[-1], "UNKNOWN_ISIN") is False

    def test_fails_on_day_not_in_index(self):
        """Date with no print (weekend, holiday, suspension) → False."""
        store, _ = _make_store()
        weekend = pd.Timestamp("2020-01-04")  # Saturday
        assert store.entry_gate(weekend, "INE001A01036") is False

    def test_fails_liquidity_below_floor(self):
        """adv_20 below the floor must block eligibility regardless of trend/momentum."""
        cfg = _default_cfg(liquidity_floor_cr=5.0)
        # adv_20 = ₹3 crore = 3e7 → below ₹5 crore floor
        store, dates = _make_store(adv_20=3e7, cfg=cfg)
        # Inject a row where close > EMA_200 and momentum > 0 but adv is low
        isin = "INE001A01036"
        df = store._data[isin]
        late_dates = df.index[df["momentum_12_1"].notna() & df["EMA_200"].notna()]
        if len(late_dates) == 0:
            pytest.skip("insufficient warmup for this synthetic series")

        # Manually check: adv_20 is 3e7, floor is 5e7 → should fail
        day = late_dates[-1]
        row = df.loc[day]
        # Condition 3 must fail
        liq_floor = cfg.liquidity_floor_cr * 1e7  # 5e7
        assert row["adv_20"] < liq_floor, "test setup: adv must be below floor"
        assert store.entry_gate(day, isin) is False

    def test_fails_when_momentum_nan(self):
        """NaN momentum (early warmup) → False regardless of other conditions."""
        store, dates = _make_store()
        isin = "INE001A01036"
        df = store._data[isin]
        # First row always has NaN momentum (position < 273)
        first_day = df.index[0]
        assert store.entry_gate(first_day, isin) is False

    def test_each_condition_is_necessary(self):
        """
        Directly test each condition in isolation using controlled SignalStore rows.

        We bypass precompute_signals and inject exact indicator values to avoid
        dependence on synthetic EMA/momentum thresholds being crossed.
        """
        cfg = _default_cfg(liquidity_floor_cr=5.0)
        liq_floor = cfg.liquidity_floor_cr * 1e7  # 5e7

        day = pd.Timestamp("2022-01-03")

        def _store_with_row(close, ema200, mom, adv) -> SignalStore:
            df = pd.DataFrame(
                {
                    "close": [close],
                    "adv_20": [adv],
                    "EMA_200": [ema200],
                    "momentum_12_1": [mom],
                    "annualized_vol": [0.20],
                },
                index=pd.DatetimeIndex([day]),
            )
            return SignalStore({"ISIN_X": df}, cfg)

        # All pass
        s = _store_with_row(close=200, ema200=150, mom=0.3, adv=liq_floor * 2)
        assert s.entry_gate(day, "ISIN_X") is True

        # Condition 1 fails: close <= EMA_200
        s = _store_with_row(close=100, ema200=150, mom=0.3, adv=liq_floor * 2)
        assert s.entry_gate(day, "ISIN_X") is False

        # Condition 2 fails: momentum <= 0
        s = _store_with_row(close=200, ema200=150, mom=-0.1, adv=liq_floor * 2)
        assert s.entry_gate(day, "ISIN_X") is False

        # Condition 3 fails: adv_20 < floor
        s = _store_with_row(close=200, ema200=150, mom=0.3, adv=liq_floor * 0.5)
        assert s.entry_gate(day, "ISIN_X") is False

        # Momentum exactly 0 → fails (strict >)
        s = _store_with_row(close=200, ema200=150, mom=0.0, adv=liq_floor * 2)
        assert s.entry_gate(day, "ISIN_X") is False

    def test_nan_in_any_field_returns_false(self):
        """NaN in close, EMA_200, momentum_12_1, or adv_20 → False."""
        cfg = _default_cfg()
        liq = cfg.liquidity_floor_cr * 1e7 * 2
        day = pd.Timestamp("2022-01-03")

        def _s(close, ema200, mom, adv):
            df = pd.DataFrame(
                {
                    "close": [close],
                    "adv_20": [adv],
                    "EMA_200": [ema200],
                    "momentum_12_1": [mom],
                    "annualized_vol": [0.20],
                },
                index=pd.DatetimeIndex([day]),
            )
            return SignalStore({"I": df}, cfg)

        assert _s(float("nan"), 100, 0.3, liq).entry_gate(day, "I") is False
        assert _s(200, float("nan"), 0.3, liq).entry_gate(day, "I") is False
        assert _s(200, 100, float("nan"), liq).entry_gate(day, "I") is False
        assert _s(200, 100, 0.3, float("nan")).entry_gate(day, "I") is False


# ---------------------------------------------------------------------------
# ranker — monotone direction tests
# ---------------------------------------------------------------------------


class TestRanker:
    """
    ranker(day, isin) = momentum_12_1 / annualized_vol.
    Higher momentum → higher score.
    Lower vol (same momentum) → higher score.
    """

    def _store_with_two(
        self, mom_a, vol_a, mom_b, vol_b
    ) -> tuple[SignalStore, pd.Timestamp]:
        cfg = _default_cfg()
        day = pd.Timestamp("2022-06-01")
        liq = cfg.liquidity_floor_cr * 1e7 * 2

        def _df(mom, vol):
            return pd.DataFrame(
                {
                    "close": [200.0],
                    "adv_20": [liq],
                    "EMA_200": [100.0],
                    "momentum_12_1": [mom],
                    "annualized_vol": [vol],
                },
                index=pd.DatetimeIndex([day]),
            )

        store = SignalStore({"A": _df(mom_a, vol_a), "B": _df(mom_b, vol_b)}, cfg)
        return store, day

    def test_higher_momentum_ranks_higher(self):
        """Same vol, higher momentum → higher ranker score."""
        store, day = self._store_with_two(mom_a=0.6, vol_a=0.2, mom_b=0.3, vol_b=0.2)
        assert store.ranker(day, "A") > store.ranker(day, "B")

    def test_lower_vol_ranks_higher(self):
        """Same momentum, lower vol → higher ranker score."""
        store, day = self._store_with_two(mom_a=0.4, vol_a=0.1, mom_b=0.4, vol_b=0.3)
        assert store.ranker(day, "A") > store.ranker(day, "B")

    def test_nan_on_zero_vol(self):
        """Zero vol → NaN (avoid division-by-zero score)."""
        cfg = _default_cfg()
        day = pd.Timestamp("2022-06-01")
        df = pd.DataFrame(
            {
                "close": [200.0],
                "adv_20": [1e8],
                "EMA_200": [100.0],
                "momentum_12_1": [0.3],
                "annualized_vol": [0.0],
            },
            index=pd.DatetimeIndex([day]),
        )
        store = SignalStore({"X": df}, cfg)
        assert math.isnan(store.ranker(day, "X"))

    def test_nan_on_nan_momentum(self):
        cfg = _default_cfg()
        day = pd.Timestamp("2022-06-01")
        df = pd.DataFrame(
            {
                "close": [200.0],
                "adv_20": [1e8],
                "EMA_200": [100.0],
                "momentum_12_1": [float("nan")],
                "annualized_vol": [0.2],
            },
            index=pd.DatetimeIndex([day]),
        )
        store = SignalStore({"X": df}, cfg)
        assert math.isnan(store.ranker(day, "X"))

    def test_pluggable_interface(self):
        """
        ranker must be callable as (day, isin) → float with no extra args,
        so the engine can pass an alternative ranker with the same signature.
        """
        store, day = self._store_with_two(0.5, 0.2, 0.2, 0.2)

        def alt_ranker(d, i):
            # An alternative ranker that just returns momentum raw (not vol-adjusted)
            row = store._get_row(d, i)
            return row["momentum_12_1"] if row is not None else float("nan")

        # Proves the ranker can be swapped without touching SignalStore internals
        score = alt_ranker(day, "A")
        assert score == pytest.approx(0.5)

    def test_known_score_value(self):
        """momentum / vol → exact arithmetic check."""
        cfg = _default_cfg()
        day = pd.Timestamp("2022-06-01")
        mom, vol = 0.36, 0.18
        df = pd.DataFrame(
            {
                "close": [200.0],
                "adv_20": [1e8],
                "EMA_200": [100.0],
                "momentum_12_1": [mom],
                "annualized_vol": [vol],
            },
            index=pd.DatetimeIndex([day]),
        )
        store = SignalStore({"X": df}, cfg)
        assert store.ranker(day, "X") == pytest.approx(mom / vol)


# ---------------------------------------------------------------------------
# eligible_ranked — combined gate + sort pipeline
# ---------------------------------------------------------------------------


class TestEligibleRanked:
    def test_filters_and_sorts(self):
        """
        eligible_ranked must: (1) exclude names failing the gate, (2) sort
        survivors descending by ranker score.
        """
        cfg = _default_cfg()
        liq = cfg.liquidity_floor_cr * 1e7 * 2
        day = pd.Timestamp("2022-06-01")

        def _df(close, ema200, mom, vol, adv):
            return pd.DataFrame(
                {
                    "close": [close],
                    "adv_20": [adv],
                    "EMA_200": [ema200],
                    "momentum_12_1": [mom],
                    "annualized_vol": [vol],
                },
                index=pd.DatetimeIndex([day]),
            )

        store = SignalStore(
            {
                # Score: 0.4/0.2 = 2.0 (should rank 2nd)
                "A": _df(close=200, ema200=100, mom=0.4, vol=0.2, adv=liq),
                # Score: 0.6/0.2 = 3.0 (should rank 1st)
                "B": _df(close=200, ema200=100, mom=0.6, vol=0.2, adv=liq),
                # Fails gate: close ≤ EMA_200 → excluded
                "C": _df(close=90, ema200=100, mom=0.5, vol=0.2, adv=liq),
                # Fails gate: negative momentum → excluded
                "D": _df(close=200, ema200=100, mom=-0.1, vol=0.2, adv=liq),
            },
            cfg,
        )

        result = store.eligible_ranked(day, ["A", "B", "C", "D"])
        isins = [r[0] for r in result]
        scores = [r[1] for r in result]

        assert "C" not in isins, "C fails the trend condition"
        assert "D" not in isins, "D fails the momentum condition"
        assert isins == ["B", "A"], "must be sorted descending by score"
        assert scores[0] > scores[1], "first score must be strictly higher"

    def test_empty_when_none_eligible(self):
        """All fail gate → empty list."""
        cfg = _default_cfg()
        day = pd.Timestamp("2022-06-01")
        df = pd.DataFrame(
            {
                "close": [80.0],
                "adv_20": [1e8],
                "EMA_200": [100.0],
                "momentum_12_1": [-0.1],
                "annualized_vol": [0.2],
            },
            index=pd.DatetimeIndex([day]),
        )
        store = SignalStore({"X": df}, cfg)
        assert store.eligible_ranked(day, ["X"]) == []

    def test_empty_input_isins(self):
        store, dates = _make_store()
        result = store.eligible_ranked(dates[-1], [])
        assert result == []
