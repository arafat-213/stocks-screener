"""config.py — SwingConfig: the one config object for the v4 swing engine.

Every default is a value **frozen by `00_SWING_PREREG.md`** (citations inline).
This doc (v4/02) decides no strategy parameter; on any conflict `00` wins (§0).

The grid knobs (`exit_type`, `atr_mult`, `target_positions`, `regime_factors`) exist
so the `00` §5 grid can sweep them in V4.2; V4.0 only ever runs the frozen defaults.

**`00` Amendment 1 (§14, signed 2026-06-24) — return-blind structural rework:** the
V4.0c footprint proved the signal is intrinsically broad (mean 118 / p99 371 concurrent),
so `n_max`-as-sizing-divisor was broken. Amendment 1 supersedes it with a **binding
concentration cap `target_positions = 15`** (slot cap AND sizing divisor), a top-N
`adv_20` selector, a **`stable_universe` U=200** universe (AND-ed into the entry scan
beneath the retained ₹5cr floor), and **`starting_capital = ₹3.5L`** (real spare capital).
All return-blind ⇒ K stays 0, FINAL_OOS pristine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional


@dataclass
class SwingConfig:
    # --- universe / liquidity (00 §3.1 + Amendment 1 §14 D) ---
    liquidity_floor_cr: float = 5.0  # adv_20 >= ₹5cr, decision-date (retained beneath
    #                                  the stable_universe mask as a tradeability floor)
    # stable_universe (00 §14 D — reuses app/backtest_v2/stable_universe.py from v3 08).
    # "floor" = the ₹5cr-only legacy universe (test/diagnostic escape hatch + byte-identical
    # pre-amendment behaviour); "stable" = the frozen Amendment-1 candidate universe.
    universe_mode: Literal["floor", "stable"] = "stable"
    universe_size_U: int = (
        200  # top-U by 126-td median adv_20 (Nifty200 liquidity proxy)
    )
    universe_buffer_B: float = 1.25  # hysteresis: a member stays until rank > B*U
    universe_review_cadence: Literal["semi-annual"] = "semi-annual"
    universe_rank_lookback_td: int = 126  # ~6mo trailing median-adv_20 window

    # --- indicators (00 §3.2 — textbook-frozen) ---
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    sma_short: int = 20
    sma_mid: int = 50
    sma_long: int = 200
    ema_exit: int = 50  # EMA50 (Type 2 exit comparator)
    atr_period: int = 20  # Wilder ATR(20)

    # --- exit (00 §3.4 — candidate = Type 3; 1/2 are grid comparators) ---
    exit_type: int = 3  # knob: 1 (MACD cross-down) / 2 (close<EMA50) / 3 (ATR trail)
    # `05` §3.1 makes atr_mult the PRIMARY turnover lever: a WIDER multiple holds winners
    # longer ⇒ fewer turns ⇒ less cost (the give-back trade-off the grid measures). `00`
    # froze 3.0 and only-ever-tested TIGHTER; `05` Stage-1 grid sweeps {3.0, 4.0, 5.0}
    # (candidate 4.0). Default stays 3.0 (the `00`/V4.4 frozen value ⇒ anchor parity).
    atr_mult: float = 3.0  # `05` §3.1 grid {3.0, 4.0, 5.0}; `00` §6.3 plateau axis
    catastrophic_stop_pct: float = 25.0  # close-breach circuit breaker beneath Type 3

    # --- decision cadence + anti-thrash levers (v4/05 §3.2 / §3.4 / §5) ---
    # `decision_cadence` (05 §3.2 — the secondary turnover lever, binary): "daily" (frozen
    # `00` default ⇒ byte-identical) re-decides exits + entries every close. "weekly"
    # coarsens the DECISION clock — on a NON-decision day step_day still applies queued
    # fills, MTMs, ratchets the trail anchor, and checks the −25% catastrophic floor (risk
    # control is NEVER coarsened), but SKIPS the configured exit check and the entry scan.
    # Decision day = the completed week's last trading day (W-FRI as-of; 05 §3.2 / §9).
    decision_cadence: Literal["daily", "weekly"] = "daily"
    # `05` §5 NON-GATING anti-thrash diagnostic (adds 0 to K). Both default 0 ⇒ byte-
    # identical. `min_hold_td` blocks the CONFIGURED exit (NOT the catastrophic floor) for
    # the first N trading days after entry; `reentry_cooldown_td` suppresses re-entry of an
    # instrument_id for N trading days after a full exit. Run ONCE on the Stage-1 candidate
    # (05 §5); the locked OOS candidate uses the §4 levers only (never these).
    min_hold_td: int = 0
    reentry_cooldown_td: int = 0

    # --- sizing / regime throttle (00 §3.5 + Amendment 1 §14 A/B/C) ---
    # `target_positions` is a BINDING concentration cap: simultaneously the hard slot cap
    # AND the equal-weight sizing divisor (per-position = f × capital / target_positions).
    # Amendment 1 retired the old returns-blind `n_max` tail cap (p99=371) — at 371 the
    # divisor gave microscopic positions / ~68% cash drag because the signal is broad
    # (mean 118 concurrent). 15 is an OPERATIONAL choice (manageable book + whole-share
    # granularity at ~₹3-4L), not a tuned knob; `00` §5 stresses {13,15,17} in V4.2.
    target_positions: int = 15

    # Oversubscription selector (00 §14 C). "adv" = the frozen V4.1 candidate: keep the
    # top-`target_positions` by adv_20 (most liquid first). "random" exists ONLY for the
    # `00` §6 selection-quality diagnostic's `B_random` reference book (keep a random
    # `target_positions` when oversubscribed, seeded for reproducibility).
    #
    # `04` (return-informed selector prereg, LOCKED 2026-06-24) adds two return-informed
    # rankers as a budgeted grid axis carrying its own K:
    #   "mom" = the registered candidate — rank firing names by trailing `selector_lookback`-td
    #           total return of the adjusted close (desc). The textbook 6-month momentum ranker.
    #   "rs"  = comparator — candidate trailing return MINUS the Nifty 50 trailing return over
    #           the same lookback (relative strength / excess). Needs nifty_mom in the engine
    #           context (pass `nifty50_price` to build_context); fails loud otherwise.
    # NOTE (`04` §3 finding, Rule 12): the Nifty 50 term is a SINGLE per-day constant subtracted
    # from every candidate, so it cannot change the cross-sectional order — as a *selector* "rs"
    # is mathematically identical to "mom". We still run it to demonstrate the identity, not assume it.
    # Default "adv" ⇒ byte-identical to the locked V4.1 engine; "mom"/"rs" add to K (`04` §1/§4).
    selector: Literal["adv", "random", "mom", "rs"] = "adv"
    selector_seed: int = 0  # only consulted when selector == "random"
    # `04` §3/§4 — the return-informed-selector lookback (trading days). Frozen at the
    # conventional 126 td (~6mo) for V4.4 Stage 1; {63, 252} are the V4.5 §6.3 plateau
    # neighborhood (NOT swept here). Also the window for the "rs" Nifty 50 benchmark return.
    selector_lookback: int = 126

    starting_capital: float = 350_000.0  # Amendment 1 §14 E — real spare capital

    # --- regime score (00 §4) ---
    regime_factors: int = 5  # 5-factor frozen; 3 = reported ablation only (V4.2)
    regime_breadth_min: float = 60.0  # cond 3: liq_breadth_pct > 60
    regime_ad_min: float = 1.0  # cond 4: liq_ad_ratio > 1
    regime_vix_max: float = 20.0  # cond 5: india_vix < 20
    regime_dma_long: int = 200  # conds 1 & 2: Nifty 50 200-DMA
    regime_dma_short: int = 50  # cond 2: Nifty 50 50-DMA

    # --- run window ---
    date_from: Optional[date] = None
    date_to: Optional[date] = None
