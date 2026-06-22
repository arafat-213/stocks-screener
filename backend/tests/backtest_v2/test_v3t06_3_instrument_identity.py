"""
test_v3t06_3_instrument_identity.py — 06 T06.3 regression suite (offline, synthetic).

Encodes WHY the chain-constant `instrument_id` re-key matters (Rule 9), not just
WHAT it does. A face-value-split re-issue (`OLD → NEW`) is two ISINs trading on
strictly consecutive, date-disjoint ranges that share one `instrument_id`. Before
this fix the v2 sim/signal layer keyed everything on the raw `isin`, so (06 §1):

  (a) the NEW leg was momentum-blind for ~the lookback window — invisible to
      selection right when a high-momentum name most wants picking; and
  (b) a position held on the OLD leg became an unsellable **ghost** once it stopped
      trading (its sell fill found no open price → "fill dropped, position carried").

The fix is a single identity-resolution join (`identity.collapse_to_instrument_id`)
threaded through the signal/factor/engine primitives. These tests assert the three
T06.3 success gates:

  - gate (a): momentum is defined + continuous through the transition;
  - gate (b): a position held across a transition is sellable (no ghost) —
              the §2 ghost reproduced RED on raw isins, GREEN on instrument_id;
  - gate (c): a universe with no successions is byte-identical (the parity guard);

plus the `collapse_to_instrument_id` contract (no-op cases + fail-loud on overlap).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.costs import CostConfig, fill_cost
from app.backtest_v2.engine import run
from app.backtest_v2.identity import collapse_to_instrument_id
from app.backtest_v2.signals import precompute_signals

# ---------------------------------------------------------------------------
# Synthetic builders
# ---------------------------------------------------------------------------

OLD = "INE100A01011"
NEW = "INE100A01029"  # consecutive face-value-split re-issue of OLD


def _rows(
    isin: str,
    symbol: str,
    dates: pd.DatetimeIndex,
    closes: list[float],
    *,
    instrument_id: str | None,
    adv: float = 1e8,
) -> list[dict]:
    """Long-format rows for one leg. `instrument_id=None` ⇒ column omitted (the
    pre-T06.2 store shape that reproduces the ghost bug)."""
    rows = []
    for d, c in zip(dates, closes):
        row = {
            "isin": isin,
            "symbol": symbol,
            "date": d,
            "open": c,  # open == close → deterministic next-open fills
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "close_raw": c,
            "close_tr": c,
            "volume": 100_000,
            "traded_value": 1e9,
            "adv_20": adv,
            "adj_factor": 1.0,
            "tr_factor": 1.0,
            "series": "EQ",
        }
        if instrument_id is not None:
            row["instrument_id"] = instrument_id
        rows.append(row)
    return rows


def _chain_frame(
    *,
    stitched: bool,
    n_old: int = 300,
    n_new: int = 80,
) -> pd.DataFrame:
    """One succession chain: OLD rises (held), NEW falls on consecutive bdays.

    `stitched=True`  → both legs carry instrument_id = OLD (the T06.2 store).
    `stitched=False` → no instrument_id column (raw-isin pre-fix shape).
    """
    old_dates = pd.bdate_range("2022-01-03", periods=n_old)
    new_dates = pd.bdate_range(old_dates[-1] + BDay(1), periods=n_new)
    iid = OLD if stitched else None

    # OLD: 100 → 300 monotone up (positive 12-1 momentum, close > EMA_200).
    old_close = [100.0 + i * (200.0 / (n_old - 1)) for i in range(n_old)]
    # NEW: continues near OLD's last close then declines (momentum turns negative).
    new_close = [298.0 - j * (180.0 / (n_new - 1)) for j in range(n_new)]

    rows = _rows(OLD, "CHAIN", old_dates, old_close, instrument_id=iid)
    rows += _rows(
        NEW, "CHAIN", new_dates, new_close, instrument_id=OLD if stitched else None
    )
    return pd.DataFrame(rows), old_dates, new_dates


def _small_cfg(**kw) -> MomentumConfig:
    base = dict(
        target_positions=1,
        sell_rank_buffer=1,
        liquidity_floor_cr=1.0,
        momentum_lookback_days=10,
        momentum_skip_days=2,
        vol_lookback_days=8,
        max_position_pct=100.0,
        starting_capital=1_000_000.0,
        use_regime_overlay=False,
        catastrophic_stop_pct=0.0,  # isolate the rebalance gate-fail sell
        rebalance="monthly",
    )
    base.update(kw)
    return MomentumConfig(**base)


# ===========================================================================
# collapse_to_instrument_id — the resolution-join contract
# ===========================================================================


def test_collapse_noop_when_column_absent():
    """A pre-T06.2 frame (no instrument_id) is returned unchanged — the same object
    (so every legacy fixture / parity suite is byte-identical)."""
    df = pd.DataFrame({"isin": [OLD, NEW], "date": [1, 2], "close": [1.0, 2.0]})
    assert collapse_to_instrument_id(df) is df


def test_collapse_noop_when_no_succession():
    """instrument_id == isin for every row (no chain) ⇒ no-op (same object, no copy)."""
    df = pd.DataFrame({"isin": [OLD, NEW], "instrument_id": [OLD, NEW], "date": [1, 2]})
    assert collapse_to_instrument_id(df) is df


def test_collapse_relabels_chain_to_instrument_id():
    df = pd.DataFrame(
        {
            "isin": [OLD, NEW],
            "instrument_id": [OLD, OLD],
            "date": [pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-04")],
        }
    )
    out = collapse_to_instrument_id(df)
    assert out is not df  # did not mutate the caller's frame
    assert list(out["isin"]) == [OLD, OLD]
    assert list(df["isin"]) == [OLD, NEW]  # original untouched


def test_collapse_fails_loud_on_overlapping_legs():
    """Two legs sharing a date would corrupt the concatenated series (06 §3 says
    legs are consecutive/disjoint) — fail loud rather than silently pick one."""
    same_day = pd.Timestamp("2022-01-03")
    df = pd.DataFrame(
        {"isin": [OLD, NEW], "instrument_id": [OLD, OLD], "date": [same_day, same_day]}
    )
    try:
        collapse_to_instrument_id(df)
        assert False, "expected ValueError on overlapping (instrument_id, date) rows"
    except ValueError as e:
        assert "date-disjoint" in str(e)


# ===========================================================================
# Gate (a) — momentum defined + continuous through the transition
# ===========================================================================


def test_momentum_continuous_across_succession():
    """On the NEW leg shortly after the transition, momentum_12_1 is DEFINED when the
    chain is stitched (history flows from OLD) — and NaN when it is not (the bug)."""
    cfg = _small_cfg()
    stitched_df, _old, new_dates = _chain_frame(stitched=True, n_old=20, n_new=10)
    broken_df, _, _ = _chain_frame(stitched=False, n_old=20, n_new=10)

    # A date only 3 trading days into the NEW leg: alone (<12 rows) momentum is
    # undefined; concatenated onto OLD (position 23) it is defined.
    probe = new_dates[3]

    store_ok = precompute_signals(stitched_df, cfg)
    # Identity collapsed to instrument_id: the chain reads back under OLD only.
    assert OLD in store_ok._data and NEW not in store_ok._data
    mom_ok = store_ok._data[OLD].loc[probe, "momentum_12_1"]
    assert not math.isnan(mom_ok), "stitched chain must have continuous momentum"

    store_broken = precompute_signals(broken_df, cfg)
    # Raw isins: NEW is its own short instrument → momentum-blind right after the split.
    assert NEW in store_broken._data
    mom_broken = store_broken._data[NEW].loc[probe, "momentum_12_1"]
    assert math.isnan(mom_broken), "raw-isin NEW leg is momentum-blind (the bug)"


# ===========================================================================
# Gate (b) — held position is sellable across the transition (ghost red→green)
# ===========================================================================


def test_held_position_sellable_across_succession_green():
    """Stitched: the name held into the split is exited cleanly on a later rebalance
    (sell fills at the live NEW leg's open) — no carried, unsellable ghost."""
    cfg = _small_cfg()
    df, _old, _new = _chain_frame(stitched=True)

    result = run(df, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    # It was actually bought (otherwise the test proves nothing) ...
    assert any(f.side == "buy" for f in result.fills_log)
    # ... and then sold once momentum turned negative on the NEW leg.
    sells = [f for f in result.fills_log if f.side == "sell"]
    assert sells, "the held chain name should have been sold after the split"
    # No surviving position: identity collapsed to OLD, fully exited, no ghost.
    final = result.snapshots[-1]
    assert final.n_positions == 0


def test_held_position_becomes_ghost_on_raw_isins_red():
    """Un-stitched (raw isins): the OLD-leg position cannot be sold after the split
    (no OLD prices → fill dropped) and is carried forever — the §2 ghost. This is the
    failure the green test above proves fixed."""
    cfg = _small_cfg()
    df, _old, _new = _chain_frame(stitched=False)

    result = run(df, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    assert any(f.side == "buy" for f in result.fills_log)
    # The position is still open at the end (frozen ghost) ...
    final = result.snapshots[-1]
    assert final.n_positions == 1
    # ... and that ghost is the OLD leg, whose suspension was logged (no price post-split).
    assert OLD in result.suspension_log


# ===========================================================================
# Gate (c) — no-succession universe is byte-identical (the parity guard)
# ===========================================================================


def _walk_frame(seed: int = 7, n_days: int = 380, n_names: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n_days)
    rows = []
    for k in range(n_names):
        isin = f"INE{k:03d}Z01011"
        price = 100.0
        for i, d in enumerate(dates):
            price = max(price * (1 + rng.normal(0.0006, 0.014)), 0.01)
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "date": d,
                    "open": price * 0.999,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "close_raw": price,
                    "close_tr": price * 1.0005**i,
                    "volume": 100_000,
                    "traded_value": 1e9,
                    "adv_20": 1e8,
                    "adj_factor": 1.0,
                    "tr_factor": 1.0005**i,
                    "series": "EQ",
                }
            )
    return pd.DataFrame(rows)


def test_no_succession_run_is_byte_identical():
    """Adding instrument_id == isin (no chain) must not change a single fill or
    equity point — the collapse is a no-op for non-succession universes (gate c)."""
    cfg = _small_cfg(target_positions=2, sell_rank_buffer=3)

    base = _walk_frame()
    with_id = base.copy()
    with_id["instrument_id"] = with_id["isin"]

    r_base = run(base, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())
    r_id = run(with_id, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    eq_base = [s.equity for s in r_base.snapshots]
    eq_id = [s.equity for s in r_id.snapshots]
    assert eq_base == eq_id, "equity curve diverged — collapse was not a no-op"
    assert len(r_base.fills_log) == len(r_id.fills_log)
    for a, b in zip(r_base.fills_log, r_id.fills_log):
        assert (a.isin, a.side, a.date) == (b.isin, b.side, b.date)
        assert a.qty == b.qty and a.price == b.price
