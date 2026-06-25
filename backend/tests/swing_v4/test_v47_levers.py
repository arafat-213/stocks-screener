"""V4.7 turnover-lever battery (v4/05 §3.2 / §3.4 / §5 / §9).

The three new degrees of freedom added by `05` — weekly decision cadence, min-hold,
and re-entry cooldown — must each be (a) deterministic, (b) no-lookahead, and (c)
byte-identical to the locked V4.4 engine on their default values. Each test states the
failure it guards (Rule 9). No live API: every series is a hand-built fixture and the
regime is injected (CLAUDE.md §5).
"""

from __future__ import annotations

import types

import numpy as np
import pandas as pd

from app.backtest_v2.portfolio import Portfolio
from app.backtest_v2.schemas import Position
from app.swing_v4.config import SwingConfig
from app.swing_v4.engine import (
    SwingLoopState,
    _exit_reason,
    _past_min_hold,
    _scan_entries,
    _weekly_decision_days,
    build_context,
    run,
    step_day,
)

ISIN = "INE000A01001"


def _small_cfg(**kw) -> SwingConfig:
    """Frozen-shape config with SMALL windows (mirrors test_v40b) so a tiny fixture
    exercises every rule; floor universe so the 126-td stable warmup is not required."""
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


class _FixedRegime:
    def __init__(self, f: float) -> None:
        self._f = f

    def deployable_fraction(self, day) -> float:  # noqa: ANN001
        return self._f

    def score(self, day) -> int:  # noqa: ANN001
        return 5


def _uptrend_dip(periods: int = 45) -> tuple[pd.DatetimeIndex, np.ndarray]:
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
# 1. Decision-day map = the last trading day of each ISO week (05 §3.2).       #
#    Guards: off-by-one week grouping, or picking Monday instead of Friday.    #
# --------------------------------------------------------------------------- #
def test_weekly_decision_days_are_week_last_trading_day():
    cal = list(pd.bdate_range("2021-01-04", periods=20))  # 4 full Mon–Fri weeks
    days = _weekly_decision_days(cal)
    fridays = {ts for ts in cal if ts.weekday() == 4}
    assert days == fridays, "no holidays ⇒ every decision day is the week's Friday"

    # Drop a Friday (a holiday) → that week's decision day becomes the Thursday.
    holiday_cal = [ts for ts in cal if ts != pd.Timestamp("2021-01-08")]
    days2 = _weekly_decision_days(holiday_cal)
    assert pd.Timestamp("2021-01-07") in days2, "missing Friday ⇒ Thursday decides"
    assert pd.Timestamp("2021-01-08") not in days2


# --------------------------------------------------------------------------- #
# 2. Default cadence is byte-identical (05 §3.2 — additive default).          #
#    Guards: the weekly plumbing accidentally altering the daily path.        #
# --------------------------------------------------------------------------- #
def test_explicit_daily_is_byte_identical_to_default():
    idx, close = _uptrend_dip(periods=45)
    base_close = close.copy()
    base_close[40:] = [
        base_close[39],
        base_close[39] - 12,
        base_close[39] - 13,
        base_close[39] - 14,
        base_close[39] - 15,
    ]
    df = _frame(idx, base_close)
    res_default = run(df, _small_cfg(), regime=_FixedRegime(1.0), whole_shares=True)
    res_daily = run(
        df,
        _small_cfg(decision_cadence="daily"),
        regime=_FixedRegime(1.0),
        whole_shares=True,
    )
    assert res_default.fills_log == res_daily.fills_log
    assert res_default.snapshots == res_daily.snapshots


# --------------------------------------------------------------------------- #
# 3. Weekly cadence defers the CONFIGURED exit to a decision day; the floor    #
#    still fires daily (05 §3.2). Guards: a weekly run silently disabling the  #
#    catastrophic floor, or firing the trail mid-week.                         #
#                                                                              #
#    A held position is seeded directly (not entered via the scan) so the test #
#    isolates EXIT cadence from entry timing — under weekly the natural single #
#    entry day may not be a decision day, which is correct but off-topic here. #
# --------------------------------------------------------------------------- #
def _run_seeded(df: pd.DataFrame, cfg: SwingConfig, entry_idx: int):
    """Step the engine over `df`, injecting one held position at calendar[entry_idx]
    (cost basis + anchor = that day's close). Returns (state, calendar)."""
    ctx, cal = build_context(df, cfg, regime=_FixedRegime(1.0), whole_shares=True)
    state = SwingLoopState(
        portfolio=Portfolio(cash=cfg.starting_capital), pending_fills=[], anchors={}
    )
    for i, d in enumerate(cal):
        if i == entry_idx:
            c0 = ctx.close[d][ISIN]
            state.portfolio.positions[ISIN] = Position(
                isin=ISIN,
                symbol="AAA",
                shares=100,
                cost_basis=c0,
                entry_date=d.date(),
                last_price=c0,
            )
            state.anchors[ISIN] = c0
        step_day(ctx, state, d)
    return state, cal


