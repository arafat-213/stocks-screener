"""V4.0a fidelity & no-lookahead battery (v4/02 §5 items 1, 6, 7 + the
indicator/regime no-lookahead proof and a hand-built regime 0–5 fixture).

Each test states the failure it guards (Rule 9 — encode WHY). No live API: every
series here is a hand-built fixture (CLAUDE.md §5).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.swing_v4 import indicators as ind
from app.swing_v4.config import SwingConfig
from app.swing_v4.regime import RegimeScore


def _days(n: int, start: str = "2020-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


# --------------------------------------------------------------------------- #
# §5.1 — Indicator parity against hand figures                                 #
# Guards: a silent indicator-definition drift.                                 #
# --------------------------------------------------------------------------- #
def test_ema_matches_hand_figures():
    # span=3 ⇒ alpha=0.5; ewm(adjust=False): e0=x0, e_t=0.5 x_t + 0.5 e_{t-1}.
    close = pd.Series([10.0, 20.0, 30.0, 40.0], index=_days(4))
    got = ind.ema(close, 3)
    np.testing.assert_allclose(got.to_numpy(), [10.0, 15.0, 22.5, 31.25])


def test_sma_min_periods_no_partial_window():
    close = pd.Series([10.0, 20.0, 30.0, 40.0], index=_days(4))
    got = ind.sma(close, 3)
    assert got.isna().tolist() == [True, True, False, False]  # no partial-window value
    np.testing.assert_allclose(got.dropna().to_numpy(), [20.0, 30.0])


def test_atr_wilder_matches_hand_figures():
    # TR = [2,3,1,3,3]; n=3 ⇒ ATR[2]=mean(2,3,1)=2.0, then Wilder recursion.
    idx = _days(5)
    high = pd.Series([10.0, 12.0, 11.0, 13.0, 15.0], index=idx)
    low = pd.Series([8.0, 9.0, 10.0, 11.0, 12.0], index=idx)
    close = pd.Series([9.0, 11.0, 10.0, 12.0, 14.0], index=idx)
    atr = ind.atr_wilder(high, low, close, 3)
    assert atr.iloc[0:2].isna().all()  # warmup
    np.testing.assert_allclose(
        atr.iloc[2:].to_numpy(), [2.0, 7.0 / 3.0, (7.0 / 3.0 * 2 + 3) / 3], rtol=1e-12
    )


def test_macd_composition_against_independent_loop():
    # Independent reference: explicit recursive EMA loop (different code path than
    # the production pandas ewm) — guards the MACD = EMA_fast − EMA_slow,
    # signal = EMA_signal(line) composition.
    close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], index=_days(7))

    def ref_ema(vals, n):
        a = 2.0 / (n + 1)
        out, prev = [], None
        for v in vals:
            prev = v if prev is None else a * v + (1 - a) * prev
            out.append(prev)
        return np.array(out)

    fast, slow, sig = 2, 3, 2
    ref_line = ref_ema(close.to_numpy(), fast) - ref_ema(close.to_numpy(), slow)
    ref_signal = ref_ema(ref_line, sig)
    line, signal = ind.macd(close, fast, slow, sig)
    np.testing.assert_allclose(line.to_numpy(), ref_line, rtol=1e-12)
    np.testing.assert_allclose(signal.to_numpy(), ref_signal, rtol=1e-12)


# --------------------------------------------------------------------------- #
# §5.6 — Completed-weeks-only                                                  #
# Guards: a partial (in-progress) week's MACD leaking the future into mid-week.#
# --------------------------------------------------------------------------- #
def test_weekly_macd_completed_weeks_only():
    # 4 full weeks of business days + a partial 5th week (Mon..Wed).
    idx = pd.bdate_range("2021-01-04", periods=23)  # Mon → through a partial week
    close = pd.Series(np.linspace(100.0, 122.0, len(idx)), index=idx)
    w = ind.weekly_macd_line(close, 2, 3, 2)

    # Pick a mid-week (Wednesday) day inside the in-progress final week.
    wednesday = idx[-1]  # last bar is mid-week (partial week)
    assert wednesday.weekday() == 2  # sanity: it is a Wednesday
    baseline = w.loc[wednesday]

    # Mutate ONLY the in-progress week's later (future) bars; the value carried on
    # this mid-week day must not move (it reflects the last *completed* Friday).
    close2 = close.copy()
    close2.iloc[-1] = 9999.0  # corrupt the still-open week
    w2 = ind.weekly_macd_line(close2, 2, 3, 2)
    assert w2.loc[wednesday] == pytest.approx(baseline)


# --------------------------------------------------------------------------- #
# Regime hand-built 0–5 fixture (V4.0a "Done": reproduce a hand-built score)   #
# + §5.7 missing-VIX scores condition 5 = 0 (no forward-fill).                  #
# --------------------------------------------------------------------------- #
def _regime_fixture():
    idx = _days(6)
    # Small DMA windows so a tiny fixture exercises conditions 1 & 2.
    cfg = SwingConfig(regime_dma_long=3, regime_dma_short=2)
    price = pd.Series([100.0, 102.0, 104.0, 106.0, 108.0, 110.0], index=idx)
    mi = pd.DataFrame(
        {
            "date": idx,
            "liq_breadth_pct": [70.0, 50.0, 65.0, 80.0, 90.0, 30.0],
            "liq_ad_ratio": [1.2, 0.8, 1.5, 2.0, 0.5, 1.1],
            "india_vix": [15.0, 25.0, np.nan, 18.0, 12.0, 19.0],
        }
    )
    return idx, price, mi, cfg


def test_regime_score_reproduces_hand_built_fixture():
    idx, price, mi, cfg = _regime_fixture()
    rs = RegimeScore(price, mi, cfg)
    got = [rs.score(d) for d in idx]
    # Hand-computed (see test docstring/comments): day2 = 4 (NOT 5) because its
    # VIX is missing ⇒ condition 5 scores 0 — the missing-VIX guard.
    assert got == [3, 0, 4, 5, 4, 4]
    frac = [rs.deployable_fraction(d) for d in idx]
    assert frac == [0.5, 0.0, 1.0, 1.0, 1.0, 1.0]


def test_regime_missing_vix_does_not_forward_fill():
    idx, price, mi, cfg = _regime_fixture()
    rs = RegimeScore(price, mi, cfg)
    # day2 has all of conds 1–4 true; only the missing VIX keeps it at 4.
    assert rs.score(idx[2]) == 4


def test_regime_three_factor_ablation():
    idx, price, mi, cfg = _regime_fixture()
    rs = RegimeScore(price, mi, cfg, n_factors=3)
    # conds 1–3 only: [1,0,3,3,3,2] → frac [0.5,0.0,1.0,1.0,1.0,0.5].
    assert [rs.score(d) for d in idx] == [1, 0, 3, 3, 3, 2]
    assert [rs.deployable_fraction(d) for d in idx] == [
        0.5,
        0.0,
        1.0,
        1.0,
        1.0,
        0.5,
    ]


def test_regime_unknown_day_is_conservative():
    _, price, mi, cfg = _regime_fixture()
    rs = RegimeScore(price, mi, cfg)
    far = pd.Timestamp("2030-01-01")
    assert rs.score(far) == 0
    assert rs.deployable_fraction(far) == 0.0


# --------------------------------------------------------------------------- #
# §5.5 (indicator/regime scope) — future-bar corruption no-lookahead           #
# Guards: any forward leak in EMA/SMA/MACD/ATR/weekly-MACD or the regime DMAs.  #
# --------------------------------------------------------------------------- #
def test_no_lookahead_indicators_under_future_corruption():
    idx = _days(40)
    rng = np.random.default_rng(7)
    base = 100 + np.cumsum(rng.normal(0, 1, len(idx)))
    close = pd.Series(base, index=idx)
    high = close + 1.0
    low = close - 1.0

    cut = 25  # corrupt every bar AFTER index `cut`
    funcs = {
        "ema": lambda c: ind.ema(c, 5),
        "sma": lambda c: ind.sma(c, 5),
        "macd_line": lambda c: ind.macd(c, 12, 26, 9)[0],
        "macd_signal": lambda c: ind.macd(c, 12, 26, 9)[1],
        "weekly": lambda c: ind.weekly_macd_line(c, 12, 26, 9),
    }
    clean = {k: f(close) for k, f in funcs.items()}
    clean_atr = ind.atr_wilder(high, low, close, 14)

    close_c = close.copy()
    close_c.iloc[cut + 1 :] = np.nan
    high_c, low_c = high.copy(), low.copy()
    high_c.iloc[cut + 1 :] = np.nan
    low_c.iloc[cut + 1 :] = np.nan

    for k, f in funcs.items():
        corrupt = f(close_c)
        pd.testing.assert_series_equal(
            clean[k].iloc[: cut + 1], corrupt.iloc[: cut + 1], check_names=False
        )
    corrupt_atr = ind.atr_wilder(high_c, low_c, close_c, 14)
    pd.testing.assert_series_equal(
        clean_atr.iloc[: cut + 1], corrupt_atr.iloc[: cut + 1], check_names=False
    )


def test_no_lookahead_regime_under_future_corruption():
    idx = _days(40)
    cfg = SwingConfig(regime_dma_long=10, regime_dma_short=5)
    price = pd.Series(100 + np.arange(len(idx), dtype=float), index=idx)
    mi = pd.DataFrame(
        {
            "date": idx,
            "liq_breadth_pct": np.linspace(40, 90, len(idx)),
            "liq_ad_ratio": np.linspace(0.5, 2.0, len(idx)),
            "india_vix": np.linspace(30, 10, len(idx)),
        }
    )
    cut = 25
    clean = RegimeScore(price, mi, cfg)
    clean_scores = [clean.score(d) for d in idx[: cut + 1]]

    price_c = price.copy()
    price_c.iloc[cut + 1 :] = np.nan
    mi_c = mi.copy()
    mi_c.loc[cut + 1 :, ["liq_breadth_pct", "liq_ad_ratio", "india_vix"]] = np.nan
    corrupt = RegimeScore(price_c, mi_c, cfg)
    corrupt_scores = [corrupt.score(d) for d in idx[: cut + 1]]
    assert clean_scores == corrupt_scores
