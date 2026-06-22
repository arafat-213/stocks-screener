"""06 T06.5 — warm-start the S3 paper book on identity-continuous (stitched) data.

The v3/11 warm-start surfaced the gap 06 fixes: replaying frozen S3 over a store that
keyed identity on the raw ISIN left the book degenerate — 6 unsellable **ghosts** held
on dead (succeeded) ISINs plus idle cash, instead of a full ~20-name momentum book
(06 §2). T06.2–T06.4 re-keyed identity onto a chain-constant ``instrument_id``. These
tests prove the *integration* deliverable of T06.5 on a synthetic store: a full
inception→edge warm-start replay through ``live_engine.process_day`` now yields a full
book with **zero carried-unsellable holdings**, and the §2 shadow-parity still holds.

The teeth (Rule 9): the GREEN test (stitched) and the RED test (raw isins, the pre-fix
store shape) run the *same* succession panel through the *same* warm-start loop. Green ⇒
the name held into the split is carried as one instrument and stays sellable; Red ⇒ the
old leg becomes the exact ghost §2 describes (held, no forward price, unsellable). Offline
throughout: synthetic prices, rising synthetic regime index, in-memory sqlite, no network.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from app.db.models import PaperV2Portfolio, PaperV2Position
from app.paper_v2 import live_engine, parity

_PRICE_COLS = [
    "isin",
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "close_raw",
    "close_tr",
    "volume",
    "traded_value",
    "adv_20",
    "adj_factor",
    "tr_factor",
    "series",
    "instrument_id",
]

# The succession chain: OLD ends, NEW begins next trading day (a face-value re-issue).
CHAIN_OLD = "INE999A01010"
CHAIN_NEW = "INE999A01028"
N_OLD = 320  # OLD trades days 0..319 ...
N_DAYS = 400  # ... NEW trades days 320..399 (consecutive, date-disjoint)


def _rows(isin, symbol, dates, closes, *, instrument_id, adv=1e8):
    """Long-format rows for one leg. ``instrument_id=None`` omits the column entirely
    (the pre-T06.2 raw-isin store shape that reproduces the §2 ghost)."""
    out = []
    for d, c in zip(dates, closes):
        row = {
            "isin": isin,
            "symbol": symbol,
            "date": d,
            "open": c,
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
        out.append(row)
    return out


def _succession_panel(*, stitched: bool):
    """24 ordinary random-walk names + 1 succession chain.

    The chain is a strong, low-noise riser on BOTH legs, so the 5-factor composite ranks
    it near the top and S3 holds it continuously — including straight through the split.
    ``stitched=True`` ⇒ both legs carry ``instrument_id = CHAIN_OLD`` (the T06.2 store);
    ``stitched=False`` ⇒ no ``instrument_id`` column (raw-isin pre-fix store).
    """
    rng = np.random.default_rng(11)
    all_dates = pd.bdate_range("2022-01-03", periods=N_DAYS)
    rows: list[dict] = []

    # 24 ordinary names — modest upward random walks (the book's other holdings).
    for k in range(24):
        isin = f"INE{k:03d}B01011"
        price = 100.0
        drift = 0.0003 + 0.00003 * k
        for d in all_dates:
            price = max(price * (1 + rng.normal(drift, 0.012)), 0.01)
            rows += _rows(
                isin,
                isin,
                [d],
                [price],
                instrument_id=(isin if stitched else None),
            )

    # The chain: smooth ~0.4%/day rise the whole way (highest momentum, lowest vol).
    old_dates = all_dates[:N_OLD]
    new_dates = all_dates[N_OLD:]
    chain_close = [100.0 * (1.004**i) for i in range(N_DAYS)]
    iid = CHAIN_OLD if stitched else None
    rows += _rows(CHAIN_OLD, "CHAIN", old_dates, chain_close[:N_OLD], instrument_id=iid)
    rows += _rows(CHAIN_NEW, "CHAIN", new_dates, chain_close[N_OLD:], instrument_id=iid)

    cols = _PRICE_COLS if stitched else [c for c in _PRICE_COLS if c != "instrument_id"]
    return pd.DataFrame(rows, columns=cols)


def _rising_index(prices: pd.DataFrame) -> pd.Series:
    """Benchmark always above its 200-DMA ⇒ regime risk-on (buys are allowed)."""
    days = sorted(prices["date"].drop_duplicates())
    return pd.Series(np.linspace(100.0, 240.0, len(days)), index=pd.DatetimeIndex(days))


def _identity_col(prices: pd.DataFrame) -> str:
    return "instrument_id" if "instrument_id" in prices.columns else "isin"


def _ghosts(prices: pd.DataFrame, positions, last_day: date) -> list[str]:
    """Held positions with NO price on ``last_day`` under their identity key — i.e.
    carried but unsellable (the §2 ghost). Resolves on ``instrument_id`` when present
    (stitched store), else raw ``isin`` (pre-fix store)."""
    key = _identity_col(prices)
    live = set(prices.loc[prices["date"] == pd.Timestamp(last_day), key])
    return [p.isin for p in positions if p.isin not in live]


def _new_book(db) -> PaperV2Portfolio:
    pf = PaperV2Portfolio(
        name="s3_probation_t065",
        starting_capital=1_000_000.0,
        cash=1_000_000.0,
        is_active=True,
        last_processed_date=None,
    )
    db.add(pf)
    db.flush()
    return pf


def _warm_start(
    db, prices: pd.DataFrame, index: pd.Series
) -> tuple[PaperV2Portfolio, date]:
    """Run the inception→confirmed-edge replay exactly as tasks.py does (ctx + adj_lookup
    built once, reused across the loop) and return (book, last_processed_day)."""
    pf = _new_book(db)
    cal = sorted(d.date() for d in prices["date"].drop_duplicates())
    target = cal[-1]
    to_process = live_engine.confirmed_replay_days(cal, None, target)
    ctx = live_engine.build_live_context(prices, index)[0]
    adj_lookup = live_engine.build_adj_factor_lookup(prices)
    for d in to_process:
        live_engine.process_day(
            db, pf.id, prices, index, d, commit=False, ctx=ctx, adj_lookup=adj_lookup
        )
    return pf, to_process[-1]


# ===========================================================================
# GREEN — stitched store: full book, zero ghosts, parity holds
# ===========================================================================


def test_t06_5_warmstart_full_book_no_ghost_green(db):
    prices = _succession_panel(stitched=True)
    index = _rising_index(prices)

    pf, last_day = _warm_start(db, prices, index)

    positions = db.query(PaperV2Position).filter_by(portfolio_id=pf.id).all()

    # (1) Full ~20-name book, not 6 ghosts + idle cash (the §2 success gate).
    assert len(positions) > 6, f"degenerate book: {len(positions)} holdings"

    # (2) The name held across the split is carried as ONE instrument (CHAIN_OLD ==
    #     instrument_id) and is therefore live/sellable on the edge — never the NEW raw leg.
    held = {p.isin for p in positions}
    assert CHAIN_OLD in held, "the chain should be held continuously across the split"
    assert CHAIN_NEW not in held, "a stitched chain is never keyed on the new raw leg"

    # (3) Zero carried-unsellable holdings (no ghost).
    assert _ghosts(prices, positions, last_day) == []

    # (4) §2 shadow-parity still holds on the stitched data (fidelity preserved).
    par = parity.shadow_parity(db, pf.id, prices, index, last_day)
    assert par.passed, par.summary
    assert par.max_dev_bps < parity.PARITY_TOL_BPS


# ===========================================================================
# RED — raw-isin store: the same chain held into the split becomes a §2 ghost
# ===========================================================================


def test_t06_5_warmstart_ghost_without_stitching_red(db):
    """The pre-fix store shape (no instrument_id). The chain name is bought and held on
    the OLD leg; after the split OLD stops trading and — with no chain-constant identity —
    the held position has no forward price and cannot be sold. It is carried as the exact
    ghost §2 describes. This is the failure the GREEN test proves fixed."""
    prices = _succession_panel(stitched=False)
    index = _rising_index(prices)

    pf, last_day = _warm_start(db, prices, index)

    positions = db.query(PaperV2Position).filter_by(portfolio_id=pf.id).all()
    held = {p.isin for p in positions}

    # The OLD leg was held into the split ...
    assert CHAIN_OLD in held, "precondition: the chain must be held before the split"
    # ... and is now a carried-unsellable ghost (no price on the edge under raw isin).
    ghosts = _ghosts(prices, positions, last_day)
    assert CHAIN_OLD in ghosts, "raw-isin old leg must be an unsellable ghost (the bug)"
