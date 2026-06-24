"""V4.0b fidelity & fill-discipline battery (v4/02 §5 items 2–5, 8–10).

Each test states the failure it guards (Rule 9 — encode WHY). No live API: every
series is a hand-built fixture and the regime is injected (CLAUDE.md §5).

The engine is exercised on tiny fixtures with SMALL indicator windows (set via
SwingConfig) so a ~40-bar series can drive SMA200-equivalent logic — the indicator
*math* is already parity-tested in V4.0a; here we test the engine's per-day ordering,
fill discipline, exit/entry wiring, whole-share accounting, and identity continuity.

V4.0b computes **no return number** (v4/02 §6) — these are mechanics/fidelity proofs.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2.portfolio import Portfolio
from app.backtest_v2.schemas import Position
from app.swing_v4.config import SwingConfig
from app.swing_v4.engine import (
    SwingLoopState,
    _exit_breach,
    _exit_reason,
    build_context,
    run,
    step_day,
)
from app.swing_v4.signals import precompute_swing_signals

ISIN = "INE000A01001"


class _FixedRegime:
    """Inject a constant deployable fraction so engine tests isolate entry/exit/fill
    logic from regime causality (the regime path is proven in V4.0a)."""

    def __init__(self, f: float) -> None:
        self._f = f

    def deployable_fraction(self, day) -> float:  # noqa: ANN001
        return self._f

    def score(self, day) -> int:  # noqa: ANN001
        return 5


def _small_cfg(**kw) -> SwingConfig:
    """Frozen-shape config with SMALL windows so a tiny fixture exercises every rule.

    ``universe_mode="floor"`` here: a 45-bar fixture can never satisfy the 126-td
    stable_universe warmup, so these engine-mechanics tests use the legacy ₹5cr-only
    universe. The stable_universe mask itself is exercised separately (test_v40d).
    """
    base = dict(
        sma_short=2,
        sma_mid=3,
        sma_long=5,
        ema_exit=4,
        atr_period=3,
        macd_fast=2,
        macd_slow=3,
        macd_signal=2,
        target_positions=5,
        starting_capital=1_000_000.0,
        universe_mode="floor",
    )
    base.update(kw)
    return SwingConfig(**base)


def _uptrend_dip(periods: int = 45) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """A gentle uptrend with one shallow dip — engineered to produce EXACTLY one
    daily-MACD bullish crossover that also satisfies the 3 trend conditions, i.e.
    exactly one valid entry day (verified by the test below)."""
    idx = pd.bdate_range("2021-01-04", periods=periods)
    base = np.linspace(100.0, 100.0 + periods, periods)
    dip = np.zeros(periods)
    dip[24:30] = [-3, -6, -7, -5, -2, 0]
    return idx, base + dip


def _frame(idx: pd.DatetimeIndex, close: np.ndarray, **overrides) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "isin": [ISIN] * len(idx),
            "symbol": ["AAA"] * len(idx),
            "date": idx,
            "open": close * 1.0,
            "high": close * 1.005,
            "low": close * 0.99,
            "close": close.astype(float),
            "adv_20": [1e8] * len(idx),
        }
    )
    for k, v in overrides.items():
        df[k] = v
    return df


# --------------------------------------------------------------------------- #
# §5.2 — Entry rule: 4 conditions AND-ed; crossover off-by-one.                #
# Guards: an AND collapsing to OR, or an off-by-one on the MACD crossover.     #
# --------------------------------------------------------------------------- #
def test_entry_all_four_true_queues_one_buy_next_open():
    cfg = _small_cfg()
    idx, close = _uptrend_dip()
    df = _frame(idx, close)

    store = precompute_swing_signals(df, cfg)
    entry_days = [d for d in idx if store.entry_signal(d, ISIN)]
    assert len(entry_days) == 1, (
        f"fixture must have exactly one entry day, got {entry_days}"
    )
    entry_day = entry_days[0]

    res = run(df, cfg, regime=_FixedRegime(1.0))
    buys = [f for f in res.fills_log if f.side == "buy"]
    assert len(buys) == 1, "exactly one entry → exactly one buy"
    # Fill discipline: the buy executes at the NEXT session's open (D close → D+1 open).
    next_session = idx[list(idx).index(entry_day) + 1]
    assert buys[0].date == next_session.date()


def test_entry_missing_one_condition_produces_no_buy():
    # Break cond2 (close > SMA200-equiv): shift the whole series below its own SMA5 by
    # making it strictly DECREASING — no bullish crossover + close never > the long MA.
    cfg = _small_cfg()
    idx, close = _uptrend_dip()
    falling = close[::-1].copy()  # reverse → downtrend
    df = _frame(idx, falling)

    store = precompute_swing_signals(df, cfg)
    assert not any(store.entry_signal(d, ISIN) for d in idx), "downtrend → no entry"
    res = run(df, cfg, regime=_FixedRegime(1.0))
    assert [f for f in res.fills_log if f.side == "buy"] == []


# --------------------------------------------------------------------------- #
# §5.3 — Type-3 ATR trail: anchor ratchets up, breach exits, anchor never down.#
# Guards: the trail anchoring on the intraday high (the v1 sin) or moving down. #
# --------------------------------------------------------------------------- #
def test_type3_trail_exit_and_anchor_monotonic():
    cfg = _small_cfg()
    idx, close = _uptrend_dip(periods=45)
    # Sharp multi-day drop at the end → Type-3 trail breach (not the floor).
    base_close = close.copy()
    base_close[40:] = [
        base_close[39],
        base_close[39] - 12,
        base_close[39] - 13,
        base_close[39] - 14,
        base_close[39] - 15,
    ]
    df = _frame(idx, base_close)

    ctx, cal = build_context(df, cfg, regime=_FixedRegime(1.0))
    state = SwingLoopState(
        portfolio=Portfolio(cash=cfg.starting_capital), pending_fills=[], anchors={}
    )
    anchor_seq: list[float] = []
    for d in cal:
        step_day(ctx, state, d)
        if ISIN in state.anchors:
            anchor_seq.append(state.anchors[ISIN])

    buys = [f for f in state.portfolio.fills_log if f.side == "buy"]
    sells = [f for f in state.portfolio.fills_log if f.side == "sell"]
    assert len(buys) == 1 and len(sells) == 1
    # V4.1 forensic exit_log: the one exit is recorded once, attributed to the trail
    # (not the floor). Guards: the diagnostic side-channel desyncing from the actual
    # sells (double-count, miss, or mislabel). exit_log records on D (decision close),
    # one row per queued exit.
    assert len(state.exit_log) == 1
    assert state.exit_log[0][1] == ISIN and state.exit_log[0][2] == "atr_trail"
    # Anchor is a high-water mark of CLOSES — strictly non-decreasing while held.
    assert all(anchor_seq[i] <= anchor_seq[i + 1] for i in range(len(anchor_seq) - 1))
    # Exit is the Type-3 trail, NOT the catastrophic floor (sell price well above floor).
    assert sells[0].price > buys[0].price * (1 - cfg.catastrophic_stop_pct / 100.0)


# --------------------------------------------------------------------------- #
# §5.4 — Catastrophic floor: a −25% close breach exits even when the (loose)   #
# Type-3 trail has NOT tightened. Guards: a gap-down slipping past the floor.   #
# --------------------------------------------------------------------------- #
def test_catastrophic_floor_fires_when_trail_is_loose():
    cfg = _small_cfg()
    pos = Position(
        isin=ISIN,
        symbol="AAA",
        shares=10,
        cost_basis=100.0,
        entry_date=date(2021, 2, 1),
        last_price=74.0,
    )

    class _WideAtrStore:
        # ATR=20 ⇒ 3×ATR=60 ⇒ trail level = anchor(100) − 60 = 40 (very loose).
        def row(self, d, iid):  # noqa: ANN001
            return pd.Series(
                {"atr20": 20.0, "ema_exit": 80.0, "exit_macd_cross_down": False}
            )

    import types

    state = SwingLoopState(
        portfolio=Portfolio(1e6), pending_fills=[], anchors={ISIN: 100.0}
    )
    day = pd.Timestamp("2021-02-10")

    # close=74: below the 75 floor, ABOVE the 40 trail level → only the floor fires.
    ctx = types.SimpleNamespace(config=cfg, signal_store=_WideAtrStore())
    assert _exit_breach(ctx, state, ISIN, pos, 74.0, day) is True

    # Same close with the floor DISABLED (pct=0) and the loose trail → no exit. Proves
    # the 74 exit above was the floor, not the trail, and that pct=0 disables the floor.
    cfg_no_floor = _small_cfg(catastrophic_stop_pct=0.0)
    ctx0 = types.SimpleNamespace(config=cfg_no_floor, signal_store=_WideAtrStore())
    assert _exit_breach(ctx0, state, ISIN, pos, 74.0, day) is False

    # V4.1 forensic instrumentation: _exit_breach is a thin bool wrapper over
    # _exit_reason, which must NAME the firing rule (catastrophic_floor here) while
    # staying byte-equivalent in its truthiness. Guards: the reason drifting from the
    # branch that fired, or the wrapper diverging from the predicate.
    assert _exit_reason(ctx, state, ISIN, pos, 74.0, day) == "catastrophic_floor"
    assert _exit_reason(ctx0, state, ISIN, pos, 74.0, day) is None
    assert _exit_breach(ctx, state, ISIN, pos, 74.0, day) == (
        _exit_reason(ctx, state, ISIN, pos, 74.0, day) is not None
    )


# --------------------------------------------------------------------------- #
# §5.5 — No-lookahead (future-bar corruption) over the ENGINE.                 #
# Guards: any forward leak in the engine's per-day decisions.                  #
# --------------------------------------------------------------------------- #
def test_no_lookahead_engine_under_future_corruption():
    cfg = _small_cfg()
    idx, close = _uptrend_dip(periods=45)
    df = _frame(idx, close)
    res_clean = run(df, cfg, regime=_FixedRegime(1.0))

    cut = 30  # corrupt every bar AFTER calendar index `cut` to a wild (finite) value
    close_c = close.copy()
    close_c[cut + 1 :] = 9999.0
    df_c = _frame(idx, close_c)
    res_c = run(df_c, cfg, regime=_FixedRegime(1.0))

    cut_date = idx[cut].date()
    # Every snapshot on/before the cut date must be byte-identical.
    clean_snaps = {s.date: s for s in res_clean.snapshots if s.date <= cut_date}
    corrupt_snaps = {s.date: s for s in res_c.snapshots if s.date <= cut_date}
    assert clean_snaps.keys() == corrupt_snaps.keys()
    for d in clean_snaps:
        assert clean_snaps[d] == corrupt_snaps[d]
    # Every fill EXECUTED on/before the cut date must be byte-identical (decisions made
    # on day ≤ cut depend only on bars ≤ cut). Fills on cut+1 may legitimately differ.
    clean_fills = [f for f in res_clean.fills_log if f.date <= cut_date]
    corrupt_fills = [f for f in res_c.fills_log if f.date <= cut_date]
    assert clean_fills == corrupt_fills


# --------------------------------------------------------------------------- #
# §5.8 — Whole-share + clamp-to-cash + equity identity every day.             #
# Guards: fractional-share fidelity drift and the implicit-leverage bug (11§13).#
# --------------------------------------------------------------------------- #
def test_whole_share_and_cash_conservation():
    cfg = _small_cfg()
    idx, close = _uptrend_dip()
    df = _frame(idx, close)
    res = run(df, cfg, regime=_FixedRegime(1.0), whole_shares=True)

    buys = [f for f in res.fills_log if f.side == "buy"]
    assert buys, "fixture should produce a buy"
    for f in res.fills_log:
        assert f.qty == float(int(f.qty)), "whole-share: every fill is an integer qty"
    for s in res.snapshots:
        assert abs(s.equity - (s.cash + s.invested_value)) < 1e-6  # identity holds
        assert s.cash >= -1e-6, "buys never drive cash negative (clamp-to-cash)"


def test_gross_never_exceeds_deployable_fraction():
    # Neutral regime (f=0.5): equal-weight sizing must keep gross ≤ 0.5 × equity.
    cfg = _small_cfg()
    idx, close = _uptrend_dip()
    df = _frame(idx, close)
    res = run(df, cfg, regime=_FixedRegime(0.5))
    for s in res.snapshots:
        if s.equity > 0:
            assert s.exposure <= 0.5 + 1e-6, "gross ≤ f × capital (00 §3.5)"


# --------------------------------------------------------------------------- #
# §5.9 — Fill discipline: a name bought at D+1 open is exit-eligible D+1 close. #
# Guards: a skipped first-day stop (the v2/11 §3e hard ordering invariant).     #
# --------------------------------------------------------------------------- #
def test_bought_name_is_exit_eligible_on_same_close():
    cfg = _small_cfg()
    idx, close = _uptrend_dip()
    df = _frame(idx, close)

    store = precompute_swing_signals(df, cfg)
    entry_day = [d for d in idx if store.entry_signal(d, ISIN)][0]
    buy_day = idx[list(idx).index(entry_day) + 1]
    bi = list(idx).index(buy_day)

    # Crash the CLOSE on the buy day to < 75% of its open → the floor must fire on the
    # SAME day the name is bought (cost basis set at apply-time, step 1 < step 4). Keep
    # the original open (the fill price / cost-basis anchor) so the drop is intraday.
    orig_open = close.copy()  # _frame sets open = close × 1.0
    close2 = close.copy()
    close2[bi] = orig_open[bi] * 0.70
    df2 = _frame(idx, close2, open=orig_open)

    res = run(df2, cfg, regime=_FixedRegime(1.0))
    buys = [f for f in res.fills_log if f.side == "buy"]
    sells = [f for f in res.fills_log if f.side == "sell"]
    assert len(buys) == 1 and len(sells) == 1
    assert buys[0].date == buy_day.date()
    # Exit decided on the buy day's close → executes the very next session (no skip).
    next_session = idx[bi + 1]
    assert sells[0].date == next_session.date()


# --------------------------------------------------------------------------- #
# §5.10 — Identity continuity across an instrument_id succession.              #
# Guards: a succession looking like exit+re-entry / a stranded ghost (06/07).  #
# --------------------------------------------------------------------------- #
def test_identity_continuity_across_succession():
    cfg = _small_cfg()
    idx, close = _uptrend_dip(periods=45)
    # Two date-disjoint legs (INE_A days 0..34, INE_B days 35..44) sharing one
    # chain-constant instrument_id (= root INE_A) — a face-value re-issue (06).
    rows = []
    for i, d in enumerate(idx):
        leg = "INE_A" if i < 35 else "INE_B"
        rows.append(
            {
                "isin": leg,
                "instrument_id": "INE_A",
                "symbol": "AAA",
                "date": d,
                "open": float(close[i]),
                "high": float(close[i]) * 1.005,
                "low": float(close[i]) * 0.99,
                "close": float(close[i]),
                "adv_20": 1e8,
            }
        )
    df = pd.DataFrame(rows)

    res = run(df, cfg, regime=_FixedRegime(1.0))
    # Every fill is keyed by the chain-constant instrument_id (never the raw leg ISIN),
    # so a position opened on leg A is carried THROUGH the leg boundary, not exited.
    assert all(f.isin == "INE_A" for f in res.fills_log)
    assert "INE_B" not in {f.isin for f in res.fills_log}
    # The single entry is NOT mirrored by a spurious sell at the A→B boundary day.
    buys = [f for f in res.fills_log if f.side == "buy"]
    boundary_day = idx[35].date()
    assert all(f.date != boundary_day for f in res.fills_log if f.side == "sell")
    assert len(buys) == 1
