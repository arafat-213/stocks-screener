"""P11 — re-warm-start the v3/11 S3 paper book with WHOLE-SHARE sizing.

`11` §13 deviation (signed 2026-06-23): the forward paper probation must rehearse
real-capital execution faithfully, and NSE equity delivery trades only in integer
shares (lot size 1). The engine now floors fills to whole shares when
`EngineContext.whole_shares` is True; `s3_config.S3_WHOLE_SHARES = True` turns it on
for the live book (routed through `build_live_context`, so book + shadow-parity stay
byte-identical).

Because the book was flat (0 positions) with ZERO forward daily runs, re-warm-starting
costs no live track record. This one-shot operator replay:
  1. RESETs the s3_probation book to its cash-only inception state.
  2. RESETs the probation clock to TODAY (created_at := now) so the clean integer book
     gets a full fresh 6 forward months (Arafat's choice, 2026-06-23).
  3. Re-runs the inception->confirmed-edge warm-start (whole_shares now ON).
  4. Asserts every carried position is an INTEGER share count, 0 ghosts, parity ~0 bps.

Same guardrails as t06_5 / t07_5: worker + Celery beat STAY STOPPED (operator run, not
the forward probation). Read-only on prices/FINAL_OOS; mutates ONLY the s3_probation
book rows. Pure row deletion + replay — no schema change, no Alembic migration.
"""

from __future__ import annotations

import datetime
import logging

import pandas as pd

from app.backtest_v2 import benchmark
from app.data.bhavcopy import store
from app.db.models import (
    PaperV2DailySnapshot,
    PaperV2PendingFill,
    PaperV2Portfolio,
    PaperV2Position,
)
from app.db.session import SessionLocal
from app.paper_v2 import live_engine, parity, s3_config

logging.basicConfig(level=logging.WARNING)


def reset_book(db, pf: PaperV2Portfolio, reset_clock: bool) -> None:
    """Truncate the book's child rows and return the portfolio to inception (cash-only).

    Pure row deletion — no schema change. `reset_clock` updates `created_at` (the
    probation go-live anchor) to now so the re-warm-started integer book gets a fresh
    6-month window (`11` §13, 2026-06-23). DailySnapshot rows are cleared too so the
    NAV curve is rebuilt cleanly under the new go-live divider (idempotent re-upsert).
    """
    db.query(PaperV2Position).filter_by(portfolio_id=pf.id).delete()
    db.query(PaperV2PendingFill).filter_by(portfolio_id=pf.id).delete()
    db.query(PaperV2DailySnapshot).filter_by(portfolio_id=pf.id).delete()
    pf.cash = pf.starting_capital
    pf.last_processed_date = None
    if reset_clock:
        pf.created_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()


def main(reset_clock: bool = True) -> None:
    db = SessionLocal()
    try:
        prices = store.read_prices_adjusted()
        prices["date"] = pd.to_datetime(prices["date"])
        inception = prices["date"].min().date()
        target = prices["date"].max().date()
        index_prices = benchmark.load_price_index(inception, target)

        pf = live_engine.get_or_create_book(db)

        old_pos = db.query(PaperV2Position).filter_by(portfolio_id=pf.id).all()
        print(
            f"[BEFORE] cash={pf.cash:,.2f} lpd={pf.last_processed_date} "
            f"created_at={pf.created_at} positions={len(old_pos)}"
        )

        # ---- 1+2. reset book + (optionally) probation clock ----
        reset_book(db, pf, reset_clock)
        print(
            f"[RESET ] cash={pf.cash:,.2f} lpd={pf.last_processed_date} "
            f"created_at={pf.created_at} positions=0"
        )

        # ---- 3. warm-start replay (inception -> confirmed edge), whole_shares ON ----
        cal = sorted(d.date() for d in prices["date"].drop_duplicates())
        to_process = live_engine.confirmed_replay_days(
            cal, pf.last_processed_date, target
        )
        ctx = live_engine.build_live_context(prices, index_prices)[0]
        assert ctx.whole_shares is True, (
            "whole_shares must be ON for the integer re-warm-start "
            f"(s3_config.S3_WHOLE_SHARES={s3_config.S3_WHOLE_SHARES})"
        )
        print(
            f"[REPLAY] {len(to_process)} confirmed days {to_process[0]} -> "
            f"{to_process[-1]}; whole_shares={ctx.whole_shares} "
            f"force_exit_K={ctx.terminate_after_silent_days}"
        )
        adj_lookup = live_engine.build_adj_factor_lookup(prices)
        go_live = pf.created_at.astimezone(
            datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        ).date()
        n_reb = 0
        for d in to_process:
            rep = live_engine.process_day(
                db,
                pf.id,
                prices,
                index_prices,
                d,
                ctx=ctx,
                adj_lookup=adj_lookup,
                go_live=go_live,
            )
            if rep.is_rebalance:
                n_reb += 1
        last_day = to_process[-1]
        print(
            f"[REPLAY] done: {n_reb} rebalances; last_processed={last_day} go_live={go_live}"
        )

        # ---- final book ----
        pf = db.get(PaperV2Portfolio, pf.id)
        pos = db.query(PaperV2Position).filter_by(portfolio_id=pf.id).all()
        equity = pf.cash + sum(p.shares * (p.last_price or p.cost_basis) for p in pos)
        print(
            f"\n[AFTER ] cash={pf.cash:,.2f} lpd={pf.last_processed_date} "
            f"positions={len(pos)} equity={equity:,.2f}"
        )
        for r in sorted(pos, key=lambda r: r.symbol):
            mtm = r.shares * (r.last_price or r.cost_basis)
            print(
                f"    {r.isin} {r.symbol:14s} shares={r.shares:10.4f} mtm={mtm:14,.2f}"
            )

        # ---- gate 1: every carried position is a WHOLE share count ----
        frac = [r for r in pos if abs(r.shares - round(r.shares)) > 1e-9]
        print(f"\n[WHOLE ] fractional-share positions: {len(frac)}")
        for r in frac:
            print(f"    FRACTIONAL {r.isin} {r.symbol} shares={r.shares!r}")

        # ---- gate 2: 0 carried-unsellable (ghost) holdings ----
        px_last = prices[prices["date"] == pd.Timestamp(last_day)]
        live_ids = set(px_last["instrument_id"]) | set(px_last["isin"])
        ghosts = [r for r in pos if r.isin not in live_ids]
        print(f"[GHOST ] carried-unsellable holdings: {len(ghosts)}")

        # ---- gate 3: shadow-parity at the final processed day ----
        par = parity.shadow_parity(db, pf.id, prices, index_prices, last_day)
        print(f"\n[PARITY] {par.summary}  max_dev_bps={par.max_dev_bps:.6f}")

        snap_n = db.query(PaperV2DailySnapshot).filter_by(portfolio_id=pf.id).count()
        print(f"[SNAP  ] daily_snapshot rows populated: {snap_n}")

        print("\n=== P11 WHOLE-SHARE RE-WARM-START GATE ===")
        print(
            f"  0 fractional positions:   {len(frac)}  -> {'PASS' if not frac else 'FAIL'}"
        )
        print(
            f"  0 ghost holdings:         {len(ghosts)}  -> {'PASS' if not ghosts else 'FAIL'}"
        )
        print(
            f"  shadow-parity ~0 bps:     {par.max_dev_bps:.6f}  -> {'PASS' if par.passed else 'FAIL'}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
