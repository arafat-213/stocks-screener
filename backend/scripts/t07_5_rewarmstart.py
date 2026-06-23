"""T07.5 — re-warm-start the v3/11 S3 paper book on DE-GHOSTED data.

Same one-shot operator replay as ``t06_5_rewarmstart`` (reset -> inception->edge
warm-start -> shadow-parity), re-run now that the 07 §6 force-exit (Approach A) is ON in
``live_engine.build_live_context`` (K = ``s3_config.S3_TERMINATE_AFTER_SILENT_DAYS`` = 15
trading days). T06.5 left the book holding the 3 merger/cancellation ghosts (HDFC,
INOXLEISUR, TATAMTRDVR — spec 07 §2/§9); this re-run proves the engine force-exits them at
termination so the warm-started book inherits **0 carried-unsellable holdings** (07 §8
T07.5 gate). Nothing about the stitched store changed — only the engine capability did.

Worker + Celery beat stay STOPPED — this is an operator run, not the forward probation
(11 §1 / spec 07 §9). Read-only on prices/FINAL_OOS; mutates ONLY the s3_probation book rows.

Steps (07 §8 T07.5):
  1. RESET the s3_probation book to its cash-only inception state.
  2. Re-run the inception->confirmed-edge warm-start over the stitched store (force-exit ON).
  3. Assert 0 carried-unsellable holdings + re-check shadow-parity ~= 0.0 bps.
"""

from __future__ import annotations

import logging

import pandas as pd

from app.backtest_v2 import benchmark
from app.data.bhavcopy import store
from app.db.models import PaperV2PendingFill, PaperV2Portfolio, PaperV2Position
from app.db.session import SessionLocal
from app.paper_v2 import live_engine, parity

logging.basicConfig(level=logging.WARNING)


def reset_book(db, pf: PaperV2Portfolio) -> None:
    """Truncate the book's child rows and return the portfolio to inception (cash-only).

    Pure row deletion — no schema change, so no Alembic migration (07 §8 guardrail).
    """
    db.query(PaperV2Position).filter_by(portfolio_id=pf.id).delete()
    db.query(PaperV2PendingFill).filter_by(portfolio_id=pf.id).delete()
    pf.cash = pf.starting_capital
    pf.last_processed_date = None
    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        prices = store.read_prices_adjusted()
        prices["date"] = pd.to_datetime(prices["date"])
        inception = prices["date"].min().date()
        target = (
            prices["date"].max().date()
        )  # store is already current to latest bhavcopy
        index_prices = benchmark.load_price_index(inception, target)

        pf = live_engine.get_or_create_book(db)

        # ---- snapshot the OLD (ghost-carrying, T06.5) state for the record ----
        old_pos = db.query(PaperV2Position).filter_by(portfolio_id=pf.id).all()
        print(
            f"[BEFORE] cash={pf.cash:,.2f} lpd={pf.last_processed_date} "
            f"positions={len(old_pos)}"
        )
        for r in old_pos:
            print(f"    {r.isin} {r.symbol} shares={r.shares:.4f}")

        # ---- 1. reset ----
        reset_book(db, pf)
        print(f"[RESET ] cash={pf.cash:,.2f} lpd={pf.last_processed_date} positions=0")

        # ---- 2. warm-start replay (inception -> confirmed edge), force-exit ON ----
        cal = sorted(d.date() for d in prices["date"].drop_duplicates())
        to_process = live_engine.confirmed_replay_days(
            cal, pf.last_processed_date, target
        )
        print(
            f"[REPLAY] {len(to_process)} confirmed trading days "
            f"{to_process[0]} -> {to_process[-1]}"
        )
        ctx = live_engine.build_live_context(prices, index_prices)[0]
        print(
            f"[REPLAY] force-exit K = {ctx.terminate_after_silent_days} trading days "
            f"(07 §6 Approach A, ON)"
        )
        adj_lookup = live_engine.build_adj_factor_lookup(prices)
        n_reb = 0
        for d in to_process:
            rep = live_engine.process_day(
                db, pf.id, prices, index_prices, d, ctx=ctx, adj_lookup=adj_lookup
            )
            if rep.is_rebalance:
                n_reb += 1
        last_day = to_process[-1]
        print(f"[REPLAY] done: {n_reb} rebalances; last_processed={last_day}")

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
                f"    {r.isin} {r.symbol:14s} shares={r.shares:12.4f} "
                f"mtm={mtm:14,.2f} entry={r.entry_date}"
            )

        # ---- carried-unsellable (ghost) detection: a held instrument with no price
        #      on/after the last processed day cannot be sold (the §2 ghost). With the
        #      07 force-exit ON this MUST now be empty. ----
        px_last = prices[prices["date"] == pd.Timestamp(last_day)]
        live_ids = set(px_last["instrument_id"]) | set(px_last["isin"])
        ghosts = [r for r in pos if r.isin not in live_ids]
        print(f"\n[GHOST ] carried-unsellable holdings: {len(ghosts)}")
        for r in ghosts:
            print(f"    GHOST {r.isin} {r.symbol}")

        # ---- 3. shadow-parity at the final processed day ----
        par = parity.shadow_parity(db, pf.id, prices, index_prices, last_day)
        print(f"\n[PARITY] {par.summary}")
        print(
            f"[PARITY] engine names={len(par.engine_weights)} "
            f"live names={len(par.live_weights)} max_dev_bps={par.max_dev_bps:.6f}"
        )
        if par.breaches:
            for isin, dev in par.breaches[:10]:
                print(f"    BREACH {isin} dev={dev:.2f}bps")

        # ---- gate summary (07 §8 T07.5) ----
        print("\n=== T07.5 SUCCESS GATE ===")
        print(
            f"  0 ghost / unsellable holdings:     {len(ghosts)}  -> "
            f"{'PASS' if len(ghosts) == 0 else 'FAIL'}"
        )
        print(
            f"  shadow-parity max_dev ~= 0.0 bps:  {par.max_dev_bps:.6f}  -> "
            f"{'PASS' if par.passed else 'FAIL'}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
