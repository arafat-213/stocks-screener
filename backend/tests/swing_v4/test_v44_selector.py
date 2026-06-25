"""V4.4 — return-informed selector (`specs/v4/04`).

`04` adds a budgeted selector axis carrying its own K: when more names fire than the
15 slots, choose which to hold by a return-informed rank instead of liquidity.

  - "mom" (candidate): trailing `selector_lookback`-td return, desc.
  - "rs"  (comparator): mom − Nifty 50 trailing return. The Nifty term is one per-day
    constant, so it cannot change the cross-sectional order ⇒ rs ≡ mom as a selector
    (`04` §3). These tests LOCK that identity (so a future reader does not mistake rs for
    independent information) and the no-lookahead / thin-data / tiebreak guarantees.

Each test states the failure it guards (Rule 9). No live API, no return number.
"""

from __future__ import annotations

import types

import numpy as np
import pandas as pd

from app.backtest_v2.portfolio import Portfolio
from app.swing_v4.config import SwingConfig
from app.swing_v4.engine import SwingLoopState, _scan_entries
from app.swing_v4.regime import RegimeScore
from app.swing_v4.signals import precompute_swing_signals


# --------------------------------------------------------------------------- #
# 1. The momentum column is point-in-time (04 §9): a FUTURE bar must not change #
#    row D's rank. Guards a lookahead leak in the selector ranker.             #
# --------------------------------------------------------------------------- #
def _one_name_frame(isin: str, closes: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2021-01-04", periods=len(closes))
    c = np.array(closes, dtype=float)
    return pd.DataFrame(
        {
            "isin": [isin] * len(closes),
            "symbol": ["SYM"] * len(closes),
            "date": idx,
            "open": c,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "adv_20": [1e8] * len(closes),
        }
    )


def test_mom_column_no_lookahead():
    cfg = SwingConfig(selector_lookback=5)
    closes = [100 + i for i in range(20)]
    iid = "INE000A01001"
    full = precompute_swing_signals(_one_name_frame(iid, closes), cfg)
    d = pd.Timestamp("2021-01-15")  # an interior date with a full lookback
    mom_full = full.row(d, iid)["mom"]

    # Truncate everything AFTER d so d is the last bar — row d's momentum must be
    # unchanged (it references only bars ≤ d).
    n = pd.bdate_range("2021-01-04", periods=20).get_loc(d) + 1
    trunc = precompute_swing_signals(_one_name_frame(iid, closes[:n]), cfg)
    mom_trunc = trunc.row(d, iid)["mom"]
    assert mom_full == mom_trunc, "future bars must not change row D's momentum rank"


# --------------------------------------------------------------------------- #
# Direct _scan_entries harness (mirrors test_v40d_rework): isolate the gate.   #
# --------------------------------------------------------------------------- #
class _FakeStore:
    """All names fire; `row` returns each name's adv_20 + mom (mom=None ⇒ NaN)."""

    def __init__(self, advs: dict[str, float], moms: dict[str, float | None]) -> None:
        self._advs = advs
        self._moms = moms

    def entry_signal(self, day, iid) -> bool:  # noqa: ANN001
        return iid in self._advs

    def row(self, day, iid):  # noqa: ANN001
        mom = self._moms.get(iid)
        return pd.Series(
            {"adv_20": self._advs[iid], "mom": float("nan") if mom is None else mom}
        )


def _scan(cfg, advs, moms, close, *, nifty_mom=None):
    day = pd.Timestamp("2021-06-01")
    ctx = types.SimpleNamespace(
        config=cfg,
        membership={iid: {day} for iid in advs},
        signal_store=_FakeStore(advs, moms),
        sym_map={iid: iid for iid in advs},
        universe_mask=None,
        nifty_mom=nifty_mom,
    )
    state = SwingLoopState(
        portfolio=Portfolio(cash=cfg.starting_capital), pending_fills=[], anchors={}
    )
    _scan_entries(ctx, state, day, day.date(), 1.0, close)
    return {f.isin for f in state.pending_fills if f.side == "buy"}


# 2. mom selector keeps the strongest-trend names, NOT the most liquid (the whole point).
#    Guards mom silently falling back to the adv ranking.
def test_mom_selector_picks_highest_momentum():
    cfg = SwingConfig(selector="mom", target_positions=2, starting_capital=1_000_000.0)
    advs = {"A": 9e8, "B": 1e8, "C": 5e8}  # A most liquid
    moms = {"A": 0.01, "B": 0.50, "C": 0.30}  # B/C strongest trend
    close = {k: 100.0 for k in advs}
    assert _scan(cfg, advs, moms, close) == {"B", "C"}, "top-2 by momentum, not adv"


# 3. A name without a full lookback (mom NaN) sorts LAST — never picked over a name with
#    a real momentum reading (no thin-data preference, 04 §3/§9).
def test_mom_thin_history_sorts_last():
    cfg = SwingConfig(selector="mom", target_positions=2, starting_capital=1_000_000.0)
    advs = {"A": 9e8, "B": 1e8, "C": 5e8}
    moms = {"A": None, "B": 0.10, "C": 0.20}  # A has no lookback
    close = {k: 100.0 for k in advs}
    assert _scan(cfg, advs, moms, close) == {"B", "C"}, "NaN-mom name sorts last"


# 4. Equal momentum → adv_20 breaks the tie (the frozen neutral tiebreak, 04 §3).
def test_mom_ties_break_on_adv():
    cfg = SwingConfig(selector="mom", target_positions=2, starting_capital=1_000_000.0)
    advs = {"A": 1e8, "B": 3e8, "C": 2e8}  # B then C most liquid
    moms = {"A": 0.20, "B": 0.20, "C": 0.20}  # all tied on momentum
    close = {k: 100.0 for k in advs}
    assert _scan(cfg, advs, moms, close) == {"B", "C"}, "tie → top-2 by adv_20"


# 5. THE §3 IDENTITY: rs (mom − per-day Nifty constant) selects the SAME names as mom,
#    for ANY benchmark value. Guards a future reader treating rs as new information.
def test_rs_identical_to_mom():
    advs = {"A": 9e8, "B": 1e8, "C": 5e8, "D": 4e8}
    moms = {"A": 0.05, "B": 0.40, "C": 0.30, "D": -0.10}
    close = {k: 100.0 for k in advs}
    day = pd.Timestamp("2021-06-01")
    mom_book = _scan(
        SwingConfig(selector="mom", target_positions=2, starting_capital=1_000_000.0),
        advs,
        moms,
        close,
    )
    for bench in (-0.5, 0.0, 0.37, 5.0):  # any uniform shift leaves the order intact
        rs_book = _scan(
            SwingConfig(
                selector="rs", target_positions=2, starting_capital=1_000_000.0
            ),
            advs,
            moms,
            close,
            nifty_mom={day: bench},
        )
        assert rs_book == mom_book, f"rs must equal mom for bench={bench} (04 §3)"


# 6. rs without the Nifty trailing return fails LOUD (Rule 12) — never silently degrades.
def test_rs_requires_nifty_mom():
    cfg = SwingConfig(selector="rs", target_positions=2, starting_capital=1_000_000.0)
    advs = {"A": 1e8, "B": 2e8}
    moms = {"A": 0.1, "B": 0.2}
    close = {k: 100.0 for k in advs}
    try:
        _scan(cfg, advs, moms, close, nifty_mom=None)
    except ValueError as e:
        assert "rs" in str(e)
    else:
        raise AssertionError("rs with no nifty_mom must raise (04 §3)")


# 7. mom is deterministic — same inputs, same book (no RNG path, unlike "random").
def test_mom_selector_deterministic():
    cfg = SwingConfig(selector="mom", target_positions=2, starting_capital=1_000_000.0)
    advs = {"A": 9e8, "B": 1e8, "C": 5e8}
    moms = {"A": 0.4, "B": 0.1, "C": 0.3}
    close = {k: 100.0 for k in advs}
    assert _scan(cfg, advs, moms, close) == _scan(cfg, advs, moms, close)


# --------------------------------------------------------------------------- #
# 8. §5 deployment diagnostic: neutral_fraction lifts the Neutral bucket only  #
#    (Bear 0 / Bull 1 unchanged). Guards the D_more knob leaking into the      #
#    candidate (default 0.5) or perturbing the extreme buckets.                #
# --------------------------------------------------------------------------- #
def _regime_inputs():
    idx = pd.bdate_range("2021-01-04", periods=260)
    # Nifty rising → c1/c2 true (score floor 2 = Neutral); internals tune 3/4/5.
    price = pd.Series(np.linspace(100.0, 200.0, len(idx)), index=idx)
    mi = pd.DataFrame(
        {
            "date": idx,
            "liq_breadth_pct": [70.0] * len(idx),  # c3 true → score 3 (Neutral bucket)
            "liq_ad_ratio": [0.5] * len(idx),  # c4 false
            "india_vix": [30.0] * len(idx),  # c5 false → caps at score 3
        }
    )
    return price, mi


def test_neutral_fraction_lifts_only_neutral_bucket():
    price, mi = _regime_inputs()
    d = pd.Timestamp("2021-12-01")  # warmed-up Neutral day (score 2–3)
    base = RegimeScore(price, mi)
    more = RegimeScore(price, mi, neutral_fraction=0.75)
    assert 2 <= base.score(d) <= 3, "fixture must land in the Neutral bucket"
    assert base.deployable_fraction(d) == 0.5, "default Neutral f frozen at 0.5"
    assert more.deployable_fraction(d) == 0.75, "D_more lifts Neutral to 0.75 (04 §5)"
