"""
TB8 — wiring-seam invariant tests for the 3 NEW seams (Rule 9: encode WHY).

TB8's heavy lifting is all reused, test-gated machinery (TB1–TB7).  The only NEW
code is the 3 seams that adapt that machinery to live data.  These tests pin the
two NON-OBVIOUS seam behaviours that a live run can't safely discover by itself:

1. ``membership_derived_listings`` correctly distinguishes a delisted name (its
   last-seen < panel end → ``delist_date`` set) from a still-listed name
   (last-seen == panel end → ``delist_date is None``).  Getting this wrong
   silently re-introduces survivorship bias (§1.2) — the whole point of the layer.
2. ``make_eligible_on_date`` weights by ``adv_20`` and its ``restrict_isins`` knob
   narrows the §6.1 denominator — and an uncovered eligible name STILL counts in
   the denominator (the weight-masking guard from the module docstring).
3. ``make_recon_reader`` re-parses the stored XBRL doc into the 4 reconciled items,
   and returns ``None`` when no document is on file (gate skips, not a mismatch).

No network, no live NSE — in-memory SQLite + injected fixtures (CLAUDE.md §5).
"""

from __future__ import annotations

import datetime
from unittest import mock

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base
from app.fundamentals.models import FundamentalsFilingIndex, FundamentalsUniverse
from app.fundamentals.tb8_ingest import (
    make_eligible_on_date,
    make_recon_reader,
    membership_derived_listings,
)

ISIN_LIVE = "INE002A01018"  # still trading through panel end
ISIN_DEAD = "INE999Z01099"  # delisted mid-window


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------------------
# Seam 1 — membership_derived_listings
# ---------------------------------------------------------------------------


def test_membership_derived_survivorship_window():
    """A name last seen before panel end is delisted; one seen at panel end is open.

    WHY: ``delist_date`` is the survivorship-free signal.  Marking a delisted name
    as still-open (or vice-versa) silently drops it from / keeps it wrongly in the
    factor universe for the dates it traded — the §1.2 bias this layer exists to kill.
    """
    panel_end = pd.Timestamp("2026-06-12")
    membership = pd.DataFrame(
        {
            "isin": [ISIN_LIVE, ISIN_LIVE, ISIN_DEAD, ISIN_DEAD],
            "date": [
                pd.Timestamp("2020-01-02"),
                panel_end,  # LIVE seen through the end → open window
                pd.Timestamp("2020-01-02"),
                pd.Timestamp("2021-08-20"),  # DEAD stops here → delisted
            ],
        }
    )
    symmap = pd.DataFrame(
        {
            "isin": [ISIN_LIVE, ISIN_DEAD],
            "symbol": ["RELIANCE", "DEADCO"],
            "first_date": [pd.Timestamp("2020-01-02")] * 2,
            "last_date": [panel_end, pd.Timestamp("2021-08-20")],
        }
    )
    with (
        mock.patch(
            "app.fundamentals.tb8_ingest.store.read_universe_membership",
            return_value=membership,
        ),
        mock.patch(
            "app.fundamentals.tb8_ingest.store.read_isin_symbol_map",
            return_value=symmap,
        ),
    ):
        records = {r.isin: r for r in membership_derived_listings()}

    assert records[ISIN_LIVE].delist_date is None  # still listed
    assert records[ISIN_LIVE].list_date == datetime.date(2020, 1, 2)
    assert records[ISIN_DEAD].delist_date == datetime.date(2021, 8, 20)  # delisted
    assert records[ISIN_DEAD].name == "DEADCO"  # latest symbol carried as name


# ---------------------------------------------------------------------------
# Seam 2 — make_eligible_on_date
# ---------------------------------------------------------------------------


def _prices_on(date: str, rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "isin": [r[0] for r in rows],
            "date": [pd.Timestamp(date)] * len(rows),
            "adv_20": [r[1] for r in rows],
            "close_raw": [100.0] * len(rows),
        }
    )


