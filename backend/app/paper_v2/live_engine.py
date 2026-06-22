"""Live paper shell for the v3/11 S3 forward probation (§2/§3e).

This is the *thin shell* the prereg mandates: a point-in-time data feeder + state
persistence + persisted pending-fills queue + order differ + paper executor. The
strategy brain is NOT re-implemented — every decision is delegated to
``backtest_v2.engine.step_day`` (the exact code ``engine.run`` executes), so the live
book is *S3*, byte-for-byte, not a look-alike. Fidelity is by construction (11 §2).

Per-day flow (``process_day``), mirroring the engine loop (11 §3e):

    hydrate state from DB
      → §5e reconcile held positions into today's back-adjustment anchor
      → step_day(ctx, state, D)            # EXECUTE prior queue → MTM → STOP → REBALANCE
      → persist state + the new pending-fills queue + last_processed_date

The §5e reconcile runs BEFORE ``step_day`` so a moving-anchor corporate action on a
held name cannot falsely trip the daily catastrophic stop inside 5.iii (11 §5e).

Month-end / rebalance detection uses ``ctx.rebalance_dates`` (the last trading day of
each month in the *stored* trading calendar). ``_month_end_dates`` marks day D a
month-end iff D is the max date of its (year, month) group — which is only trustworthy
once a *later* trading day exists in the frame. Live, the stored frame ends at the
latest published bhavcopy, so its trailing day is an UNCONFIRMED month-end and would
falsely rebalance every single day. ``confirmed_replay_days`` (P11.2 §4c, holiday-proof)
resolves this by holding the trailing edge back until its successor confirms it: the
book trails one trading day in wall-clock, but every decision/fill is byte-identical to
the backtest and to the ordered-backfill path (paper replay is fidelity-neutral, §7.2).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from app.backtest_v2 import engine
from app.backtest_v2.costs import CostLevel
from app.backtest_v2.portfolio import Portfolio
from app.backtest_v2.schemas import DailySnapshot, Fill, Position
from app.db.models import PaperV2PendingFill, PaperV2Portfolio, PaperV2Position
from app.paper_v2 import s3_config
from app.paper_v2.ca_reconcile import reconcile_position

log = logging.getLogger(__name__)


@dataclass
class ProcessReport:
    """What happened on one processed trading day — drives alerts and the audit log."""

    process_date: date
    skipped: bool = False  # already processed (idempotency guard)
    is_rebalance: bool = False
    snapshot: DailySnapshot | None = None
    fills_executed: list[Fill] = field(default_factory=list)  # applied at today's open
    queued: list[Fill] = field(default_factory=list)  # next-open orders queued today
    reconciled_isins: list[str] = field(default_factory=list)  # §5e rescaled today


# ---------------------------------------------------------------------------
# Context (S3 brain over the stored history)
# ---------------------------------------------------------------------------


def build_live_context(
    prices: pd.DataFrame,
    index_prices: pd.Series | None,
    *,
    cost_level: CostLevel = "base",
) -> tuple[engine.EngineContext, list[pd.Timestamp]]:
    """Build the S3 engine context + calendar over the full stored ``prices`` frame.

    Identical wiring to the consumed FINAL_OOS run (s3_config), so ``step_day`` makes
    the same decisions the backtest would. ``date_from/date_to`` are left open so the
    calendar/pivots span the full stored history (the live shell steps a single day).
    """
    v3cfg = s3_config.make_s3_v3config()
    eng_cfg = s3_config.make_s3_engine_cfg(v3cfg)
    ss = s3_config.build_s3_signal_store(prices, v3cfg)
    return engine.build_context(
        prices,
        eng_cfg,
        index_prices=index_prices,
        cost_level=cost_level,
        signal_store=ss,
    )


# ---------------------------------------------------------------------------
# Forward-aware replay window (11 §4c) — holiday-proof month-end confirmation
# ---------------------------------------------------------------------------


def confirmed_replay_days(
    calendar: list[date | pd.Timestamp],
    last_processed: date | None,
    target: date,
) -> list[date]:
    """The unprocessed trading days whose month-end status is FINAL (11 §4c).

    A day D's rebalance status is final only once a *later* trading day exists in the
    stored frame: ``_month_end_dates`` flags D a month-end iff D is the max date of its
    (year, month) group, and that is trustworthy only when D has a successor. Live, the
    stored frame ends at the latest published bhavcopy, so its **trailing day is an
    unconfirmed month-end** — processed as-is it would fire a false rebalance every day
    of the trailing month (the blocker this resolves).

    The holiday-proof fix (no future trading calendar exists in the repo — the bhavcopy
    pipeline only skips weekends and tolerates holiday gaps): **hold the trailing edge
    back** until a later stored day confirms it. The book trails one trading day in
    wall-clock, but the held-back day is processed on the next run with the SAME
    information set (decision from data ≤ D, fill at D+1's open), so it is byte-identical
    to the backtest and to the ordered-backfill path — paper replay is fidelity-neutral
    (§7.2). For a historical replay (``target`` well before the frame's end) nothing is
    held back: every day ≤ target already has a successor.

    Returns the ascending dates D with ``last_processed < D ≤ target`` and
    ``D < max(calendar)`` (the trailing edge excluded).
    """
    if not calendar:
        return []
    days = sorted(_to_date(d) for d in calendar)
    trailing_edge = days[-1]  # unconfirmed: no successor in the stored frame yet
    return [
        d
        for d in days
        if d < trailing_edge
        and d <= target
        and (last_processed is None or d > last_processed)
    ]


# The single forward S3 paper book (11 §1). One row, created cash-only at inception; the
# warm-start replay (inception → confirmed edge) then brings it to today's S3 holdings,
# after which the counted forward months accrue (P11.2). Its cash default equals the
# engine ``starting_capital`` (1e6) so the monthly shadow re-derivation (parity) matches.
PROBATION_BOOK_NAME = "s3_probation"


def get_or_create_book(session: Session) -> PaperV2Portfolio:
    """Idempotently fetch (or create cash-only) the S3 probation paper book (11 §1).

    Created with the model defaults (starting_capital == cash == 1e6 == the engine
    default), so the live book and the parity shadow start from the same capital.
    """
    pf = (
        session.query(PaperV2Portfolio)
        .filter(PaperV2Portfolio.name == PROBATION_BOOK_NAME)
        .one_or_none()
    )
    if pf is None:
        pf = PaperV2Portfolio(name=PROBATION_BOOK_NAME)
        session.add(pf)
        session.commit()
    return pf


# ---------------------------------------------------------------------------
# Persistence: DB ⇄ LoopState
# ---------------------------------------------------------------------------


def hydrate_state(session: Session, portfolio_id: int) -> engine.LoopState:
    """Reconstruct the in-memory LoopState (Portfolio + pending queue) from the DB.

    The pending fills are ordered by insertion id so the rehydrated queue preserves the
    engine's append order (5.i then sorts stably by side).
    """
    pf = session.get(PaperV2Portfolio, portfolio_id)
    if pf is None:
        raise ValueError(f"paper_v2 portfolio {portfolio_id} not found")

    portfolio = Portfolio(cash=pf.cash)
    rows = (
        session.query(PaperV2Position)
        .filter(PaperV2Position.portfolio_id == portfolio_id)
        .all()
    )
    portfolio.positions = {
        r.isin: Position(
            isin=r.isin,
            symbol=r.symbol,
            shares=r.shares,
            cost_basis=r.cost_basis,
            entry_date=r.entry_date,
            last_price=r.last_price if r.last_price is not None else r.cost_basis,
        )
        for r in rows
    }

    pending = (
        session.query(PaperV2PendingFill)
        .filter(
            PaperV2PendingFill.portfolio_id == portfolio_id,
            PaperV2PendingFill.status == "pending",
        )
        .order_by(PaperV2PendingFill.id)
        .all()
    )
    pending_fills = [
        Fill(
            isin=p.isin,
            symbol=p.symbol,
            side=p.side,
            qty=p.qty,
            # Decision-close price: required for buys (target notional = qty×price)
            # and harmless for sells/trims (their qty is fixed; step_day 5.i restamps
            # the execution price to next-open). 0.0 only if a legacy row lacks it.
            price=p.decision_price if p.decision_price is not None else 0.0,
            date=p.decision_date,
            cost_rupees=0.0,
        )
        for p in pending
    ]

    return engine.LoopState(
        portfolio=portfolio,
        pending_fills=pending_fills,
        rebalance_dates_used=[],
        per_rebalance_turnover=[],
    )


def _adj_factor_at(prices: pd.DataFrame, isin: str, entry_date: date) -> float | None:
    """Back-adjustment factor for ``isin`` at its entry-date row (or the last row on or
    before it). Used by §5e to detect a moving anchor on a held name."""
    sub = prices[
        (prices["isin"] == isin) & (prices["date"] <= pd.Timestamp(entry_date))
    ]
    if sub.empty or "adj_factor" not in sub.columns:
        return None
    return float(sub.sort_values("date").iloc[-1]["adj_factor"])


def reconcile_held_positions(
    state: engine.LoopState,
    db_factors: dict[str, float],
    prices: pd.DataFrame,
) -> list[str]:
    """§5e — rescale every held position whose back-adjustment anchor moved since the
    last append, BEFORE the daily stop check. Returns the ISINs actually rescaled.

    ``db_factors`` maps isin → the ``last_adj_factor`` persisted for that held name. The
    new factor is read at the position's entry date from the freshly-appended ``prices``.
    Delegates the arithmetic to the P11.0-gated ``reconcile_position`` (Rule 5).
    """
    rescaled: list[str] = []
    new_positions: dict[str, Position] = {}
    for isin, pos in state.portfolio.positions.items():
        new_factor = _adj_factor_at(prices, isin, pos.entry_date)
        old_factor = db_factors.get(isin)
        if new_factor is None or old_factor is None:
            new_positions[isin] = pos
            continue
        rec = reconcile_position(pos.cost_basis, pos.shares, old_factor, new_factor)
        if rec.rescaled:
            rescaled.append(isin)
            log.info(
                "§5e reconcile %s: factor %.6f→%.6f (r=%.6f) cost_basis %.4f→%.4f",
                isin,
                old_factor,
                new_factor,
                rec.factor_ratio,
                pos.cost_basis,
                rec.cost_basis,
            )
        new_positions[isin] = Position(
            isin=pos.isin,
            symbol=pos.symbol,
            shares=rec.shares,
            cost_basis=rec.cost_basis,
            entry_date=pos.entry_date,
            last_price=pos.last_price,
        )
    state.portfolio.positions = new_positions
    return rescaled


def persist_state(
    session: Session,
    portfolio_id: int,
    state: engine.LoopState,
    process_date: date,
    prices: pd.DataFrame,
    executed: list[Fill],
    is_rebalance: bool,
) -> None:
    """Write the post-step LoopState back to the DB: cash, positions (+ refreshed
    ``last_adj_factor`` for §5e), the executed fills (mark prior queue ``filled``), and
    the new pending-fills queue. ``last_processed_date`` advances the replay clock."""
    pf = session.get(PaperV2Portfolio, portfolio_id)
    pf.cash = state.portfolio.cash
    pf.last_processed_date = process_date

    # ---- positions: replace the persisted set with the live set ----
    existing = {
        r.isin: r
        for r in session.query(PaperV2Position).filter(
            PaperV2Position.portfolio_id == portfolio_id
        )
    }
    live_isins = set(state.portfolio.positions)
    for isin, row in existing.items():
        if isin not in live_isins:
            session.delete(row)
    for isin, pos in state.portfolio.positions.items():
        factor = _adj_factor_at(prices, isin, pos.entry_date)
        row = existing.get(isin)
        if row is None:
            row = PaperV2Position(portfolio_id=portfolio_id, isin=isin)
            session.add(row)
        row.symbol = pos.symbol
        row.shares = pos.shares
        row.cost_basis = pos.cost_basis
        row.last_price = pos.last_price
        row.entry_date = pos.entry_date
        if factor is not None:
            row.last_adj_factor = factor

    # ---- queue: mark the prior pending rows filled, then insert the new queue ----
    prior = (
        session.query(PaperV2PendingFill)
        .filter(
            PaperV2PendingFill.portfolio_id == portfolio_id,
            PaperV2PendingFill.status == "pending",
        )
        .all()
    )
    exec_by_key: dict[tuple[str, str], Fill] = {(f.isin, f.side): f for f in executed}
    for p in prior:
        p.status = "filled"
        p.fill_date = process_date
        ex = exec_by_key.get((p.isin, p.side))
        if ex is not None:
            p.fill_price = ex.price
            p.cost_rupees = ex.cost_rupees

    reason = "rebalance" if is_rebalance else "catastrophic_stop"
    for f in state.pending_fills:
        session.add(
            PaperV2PendingFill(
                portfolio_id=portfolio_id,
                isin=f.isin,
                symbol=f.symbol,
                side=f.side,
                qty=f.qty,
                decision_price=f.price,
                reason=reason,
                decision_date=process_date,
                status="pending",
            )
        )


# ---------------------------------------------------------------------------
# The per-day entry point
# ---------------------------------------------------------------------------


def process_day(
    session: Session,
    portfolio_id: int,
    prices: pd.DataFrame,
    index_prices: pd.Series | None,
    process_date: date,
    *,
    cost_level: CostLevel = "base",
    commit: bool = True,
) -> ProcessReport:
    """Process ONE trading day for the S3 paper book (11 §3e/§4a/§4b).

    Idempotent (Rule: Pipeline Laws): a date ``<= last_processed_date`` is skipped. The
    decision/fill logic is ``engine.step_day`` verbatim; this function only feeds data,
    reconciles the anchor (§5e), and persists. Returns a ProcessReport for the alerter.
    """
    process_date = _to_date(process_date)
    pf = session.get(PaperV2Portfolio, portfolio_id)
    if pf is None:
        raise ValueError(f"paper_v2 portfolio {portfolio_id} not found")
    if pf.last_processed_date is not None and process_date <= pf.last_processed_date:
        log.info(
            "process_day: %s already processed (last=%s) — skipping (idempotent)",
            process_date,
            pf.last_processed_date,
        )
        return ProcessReport(process_date=process_date, skipped=True)

    ctx, _calendar = build_live_context(prices, index_prices, cost_level=cost_level)
    day_ts = pd.Timestamp(process_date)

    # Snapshot the persisted per-ISIN factors BEFORE hydrating (for §5e).
    db_factors = {
        r.isin: r.last_adj_factor
        for r in session.query(PaperV2Position).filter(
            PaperV2Position.portfolio_id == portfolio_id
        )
    }

    state = hydrate_state(session, portfolio_id)
    reconciled = reconcile_held_positions(state, db_factors, prices)

    engine.step_day(ctx, state, day_ts)

    is_rebalance = day_ts in ctx.rebalance_dates
    executed = list(state.portfolio.fills_log)  # fresh portfolio ⇒ today's fills only
    queued = list(state.pending_fills)
    snapshot = state.portfolio.snapshots[-1] if state.portfolio.snapshots else None

    persist_state(
        session, portfolio_id, state, process_date, prices, executed, is_rebalance
    )
    if commit:
        session.commit()
    else:
        session.flush()  # make writes visible to later same-session reads (tests)

    return ProcessReport(
        process_date=process_date,
        is_rebalance=is_rebalance,
        snapshot=snapshot,
        fills_executed=executed,
        queued=queued,
        reconciled_isins=reconciled,
    )


def _to_date(d: date | pd.Timestamp) -> date:
    return d.date() if isinstance(d, pd.Timestamp) else d