def test_weekly_defers_configured_exit_to_decision_day():
    idx, close = _uptrend_dip(periods=45)
    base_close = close.copy()
    # A multi-day trail-grade slide (not a −25% crash) starting mid-week at idx 40.
    base_close[40:] = [
        base_close[39],
        base_close[39] - 12,
        base_close[39] - 13,
        base_close[39] - 14,
        base_close[39] - 15,
    ]
    df = _frame(idx, base_close)

    state_daily, _ = _run_seeded(df, _small_cfg(), entry_idx=35)
    state_weekly, _ = _run_seeded(
        df, _small_cfg(decision_cadence="weekly"), entry_idx=35
    )

    daily_trail = [e for e in state_daily.exit_log if e[2] == "atr_trail"]
    weekly_trail = [e for e in state_weekly.exit_log if e[2] == "atr_trail"]
    assert daily_trail and weekly_trail, "both cadences must eventually trail-exit"
    # Weekly defers the breach to the week's last trading day (≥ the daily exit date).
    assert weekly_trail[0][0] >= daily_trail[0][0]
    # Every weekly trail exit is recorded on a decision day (no floor breach here).
    decision = {ts.date() for ts in _weekly_decision_days(list(idx))}
    for d, _iid, reason in weekly_trail:
        assert d in decision, f"weekly trail exit on {d} is not a decision day"


def test_weekly_floor_still_fires_on_a_non_decision_day():
    idx, close = _uptrend_dip(periods=45)
    base_close = close.copy()
    crash_i = 41  # 2021-03-02 — a Tuesday (non-decision) in this bdate range
    assert idx[crash_i].weekday() != 4, (
        "fixture crash must be on a non-decision weekday"
    )
    base_close[crash_i:] = base_close[crash_i - 1] * 0.5  # −50% close
    df = _frame(idx, base_close)

    state, _ = _run_seeded(df, _small_cfg(decision_cadence="weekly"), entry_idx=35)
    floor_exits = [e for e in state.exit_log if e[2] == "catastrophic_floor"]
    assert floor_exits, "the −50% crash must trip the floor even under weekly cadence"
    # The floor fired on the crash day itself — a non-decision (mid-week) day.
    assert floor_exits[0][0] == idx[crash_i].date()
    assert idx[crash_i] not in _weekly_decision_days(list(idx))


# --------------------------------------------------------------------------- #
# 4. No-lookahead under weekly cadence (05 §9). Guards: the decision-day set   #
#    or weekly path leaking a future bar into an on/before-cut decision.       #
# --------------------------------------------------------------------------- #
def test_weekly_no_lookahead_under_future_corruption():
    cfg = _small_cfg(decision_cadence="weekly")
    idx, close = _uptrend_dip(periods=45)
    df = _frame(idx, close)
    res_clean = run(df, cfg, regime=_FixedRegime(1.0), whole_shares=True)

    cut = 30
    close_c = close.copy()
    close_c[cut + 1 :] = 9999.0
    res_c = run(
        df.assign(open=close_c, close=close_c),
        cfg,
        regime=_FixedRegime(1.0),
        whole_shares=True,
    )  # type: ignore[arg-type]

    cut_date = idx[cut].date()
    clean_snaps = {s.date: s for s in res_clean.snapshots if s.date <= cut_date}
    corrupt_snaps = {s.date: s for s in res_c.snapshots if s.date <= cut_date}
    assert clean_snaps.keys() == corrupt_snaps.keys()
    for d in clean_snaps:
        assert clean_snaps[d] == corrupt_snaps[d]
    clean_fills = [f for f in res_clean.fills_log if f.date <= cut_date]
    corrupt_fills = [f for f in res_c.fills_log if f.date <= cut_date]
    assert clean_fills == corrupt_fills