def test_eligible_weights_by_adv20_and_applies_floor():
    """adv_20 is the weight; names below the liquidity floor are excluded.

    WHY: the §6.1 denominator is the liquidity-eligible universe, weighted by a
    basis available for EVERY eligible name.  adv_20 is that basis (a name without
    fundamentals still has an adv_20), so the weight-coverage denominator is
    complete — a missing large name can't be masked.
    """
    floor = 5e7  # ₹5 cr
    prices = _prices_on(
        "2021-03-31",
        [("A", 9e7), ("B", 6e7), ("C", 1e7)],  # C below floor
    )
    eligible = make_eligible_on_date(prices, floor)(datetime.date(2021, 3, 31))
    got = dict(eligible)
    assert set(got) == {"A", "B"}  # C excluded by the floor
    assert got["A"] == 9e7 and got["B"] == 6e7  # weighted by adv_20, not 1.0


def test_eligible_restrict_isins_narrows_denominator():
    """``restrict_isins`` (smoke) narrows the eligible set to the ingested subset.

    WHY: in smoke mode only a handful of ISINs are ingested; without restricting
    the denominator the coverage % would read ~0% against the full eligible
    universe and the smoke would be meaningless.
    """
    floor = 5e7
    prices = _prices_on("2021-03-31", [("A", 9e7), ("B", 6e7)])
    eligible = make_eligible_on_date(prices, floor, restrict_isins={"A"})(
        datetime.date(2021, 3, 31)
    )
    assert dict(eligible) == {"A": 9e7}  # B dropped though it clears the floor


# ---------------------------------------------------------------------------
# Seam 3 — make_recon_reader
# ---------------------------------------------------------------------------


def test_recon_reader_reparses_stored_doc(session):
    """The recon reader re-parses the stored XBRL doc into the 4 reconciled items.

    WHY: §6.5 diffs the stored row against an independently-recomputed reference.
    Re-parsing the stored ``document_url`` catches a corrupted/stale stored row or
    a parser drift since ingest.
    """
    session.add(FundamentalsUniverse(isin=ISIN_LIVE, exchange="NSE"))
    session.add(
        FundamentalsFilingIndex(
            isin=ISIN_LIVE,
            period_end=datetime.date(2022, 3, 31),
            available_date=datetime.date(2022, 5, 10),
            statement_type="Annual",
            source_exchange="NSE",
            document_url="https://nse/doc.xml",
        )
    )
    session.commit()

    xbrl = (
        '<xbrl xmlns:in-bse-fin="http://www.in-bse-fin.org">'
        "<in-bse-fin:RevenueFromOperations>1000</in-bse-fin:RevenueFromOperations>"
        "<in-bse-fin:ProfitLossForPeriod>120</in-bse-fin:ProfitLossForPeriod>"
        "<in-bse-fin:Equity>500</in-bse-fin:Equity>"
        "<in-bse-fin:Assets>800</in-bse-fin:Assets>"
        "</xbrl>"
    )
    reader = make_recon_reader(session, fetcher=lambda url: xbrl)
    out = reader([(ISIN_LIVE, datetime.date(2022, 3, 31))])
    ref = out[(ISIN_LIVE, datetime.date(2022, 3, 31))]
    assert ref == {
        "revenue": 1000.0,
        "net_income": 120.0,
        "total_equity": 500.0,
        "total_assets": 800.0,
    }


def test_recon_reader_none_when_no_document(session):
    """No stored filing with a document → reference is None (gate skips, not a fail).

    WHY: unavailability is not a reconciliation mismatch; the gate must skip it.
    """
    reader = make_recon_reader(session, fetcher=lambda url: "")
    out = reader([(ISIN_LIVE, datetime.date(2022, 3, 31))])
    assert out[(ISIN_LIVE, datetime.date(2022, 3, 31))] is None
