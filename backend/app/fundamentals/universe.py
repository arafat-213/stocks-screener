"""
fundamentals.universe — TB2: populate the survivorship-free universe master.

The universe master (`fundamentals_universe`, TB1) is the spine the whole
Track-B layer hangs on: **one row per ISIN ever listed in-window** (~2017-01 →
2026-06), delisted/merged names included, with list/delist dates and exchange
(§3.1, problem §1.2). "Survivorship-free" means a name that stopped trading is
*retained* with its real trading window — never dropped because it no longer
exists today.

Two responsibilities live here:

  1. **Populate** the master from exchange listing/delisting records, idempotent
     + checkpointed (CLAUDE.md §1): re-running never duplicates an ISIN (ISIN is
     the PK) and resumes from the last successful ISIN after a crash. Per-ISIN
     failures log to `PipelineError` via `classify_error` and never crash the run.
  2. **Cross-check** the populated master against the v2 price layer's
     survivorship-free ISIN set: every ISIN the price layer carries MUST be
     representable here, else that name can never receive fundamentals and would
     be silently dropped from any Track-B factor. Missing ISINs are *surfaced*,
     not swallowed (Rule 12).

Source seam
-----------
The listing/delisting records arrive through an injectable ``ListingSource``
callable (CLAUDE.md §5: mock every exchange fetch in tests — pass a fixture
source). ``fetch_exchange_listings`` is the production seam; no concrete
NSE/BSE listings source is wired yet (the TB0.5 decision is NSE-only ≈2020 —
see ``00_PREREGISTRATION.md``), so it fails loud rather than fabricating data.
The populate logic is source-agnostic and fully test-gated against fixtures.
"""

from __future__ import annotations

import datetime
import json
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.data.bhavcopy import store
from app.db.models import PipelineCheckpoint, PipelineError
from app.fundamentals.models import FundamentalsUniverse
from app.pipeline.errors import classify_error

# Checkpoint phase name for the TB2 populate stage (one PipelineCheckpoint row
# per run_id+phase; `completed_symbols` holds the JSON array of done ISINs).
PHASE = "tb2_universe"


@dataclass(frozen=True)
class ListingRecord:
    """One exchange listing/delisting record — the populate input unit.

    ``delist_date is None`` means the ISIN was still listed at the end of the
    window: the survivorship-free "open window" flag.
    """

    isin: str
    name: str | None = None
    exchange: str | None = None  # TB0 §8.1 EXCHANGE_PRIORITY values: "NSE"/"BSE"
    list_date: datetime.date | None = None
    delist_date: datetime.date | None = None


# An injectable source of listing records. Tests pass a fixture; production
# passes `fetch_exchange_listings` (or whatever concrete source gets wired).
ListingSource = Callable[[], Iterable[ListingRecord]]


@dataclass
class PopulateStats:
    """Outcome of a populate run (surfaced, not logged-and-forgotten)."""

    total: int = 0
    inserted: int = 0
    updated: int = 0
    failed: int = 0
    skipped_checkpoint: int = 0


@dataclass
class CrossCheckReport:
    """Result of cross-checking the master against the v2 price universe."""

    price_universe_count: int
    master_count: int
    # Price-layer ISINs absent from the master — these would be silently dropped
    # from Track-B factors if not surfaced (Rule 12). Empty == clean.
    missing_from_master: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_from_master


def fetch_exchange_listings() -> Iterable[ListingRecord]:
    """Production listing/delisting source — NOT yet wired (fails loud, Rule 12).

    The TB0.5 feasibility decision is NSE-only with ``DISCOVERY_START`` ≈ 2020
    (``00_PREREGISTRATION.md``); the concrete NSE listings/delistings fetcher is
    a separate ingest-source task. Until it exists, callers must inject a real
    ``ListingSource`` explicitly — this stub refuses to fabricate a universe.
    """
    raise NotImplementedError(
        "No concrete exchange listings/delistings source is wired yet "
        "(TB0.5 = NSE-only ≈2020). Inject a ListingSource into "
        "populate_universe() — see app/fundamentals/universe.py."
    )


def _get_completed_isins(session: Session, run_id: str) -> set[str]:
    """ISINs already populated in this run (resume-after-crash, CLAUDE.md §1)."""
    checkpoint = (
        session.query(PipelineCheckpoint).filter_by(run_id=run_id, phase=PHASE).first()
    )
    if checkpoint and checkpoint.completed_symbols:
        try:
            return set(json.loads(checkpoint.completed_symbols))
        except Exception:
            return set()
    return set()


