"""v4/01 — market-internals derivation tests (breadth + A/D + India VIX).

Offline only — synthetic frames, a tmp root, no network (CLAUDE.md Rule 4 / §5).
Each test encodes WHY the behaviour matters (Rule 9), not just what it computes:
  * the split-day test fails the moment anyone diffs ``close_raw`` instead of the
    split-adjusted ``close`` (v1's data-layer sin);
  * the survivorship test fails if a name with no prior-day close is ever counted.
"""

import numpy as np
import pandas as pd
import pytest

from app.data.bhavcopy import market_internals as mi
from app.data.bhavcopy import store

D1 = pd.Timestamp("2020-01-01")
D2 = pd.Timestamp("2020-01-02")
D3 = pd.Timestamp("2020-01-03")

_LIQUID = 6e7  # > ₹5cr floor
_ILLIQUID = 1e7  # < ₹5cr floor


def _panel(rows: list[tuple]) -> pd.DataFrame:
    """rows = (isin, date, close, adv_20) → the minimal frame compute() reads."""
    return pd.DataFrame(rows, columns=["isin", "date", "close", "adv_20"])


def test_breadth_ad_exact_counts_and_survivorship():
    """Hand-checked counts over 3 ISINs × 3 days.

    A (liquid): 100 → 110 (up) → 105 (down).
    B (illiquid): 50 → 50 (flat) → 55 (up).
    C (liquid, NEW on D2): absent D1 → 200 (D2) → 190 (D3, down).
    C must be EXCLUDED on D2 (no prior-day close) — the survivorship guard.
    """
    df = _panel(
        [
            ("A", D1, 100.0, _LIQUID),
            ("A", D2, 110.0, _LIQUID),
            ("A", D3, 105.0, _LIQUID),
            ("B", D1, 50.0, _ILLIQUID),
            ("B", D2, 50.0, _ILLIQUID),
            ("B", D3, 55.0, _ILLIQUID),
            ("C", D2, 200.0, _LIQUID),
            ("C", D3, 190.0, _LIQUID),
        ]
    )
    out = mi.compute_market_internals(df).set_index("date")

    # D1 — no prior day: nothing counted (explicit warmup edge).
    assert out.loc[D1, "total"] == 0
    assert np.isnan(out.loc[D1, "breadth_pct"])

    # D2 — A up, B flat; C excluded (new listing, no prior). decliners == 0.
    assert (
        out.loc[D2, "advancers"],
        out.loc[D2, "decliners"],
        out.loc[D2, "unchanged"],
    ) == (1, 0, 1)
    assert out.loc[D2, "total"] == 2  # C not counted → 2, not 3 (survivorship)
    assert out.loc[D2, "breadth_pct"] == pytest.approx(100.0)
    assert out.loc[D2, "ad_ratio"] == pytest.approx(
        1.0
    )  # decliners==0 → adv/1 sentinel

    # D3 — B up; A, C down.
    assert (out.loc[D3, "advancers"], out.loc[D3, "decliners"]) == (1, 2)
    assert out.loc[D3, "total"] == 3
    assert out.loc[D3, "breadth_pct"] == pytest.approx(100 / 3)
    assert out.loc[D3, "ad_ratio"] == pytest.approx(0.5)


def test_liquid_subset_gates_on_adv20_floor():
    """The liquid subset counts only names with adv_20 >= ₹5cr as of the day.

    Same panel as above: B is illiquid, so it never enters the liq_* counts.
    """
    df = _panel(
        [
            ("A", D1, 100.0, _LIQUID),
            ("A", D2, 110.0, _LIQUID),
            ("A", D3, 105.0, _LIQUID),
            ("B", D1, 50.0, _ILLIQUID),
            ("B", D2, 50.0, _ILLIQUID),
            ("B", D3, 55.0, _ILLIQUID),
            ("C", D2, 200.0, _LIQUID),
            ("C", D3, 190.0, _LIQUID),
        ]
    )
    out = mi.compute_market_internals(df).set_index("date")

    # D2: only A (up, liquid) counted; B's flat is dropped (illiquid).
    assert (out.loc[D2, "liq_advancers"], out.loc[D2, "liq_decliners"]) == (1, 0)
    assert out.loc[D2, "liq_total"] == 1
    # D3: A and C down (liquid); B's up dropped (illiquid) → breadth 0%.
    assert (out.loc[D3, "liq_advancers"], out.loc[D3, "liq_decliners"]) == (0, 2)
    assert out.loc[D3, "liq_breadth_pct"] == pytest.approx(0.0)


