"""V4.0 rework battery — `00` Amendment 1 (§14): concentration cap + stable universe.

Amendment 1 is a **return-blind structural** rework (no return computed ⇒ K stays 0):
  - A/B: `n_max` (returns-blind tail cap, 371) → `target_positions = 15`, a BINDING
    concentration cap = slot cap AND sizing divisor.
  - C: `adv_20` promoted from a rare-day tiebreak to the PRIMARY top-N selector.
  - D: universe narrowed to a `U=200` `stable_universe`, AND-ed into the entry scan
    beneath the retained ₹5cr tradeability floor.
  - E: `starting_capital = ₹3.5L` (real spare capital).

Each test states the failure it guards (Rule 9). No live API, no return number.
"""

from __future__ import annotations

import types

import numpy as np
import pandas as pd

from app.backtest_v2.portfolio import Portfolio
from app.swing_v4.config import SwingConfig
from app.swing_v4.engine import SwingLoopState, _scan_entries, build_context


# --------------------------------------------------------------------------- #
# §14 B/E — the frozen Amendment-1 SwingConfig defaults.                       #
# Guards: a silent drift of the binding cap / capital / universe back to the   #
# retired pre-amendment values (n_max=371 / ₹10L / full-universe).             #
# --------------------------------------------------------------------------- #
def test_amendment1_config_defaults():
    cfg = SwingConfig()
    assert cfg.target_positions == 15, "binding concentration cap (§14 B)"
    assert not hasattr(cfg, "n_max"), "the retired n_max field must be gone (§14 A)"
    assert cfg.starting_capital == 350_000.0, "real spare capital (§14 E)"
    assert cfg.universe_mode == "stable", "frozen candidate universe (§14 D)"
    assert cfg.universe_size_U == 200, "U=200 Nifty200 liquidity proxy (§14 D)"


# --------------------------------------------------------------------------- #
# §14 D — the stable_universe mask is built only in "stable" mode.            #
# Guards: the mask silently not wiring in (entries would hit the full          #
# universe), or the "floor" escape hatch silently building one.               #
# --------------------------------------------------------------------------- #
def _flat_frame(isin: str, periods: int = 30) -> pd.DataFrame:
    idx = pd.bdate_range("2021-01-04", periods=periods)
    close = np.linspace(100.0, 110.0, periods)
    return pd.DataFrame(
        {
            "isin": [isin] * periods,
            "symbol": [isin[-3:]] * periods,
            "date": idx,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "adv_20": [1e8] * periods,
        }
    )


def test_universe_mask_built_only_in_stable_mode():
    df = _flat_frame("INE000A01001")
    regime = types.SimpleNamespace(deployable_fraction=lambda d: 1.0)

    cfg_stable = SwingConfig(sma_long=5, universe_mode="stable")
    ctx_s, _ = build_context(df, cfg_stable, regime=regime)
    assert ctx_s.universe_mask is not None, "stable mode must build the mask (§14 D)"

    cfg_floor = SwingConfig(sma_long=5, universe_mode="floor")
    ctx_f, _ = build_context(df, cfg_floor, regime=regime)
    assert ctx_f.universe_mask is None, "floor mode must leave the mask off"


# --------------------------------------------------------------------------- #
# Direct _scan_entries unit tests (mirror the _exit_breach fixture pattern):   #
# fake the mask + signal store so the entry gate is isolated from the 126-td   #
# stable_universe warmup (exercised end-to-end via the real mask elsewhere).   #
# --------------------------------------------------------------------------- #
class _FakeStore:
    """All names fire an entry signal; `row` returns the per-name adv_20."""

    def __init__(self, advs: dict[str, float]) -> None:
        self._advs = advs

    def entry_signal(self, day, iid) -> bool:  # noqa: ANN001
        return iid in self._advs

    def row(self, day, iid):  # noqa: ANN001
        return pd.Series({"adv_20": self._advs[iid]})


class _FakeMask:
    def __init__(self, members: set[str]) -> None:
        self._members = members

    def is_member(self, day, iid) -> bool:  # noqa: ANN001
        return iid in self._members


def _scan_ctx(cfg, advs, members, close):
    day = pd.Timestamp("2021-06-01")
    ctx = types.SimpleNamespace(
        config=cfg,
        membership={iid: {day} for iid in advs},
        signal_store=_FakeStore(advs),
        sym_map={iid: iid for iid in advs},
        universe_mask=_FakeMask(members) if members is not None else None,
    )
    state = SwingLoopState(
        portfolio=Portfolio(cash=cfg.starting_capital), pending_fills=[], anchors={}
    )
    _scan_entries(ctx, state, day, day.date(), 1.0, close)
    return {f.isin for f in state.pending_fills if f.side == "buy"}


# §14 D — a name that fires + is liquid but is OUTSIDE the stable universe is NOT bought.
# Guards: the universe mask not being AND-ed into the entry scan.
def test_stable_universe_mask_suppresses_out_of_universe_entry():
    cfg = SwingConfig(target_positions=5, starting_capital=1_000_000.0)
    advs = {"A": 3e8, "B": 2e8, "C": 1e8}
    close = {"A": 100.0, "B": 100.0, "C": 100.0}
    bought = _scan_ctx(cfg, advs, members={"A", "B"}, close=close)
    assert bought == {"A", "B"}, (
        "C fires + is liquid but is not in the U-universe (§14 D)"
    )


# §14 C — when more names fire than free slots, hold the top-`target_positions` by adv_20.
# Guards: adv_20 staying a mere tiebreak (selecting an arbitrary subset, not the top-N).
def test_target_positions_top_n_adv_selector_binds():
    cfg = SwingConfig(target_positions=2, starting_capital=1_000_000.0)
    advs = {"A": 1e8, "B": 3e8, "C": 2e8}  # B most liquid, then C, then A
    close = {"A": 100.0, "B": 100.0, "C": 100.0}
    bought = _scan_ctx(cfg, advs, members={"A", "B", "C"}, close=close)
    assert bought == {"B", "C"}, "top-2 by adv_20 (the primary selector, §14 C)"