# --------------------------------------------------------------------------- #
# 5. min_hold blocks the CONFIGURED exit but never the floor (05 §5).         #
#    Guards: min-hold leaking onto the catastrophic floor (a risk control).   #
# --------------------------------------------------------------------------- #
class _TrailStore:
    def __init__(self, atr: float) -> None:
        self._atr = atr

    def row(self, day, iid):  # noqa: ANN001
        return pd.Series(
            {"atr20": self._atr, "ema_exit": 0.0, "exit_macd_cross_down": False}
        )


def test_min_hold_blocks_configured_exit_not_floor():
    cal = list(pd.bdate_range("2021-02-01", periods=15))
    cal_index = {ts: i for i, ts in enumerate(cal)}
    cfg = _small_cfg(min_hold_td=5)
    ctx = types.SimpleNamespace(
        config=cfg, cal_index=cal_index, signal_store=_TrailStore(atr=1.0)
    )
    pos = Position(
        isin=ISIN,
        symbol="AAA",
        shares=10,
        cost_basis=100.0,
        entry_date=cal[0].date(),
        last_price=100.0,
    )
    state = SwingLoopState(
        portfolio=Portfolio(1e6), pending_fills=[], anchors={ISIN: 100.0}
    )
    # Day 3 (3 td held < 5): inside min-hold. trail level = 100 − 3×1 = 97; close 90 breaches.
    d3 = cal[3]
    assert not _past_min_hold(ctx, pos, d3)
    assert (
        _exit_reason(ctx, state, ISIN, pos, 90.0, d3, allow_configured_exit=False)
        is None
    ), "trail exit must be suppressed inside the min-hold window"
    # ...but a −25%+ floor breach fires regardless of min-hold (close 70 < 75 floor).
    assert (
        _exit_reason(ctx, state, ISIN, pos, 70.0, d3, allow_configured_exit=False)
        == "catastrophic_floor"
    )
    # Day 6 (6 td held ≥ 5): past min-hold → the same trail breach now fires.
    d6 = cal[6]
    assert _past_min_hold(ctx, pos, d6)
    assert (
        _exit_reason(
            ctx,
            state,
            ISIN,
            pos,
            90.0,
            d6,
            allow_configured_exit=_past_min_hold(ctx, pos, d6),
        )
        == "atr_trail"
    )


# --------------------------------------------------------------------------- #
# 6. Re-entry cooldown suppresses a re-buy within N td of a full exit (05 §5).#
#    Guards: a cooldown that never expires, or one that leaks when set to 0.   #
# --------------------------------------------------------------------------- #
class _FakeEntryStore:
    def entry_signal(self, day, iid) -> bool:  # noqa: ANN001
        return True

    def row(self, day, iid):  # noqa: ANN001
        return pd.Series({"adv_20": 1e8, "mom": float("nan")})


def _cooldown_ctx(cfg: SwingConfig, cal_index: dict) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        config=cfg,
        membership={ISIN: set(cal_index)},
        signal_store=_FakeEntryStore(),
        sym_map={ISIN: ISIN},
        universe_mask=None,
        nifty_mom=None,
        cal_index=cal_index,
    )


def test_reentry_cooldown_suppresses_within_window_then_allows():
    cal = list(pd.bdate_range("2021-06-01", periods=20))
    cal_index = {ts: i for i, ts in enumerate(cal)}
    exit_day = cal[2]

    def _scan_on(day_idx: int, cooldown: int) -> int:
        cfg = _small_cfg(reentry_cooldown_td=cooldown)
        ctx = _cooldown_ctx(cfg, cal_index)
        state = SwingLoopState(
            portfolio=Portfolio(cfg.starting_capital),
            pending_fills=[],
            anchors={},
            last_exit={ISIN: exit_day},
        )
        day = cal[day_idx]
        _scan_entries(ctx, state, day, day.date(), 1.0, {ISIN: 100.0})
        return len([f for f in state.pending_fills if f.side == "buy"])

    # 5-td cooldown: exit at idx 2 ⇒ blocked through idx 6 (4 td later), allowed at idx 7.
    assert _scan_on(5, cooldown=5) == 0, "within cooldown ⇒ no re-entry"
    assert _scan_on(7, cooldown=5) == 1, "past cooldown ⇒ re-entry allowed"
    # cooldown 0 (default) never suppresses, even one day after the exit.
    assert _scan_on(3, cooldown=0) == 1, "cooldown=0 is byte-identical (no suppression)"