def test_split_adjusted_close_is_not_a_phantom_decliner():
    """REGRESSION (v1's sin): a back-adjusted split must NOT count as a decline.

    ISIN D's raw close cliffs 500 → 101 across a split, but the split-adjusted
    ``close`` is continuous (100 → 101, a genuine +1 advance). compute() diffs the
    ADJUSTED close, so D is an advancer. This test FAILS if anyone diffs ``close_raw``
    — which would record a phantom −80% decliner. That is exactly the corporate-action
    data-layer trap that biased every v1 number.
    """
    df = _panel([("D", D1, 100.0, _LIQUID), ("D", D2, 101.0, _LIQUID)])
    out = mi.compute_market_internals(df).set_index("date")
    assert out.loc[D2, "advancers"] == 1
    assert out.loc[D2, "decliners"] == 0  # close_raw would have made this 1


def test_vix_left_join_missing_day_is_nan_not_filled():
    """India VIX aligns by date; a trading day with no VIX is NaN, never filled (01 §3)."""
    df = _panel(
        [
            ("A", D1, 100.0, _LIQUID),
            ("A", D2, 110.0, _LIQUID),
            ("A", D3, 105.0, _LIQUID),
        ]
    )
    vix = pd.DataFrame({"date": [D1, D3], "india_vix": [15.0, 22.0]})  # D2 absent
    out = mi.compute_market_internals(df, vix_series=vix).set_index("date")
    assert out.loc[D1, "india_vix"] == pytest.approx(15.0)
    assert np.isnan(out.loc[D2, "india_vix"])  # surfaced, not forward-filled to 15
    assert out.loc[D3, "india_vix"] == pytest.approx(22.0)


def test_vix_none_yields_all_nan_column():
    """No VIX series ⇒ india_vix all-NaN (the 3-factor tier still works — 01 §0)."""
    df = _panel([("A", D1, 100.0, _LIQUID), ("A", D2, 110.0, _LIQUID)])
    out = mi.compute_market_internals(df)
    assert out["india_vix"].isna().all()


def test_empty_input_returns_empty_schema():
    out = mi.compute_market_internals(
        pd.DataFrame(columns=["isin", "date", "close", "adv_20"])
    )
    assert list(out.columns) == mi.MARKET_INTERNALS_COLUMNS
    assert out.empty


def test_store_round_trip(tmp_path):
    """write_/read_market_internals preserve schema + values (mirrors the CA artifact)."""
    df = _panel(
        [
            ("A", D1, 100.0, _LIQUID),
            ("A", D2, 110.0, _LIQUID),
            ("A", D3, 105.0, _LIQUID),
            ("B", D1, 50.0, _ILLIQUID),
            ("B", D2, 50.0, _ILLIQUID),
            ("B", D3, 55.0, _ILLIQUID),
        ]
    )
    internals = mi.compute_market_internals(df)
    store.write_market_internals(internals, root=tmp_path)
    back = store.read_market_internals(root=tmp_path)

    assert list(back.columns) == list(store.MARKET_INTERNALS_SCHEMA)
    pd.testing.assert_frame_equal(
        back.reset_index(drop=True),
        internals.reset_index(drop=True),
        check_dtype=False,
    )


def test_read_missing_artifact_returns_empty(tmp_path):
    """A root with no market_internals.parquet reads back empty (not an error)."""
    back = store.read_market_internals(root=tmp_path)
    assert back.empty
    assert list(back.columns) == list(store.MARKET_INTERNALS_SCHEMA)