def _save_checkpoint(session: Session, run_id: str, completed: set[str]) -> None:
    checkpoint = (
        session.query(PipelineCheckpoint).filter_by(run_id=run_id, phase=PHASE).first()
    )
    if not checkpoint:
        checkpoint = PipelineCheckpoint(
            run_id=run_id,
            phase=PHASE,
            started_at=datetime.datetime.now(datetime.timezone.utc),
        )
        session.add(checkpoint)
    checkpoint.completed_symbols = json.dumps(sorted(completed))
    checkpoint.completed_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()


def _log_pipeline_error(
    session: Session, run_id: str, isin: str, exc: Exception
) -> None:
    """Log a per-ISIN failure; never let one name crash the run (CLAUDE.md §1)."""
    p_error = PipelineError(
        run_id=run_id,
        symbol=isin,
        phase=PHASE,
        error_type=classify_error(exc),
        message=str(exc),
        traceback=traceback.format_exc(),
    )
    session.add(p_error)
    session.commit()


def populate_universe(
    session: Session,
    source: ListingSource,
    run_id: str,
    *,
    resume: bool = True,
) -> PopulateStats:
    """Idempotently populate `fundamentals_universe` from a listing source.

    ISIN is the primary key, so re-running upserts the same rows — never a
    duplicate. ``resume=True`` skips ISINs already checkpointed for ``run_id``
    so a crashed run continues from the last successful ISIN. A per-ISIN failure
    is rolled back, logged to `PipelineError`, and the run continues (Rule 12 /
    CLAUDE.md §1). ``run_id`` must reference an existing `PipelineRun` (the run
    lifecycle + concurrency guard are owned by the orchestrator).
    """
    completed = _get_completed_isins(session, run_id) if resume else set()
    stats = PopulateStats()

    for rec in source():
        stats.total += 1
        if rec.isin in completed:
            stats.skipped_checkpoint += 1
            continue
        try:
            if not rec.isin:
                # A record with no ISIN can't key the master — a per-ISIN failure
                # (logged + skipped), never a silent or fatal one.
                raise ValueError("listing record has no ISIN; cannot key the master")
            existing = session.get(FundamentalsUniverse, rec.isin)
            is_update = existing is not None
            if is_update:
                # Idempotent upsert: refresh mutable fields; `updated_at` bumps
                # via the model's onupdate. ISIN identity is preserved.
                existing.name = rec.name
                existing.exchange = rec.exchange
                existing.list_date = rec.list_date
                existing.delist_date = rec.delist_date
            else:
                session.add(
                    FundamentalsUniverse(
                        isin=rec.isin,
                        name=rec.name,
                        exchange=rec.exchange,
                        list_date=rec.list_date,
                        delist_date=rec.delist_date,
                    )
                )
            session.commit()
        except Exception as exc:  # one bad ISIN must not crash the run
            session.rollback()
            stats.failed += 1
            _log_pipeline_error(session, run_id, rec.isin, exc)
            continue
        # Count only after the write durably committed.
        if is_update:
            stats.updated += 1
        else:
            stats.inserted += 1
        completed.add(rec.isin)
        _save_checkpoint(session, run_id, completed)

    return stats


def read_price_universe_isins(root: str | None = None) -> set[str]:
    """The v2 price layer's survivorship-free ISIN set (thin IO seam).

    Reads the price layer's ISIN→symbol map (one row per ISIN) — the literal set
    of ISINs the price layer carries. Kept separate from the pure cross-check
    function below so the latter is testable without touching Parquet/disk.
    """
    df = store.read_isin_symbol_map(root=root)
    return set(df["isin"].dropna().unique().tolist())


def cross_check_against_price_universe(
    session: Session, price_isins: set[str]
) -> CrossCheckReport:
    """Flag any price-layer ISIN absent from the master (Rule 12 — surface).

    Every ISIN the price layer carries must be representable in the master so the
    price and fundamentals layers join cleanly on ISIN; a missing one is reported,
    never silently dropped.
    """
    master = {row[0] for row in session.query(FundamentalsUniverse.isin).all()}
    missing = sorted(set(price_isins) - master)
    return CrossCheckReport(
        price_universe_count=len(set(price_isins)),
        master_count=len(master),
        missing_from_master=missing,
    )
