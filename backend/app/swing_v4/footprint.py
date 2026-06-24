"""footprint.py — returns-blind concurrent-holdings footprint (v4/02 §4, 00 §3.5/§14).

`00` §3.5 originally made ``N_max`` a **returns-blind procedure**, not a picked number,
to resolve the "the cap must lock before the run, but we mustn't tune it" tension. This
module is the only place V4.0 produces a number — and it is **a count, never a return**:
no sizing, no costs, no PnL, no Calmar/Sharpe/turnover. It therefore **adds 0 to K** (no
return is evaluated; v4/02 §4).

**Amendment 1 (00 §14) retired the N_max *lock* → kept this as a DIAGNOSTIC.** The V4.0c
footprint over the full v2 universe (max 408 / p95 298 / p99 371 / **mean 118**) proved
the signal is intrinsically broad, which is exactly *why* a binding concentration cap
(`target_positions = 15`) is needed. The p99-rounded number (``n_max_locked`` below) is
no longer a lock — it is the diagnostic that motivated the cap. Pass a ``universe_mask``
(or run with ``cfg.universe_mode == "stable"`` via ``main()``) to re-measure the crowding
*within the narrowed U=200 stable universe* — the post-amendment hunting ground.

Procedure (v4/02 §4):
  1. Run the **frozen entry rule + Type-3 exit** as a pure per-name state machine over
     **DISCOVERY** (2018-02-06 → 2023-06-30).
  2. Run it **unconstrained**: no ``N_max`` cap, no regime throttle, no sizing, no costs,
     no PnL. Every name whose 4 entry conditions fire is treated as "held" until its own
     Type-3 exit fires. Excluding the throttle yields a *conservative upper-bound* crowding
     distribution ⇒ the resulting cap is a genuine tail-risk control that rarely binds,
     not a performance lever (v4/02 §11 item 5, Arafat-confirmed).
  3. Record **only** the time series of concurrent open holdings (and fresh actionable
     entry signals/day). Report the full distribution: max / p95 / p99.
  4. Lock ``N_max`` ≈ the p99 of concurrent holdings, rounded to an integer.

Fidelity to the engine state machine (engine.py §1.1): an entry signal on D close fills
at D+1 open (the name becomes "held" the next trading day, anchor seeded at that day's
close); a Type-3 close-breach on day Dk queues the exit for Dk+1 open, so the name is
counted as held through Dk inclusive. This mirrors how a position lives in
``Portfolio.positions`` across the engine's MTM snapshot — exactly, but with no cash,
shares, or price-paid (count only).

The **catastrophic floor is deliberately NOT applied** here: §4 specifies "entry rule +
Type-3 exit", and the floor needs a fill-price cost basis that does not exist in a
count-only pass. Omitting it can only *lengthen* holds ⇒ more concurrency ⇒ a strictly
more conservative (larger) cap. Surfaced per Rule 12.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2.stable_universe import (
    StableUniverseMask,
    build_stable_universe_mask,
)
from app.backtest_v2.validation import DISCOVERY
from app.swing_v4.config import SwingConfig
from app.swing_v4.signals import SwingSignalStore, precompute_swing_signals


@dataclass
class FootprintResult:
    """The returns-blind N_max measurement (v4/02 §4). A count, never a return."""

    concurrent: pd.Series  # date → concurrent open holdings (DISCOVERY trading days)
    daily_entries: pd.Series  # date → fresh actionable entry signals that day
    max_concurrent: int
    p95: float
    p99: float
    n_max_locked: int  # ≈ p99, rounded — DIAGNOSTIC ONLY post-Amendment-1 (00 §14)
    window: tuple[date, date]
    n_instruments: int  # distinct instrument_ids that ever held during the window


def measure_footprint(
    prices: pd.DataFrame,
    cfg: SwingConfig | None = None,
    *,
    window: tuple[date, date] = DISCOVERY,
    signal_store: SwingSignalStore | None = None,
    universe_mask: StableUniverseMask | None = None,
) -> FootprintResult:
    """Measure the unconstrained concurrent-holdings footprint over ``window``.

    Parameters
    ----------
    prices : pd.DataFrame
        Long-format multi-ISIN **adjusted** frame from ``read_prices_adjusted``
        (columns: isin, date, open, high, low, close, adv_20; post-06 instrument_id).
        Full history should be passed so SMA200/ATR20 warm up before the window start.
    cfg : SwingConfig
        Frozen `00` strategy params. Only the **entry rule + Type-3 trail** are used
        (``exit_type`` is ignored — the footprint is by definition the Type-3 footprint,
        00 §3.5 / v4/02 §4). ``target_positions`` is irrelevant here — the footprint is
        unconstrained by design (it measures the *uncapped* crowding, a diagnostic).
    window : (date, date)
        Inclusive count window. Defaults to DISCOVERY. Percentiles are taken over every
        trading day in the window (including zero-holding days), never only busy days.
    signal_store : pre-built SwingSignalStore; if None, ``precompute_swing_signals`` runs.
    universe_mask : optional stable_universe mask (00 §14 D). When given, a name's entry
        is only counted while it is a member on that day — the footprint then measures
        crowding *within the narrowed U=200 universe* (the post-amendment book). When
        None, the full-universe footprint is measured (the original V4.0c diagnostic).
    """
    cfg = cfg or SwingConfig()
    if signal_store is None:
        signal_store = precompute_swing_signals(prices, cfg)

    mult = cfg.atr_mult
    liq_floor = cfg.liquidity_floor_cr * 1e7
    w_start = pd.Timestamp(window[0])
    w_end = pd.Timestamp(window[1])

    held_counter: Counter[pd.Timestamp] = Counter()
    entry_counter: Counter[pd.Timestamp] = Counter()
    instruments_held: set[str] = set()

    for iid, df in signal_store.items():
        closes = df["close"].to_numpy(dtype=float)
        atrs = df["atr20"].to_numpy(dtype=float)
        entries = df["entry"].to_numpy(dtype=float)
        advs = df["adv_20"].to_numpy(dtype=float)
        dates = df.index

        held = False
        anchor: float | None = None
        entry_pending = False
        exit_pending = False

        for j in range(len(df)):
            # --- step 1: apply prior-session queued fills at this open ---
            if exit_pending:
                held, anchor, exit_pending = False, None, False
            if entry_pending:
                held, anchor, entry_pending = True, None, False

            ts = dates[j]
            c = closes[j]

            if held:
                # --- step 3: ratchet trail anchor = max adjusted close since entry ---
                if not math.isnan(c):
                    anchor = c if anchor is None else max(anchor, c)
                # --- step 4: Type-3 exit check (close < anchor − mult×ATR20) ---
                atr = atrs[j]
                if (
                    anchor is not None
                    and not math.isnan(c)
                    and not math.isnan(atr)
                    and c < anchor - mult * atr
                ):
                    exit_pending = True
                # count concurrency on this name's own trading day (MTM-snapshot parity)
                if w_start <= ts <= w_end:
                    held_counter[ts] += 1
                    instruments_held.add(str(iid))

            # --- step 6: entry scan (4 frozen conditions true on D + liquid) ---
            elif not entry_pending:
                ent = entries[j]
                adv = advs[j]
                in_universe = universe_mask is None or universe_mask.is_member(ts, iid)
                if (
                    ent == 1.0
                    and not math.isnan(adv)
                    and adv >= liq_floor
                    and in_universe
                ):
                    entry_pending = True
                    if w_start <= ts <= w_end:
                        entry_counter[ts] += 1

    # Build a Series over EVERY trading day in the window (zero-holding days included),
    # using the union calendar of all instruments — otherwise the percentiles would be
    # taken only over busy days and over-state the cap.
    all_dates = sorted(
        {d for _, df in signal_store.items() for d in df.index if w_start <= d <= w_end}
    )
    concurrent = pd.Series(
        [held_counter.get(d, 0) for d in all_dates], index=pd.DatetimeIndex(all_dates)
    )
    daily_entries = pd.Series(
        [entry_counter.get(d, 0) for d in all_dates], index=pd.DatetimeIndex(all_dates)
    )

    if len(concurrent) == 0:
        raise ValueError(f"No trading days in window {window}.")

    vals = concurrent.to_numpy()
    max_c = int(vals.max())
    p95 = float(np.percentile(vals, 95))
    p99 = float(np.percentile(vals, 99))
    n_max_locked = int(round(p99))

    return FootprintResult(
        concurrent=concurrent,
        daily_entries=daily_entries,
        max_concurrent=max_c,
        p95=p95,
        p99=p99,
        n_max_locked=n_max_locked,
        window=window,
        n_instruments=len(instruments_held),
    )


def _print_footprint(label: str, res: "FootprintResult") -> None:  # pragma: no cover
    print(f"\n=== {label} (count only) ===")
    print(f"  Window:                 {res.window[0]} → {res.window[1]}")
    print(f"  Trading days counted:   {len(res.concurrent)}")
    print(f"  Instruments ever held:  {res.n_instruments}")
    print(f"  Concurrent holdings — max:  {res.max_concurrent}")
    print(f"  Concurrent holdings — p95:  {res.p95:.2f}")
    print(f"  Concurrent holdings — p99:  {res.p99:.2f}")
    print(f"  Concurrent holdings — mean: {res.concurrent.mean():.2f}")
    print(f"  Fresh entries/day — max:    {int(res.daily_entries.max())}")
    print(f"  Fresh entries/day — mean:   {res.daily_entries.mean():.2f}")
    print(f"  p99-rounded count (diagnostic): {res.n_max_locked}")


def main() -> None:  # pragma: no cover — operational runner, not a pytest path
    """Run the returns-blind concurrent-holdings footprint on the real adjusted store.

    No live API, no return number. Prints two diagnostics over DISCOVERY:
      1. the full-universe footprint (reproduces the V4.0c 371/118 finding), and
      2. the **Amendment-1 U=200 stable-universe** footprint — the post-amendment book.
    The contrast confirms `target_positions = 15` is a *binding* concentration cap, not
    a tail cap. Both are count-only (no PnL ⇒ adds 0 to K; 00 §14).
    """
    from app.data.bhavcopy import store

    print("Loading adjusted prices (full history for warmup)...", flush=True)
    prices = store.read_prices_adjusted()
    cfg = SwingConfig()

    print(
        f"Measuring unconstrained Type-3 footprint over DISCOVERY "
        f"{DISCOVERY[0]} → {DISCOVERY[1]} (no cap / no throttle / no sizing / no PnL)...",
        flush=True,
    )
    res_full = measure_footprint(prices, cfg)
    _print_footprint("Full-universe footprint (the V4.0c diagnostic)", res_full)

    print(
        f"\nBuilding U={cfg.universe_size_U} stable_universe mask "
        f"(B={cfg.universe_buffer_B}, {cfg.universe_rank_lookback_td}-td median adv_20)...",
        flush=True,
    )
    mask = build_stable_universe_mask(
        prices,
        cfg.universe_size_U,
        cfg.universe_buffer_B,
        cfg.universe_rank_lookback_td,
        cfg.universe_review_cadence,
    )
    res_stable = measure_footprint(prices, cfg, universe_mask=mask)
    _print_footprint(
        f"Amendment-1 stable-universe footprint (U={cfg.universe_size_U})", res_stable
    )

    print(
        f"\n  >>> target_positions = {cfg.target_positions} is a BINDING concentration "
        f"cap (00 §14); both footprints are diagnostics, neither is a lock; adds 0 to K."
    )


if __name__ == "__main__":  # pragma: no cover
    main()
