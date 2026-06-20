"""
test_v3tbe5b_leverage_rescue.py — TBE5b done-criteria.

TBE5b rescues the leverage factor by adding a fallback to the disclosed
DebtEquityRatio XBRL tag when total_debt is NULL (results-only filings carry
the ratio but no balance-sheet borrowings).

Done-criteria:
  [DC1] Fallback path: total_debt absent + debt_equity_ratio present → -ratio
        WHY: results-only filings (the bulk of DISCOVERY) carry DebtEquityRatio
        but no Borrowings — without the fallback, leverage is NULL for ~78% of
        eligible names and the quality block loses most of its signal.
  [DC2] Primary path unchanged: total_debt present → -(total_debt/equity)
        WHY: balance-sheet borrowings remain authoritative when available; the
        fallback must not override a more-precise computed value.
  [DC3] Negative disclosed ratio → None
        WHY: D/E < 0 implies negative equity or a filing error; non-positive
        equity already returns None in the equity guard, so consistency requires
        the ratio path to behave identically (03 §4.3 degenerate rule).
  [DC4] Zero ratio → 0.0 (zero-debt company, valid)
        WHY: a zero-debt company is the best leverage score (highest rank);
        returning None would incorrectly exclude them from the quality signal.
  [DC5] Financial exclusion still applies before any ratio lookup
        WHY: 03 §3 exempts banks/NBFCs from leverage regardless of data source.
  [DC6] DebtEquityRatio tag parsed from XBRL text (parser layer)
        WHY: the tag must be correctly extracted by parse_xbrl to reach the DB.
  [DC7] Absent DebtEquityRatio tag → None in XBRLParseResult (no zero-fill)
        WHY: Rule 12 — a missing disclosure must not be silently treated as zero.
  [DC8] Absent ratio + absent total_debt → None (both sources missing)
        WHY: no information means no signal; the factor must not guess.
"""

from __future__ import annotations

import datetime

import pytest

from app.backtest_v2.fundamental_factors import leverage
from app.fundamentals.reader import FundamentalsSnapshot
from app.fundamentals.xbrl_parser import XBRLParseResult, parse_xbrl

_BASE = datetime.date(2022, 1, 1)


# ---------------------------------------------------------------------------
# Snapshot helper (thin wrapper so tests stay readable)
# ---------------------------------------------------------------------------


def _snap(
    *,
    total_equity: float | None = 1000.0,
    total_debt: float | None = None,
    debt_equity_ratio: float | None = None,
    is_financial: bool = False,
    statement_type: str = "Annual",
) -> tuple[list[FundamentalsSnapshot], bool]:
    snap = FundamentalsSnapshot(
        isin="TEST",
        period_end=_BASE,
        available_date=_BASE + datetime.timedelta(days=60),
        statement_type=statement_type,
        net_income=None,
        cfo=None,
        total_equity=total_equity,
        total_assets=None,
        total_debt=total_debt,
        shares_outstanding=None,
        ebit=None,
        revenue=None,
        debt_equity_ratio=debt_equity_ratio,
    )
    return [snap], is_financial


# ---------------------------------------------------------------------------
# DC1 — fallback path (total_debt absent, debt_equity_ratio present)
# ---------------------------------------------------------------------------


class TestLeverageFallback:
    def test_fallback_engaged_when_total_debt_none(self):
        """D/E ratio used as fallback when total_debt is NULL (DC1)."""
        snaps, is_fin = _snap(total_debt=None, debt_equity_ratio=0.5)
        result = leverage(snaps, is_fin)
        assert result == pytest.approx(-0.5)

    def test_fallback_zero_ratio_returns_zero(self):
        """Zero D/E ratio (zero-debt company) → 0.0 (DC4)."""
        snaps, is_fin = _snap(total_debt=None, debt_equity_ratio=0.0)
        result = leverage(snaps, is_fin)
        assert result == pytest.approx(0.0)

    def test_fallback_high_leverage(self):
        """High D/E ratio (e.g. 2.5) → -2.5 (very levered → low rank) (DC1)."""
        snaps, is_fin = _snap(total_debt=None, debt_equity_ratio=2.5)
        result = leverage(snaps, is_fin)
        assert result == pytest.approx(-2.5)


# ---------------------------------------------------------------------------
# DC2 — primary path unchanged
# ---------------------------------------------------------------------------


class TestLeveragePrimaryPath:
    def test_primary_path_when_total_debt_present(self):
        """total_debt/equity used when total_debt is present (DC2)."""
        snaps, is_fin = _snap(total_debt=400.0, total_equity=1000.0)
        result = leverage(snaps, is_fin)
        assert result == pytest.approx(-0.4)

    def test_primary_path_overrides_fallback_when_both_present(self):
        """total_debt takes precedence over debt_equity_ratio when both available (DC2)."""
        # total_debt/equity = 400/1000 = 0.4; ratio = 0.9 (different)
        snaps, is_fin = _snap(
            total_debt=400.0, total_equity=1000.0, debt_equity_ratio=0.9
        )
        result = leverage(snaps, is_fin)
        # Must use primary path: -(400/1000) = -0.4, not -0.9
        assert result == pytest.approx(-0.4)


# ---------------------------------------------------------------------------
# DC3 — negative disclosed ratio → None
# ---------------------------------------------------------------------------


class TestLeverageNegativeRatio:
    def test_negative_ratio_returns_none(self):
        """Negative D/E ratio is a filing error → None (DC3)."""
        snaps, is_fin = _snap(total_debt=None, debt_equity_ratio=-0.3)
        result = leverage(snaps, is_fin)
        assert result is None

    def test_negative_ratio_not_zero_filled(self):
        """Negative ratio must not be treated as zero — it's a data error (DC3/Rule 12)."""
        snaps, is_fin = _snap(total_debt=None, debt_equity_ratio=-1.0)
        result = leverage(snaps, is_fin)
        assert result is None  # NOT 0.0 and NOT 1.0


# ---------------------------------------------------------------------------
# DC5 — financial exclusion
# ---------------------------------------------------------------------------


class TestLeverageFinancialExclusion:
    def test_financial_isin_returns_none_even_with_ratio(self):
        """Financial exclusion applies before ratio lookup (DC5)."""
        snaps, _ = _snap(total_debt=None, debt_equity_ratio=0.5)
        result = leverage(snaps, is_financial=True)
        assert result is None

    def test_financial_isin_returns_none_even_with_total_debt(self):
        """Financial exclusion applies even when total_debt is present (DC5)."""
        snaps, _ = _snap(total_debt=200.0, debt_equity_ratio=0.2)
        result = leverage(snaps, is_financial=True)
        assert result is None


# ---------------------------------------------------------------------------
# DC8 — both sources absent → None
# ---------------------------------------------------------------------------


class TestLeverageBothAbsent:
    def test_none_when_both_total_debt_and_ratio_absent(self):
        """No fallback data at all → None (DC8)."""
        snaps, is_fin = _snap(total_debt=None, debt_equity_ratio=None)
        result = leverage(snaps, is_fin)
        assert result is None

    def test_non_positive_equity_still_none_even_with_ratio(self):
        """Non-positive equity → None regardless of ratio availability (03 §4.3)."""
        snaps, is_fin = _snap(total_equity=0.0, total_debt=None, debt_equity_ratio=0.5)
        result = leverage(snaps, is_fin)
        assert result is None

    def test_negative_equity_still_none(self):
        """Negative equity → None regardless of ratio (03 §4.3)."""
        snaps, is_fin = _snap(
            total_equity=-500.0, total_debt=None, debt_equity_ratio=0.5
        )
        result = leverage(snaps, is_fin)
        assert result is None


# ---------------------------------------------------------------------------
# DC6 — parse_xbrl extracts DebtEquityRatio tag correctly
# ---------------------------------------------------------------------------

_XBRL_WITH_RATIO = """<?xml version="1.0"?>
<xbrl xmlns:in-bse-fin="http://www.bseindia.com/in-bse-fin">
  <in-bse-fin:DebtEquityRatio contextRef="OneD" unitRef="pure" decimals="INF">0.45</in-bse-fin:DebtEquityRatio>
  <in-bse-fin:ProfitLossForPeriod contextRef="OneD" unitRef="INR" decimals="0">50000</in-bse-fin:ProfitLossForPeriod>
</xbrl>"""

_XBRL_WITHOUT_RATIO = """<?xml version="1.0"?>
<xbrl xmlns:in-bse-fin="http://www.bseindia.com/in-bse-fin">
  <in-bse-fin:ProfitLossForPeriod contextRef="OneD" unitRef="INR" decimals="0">50000</in-bse-fin:ProfitLossForPeriod>
</xbrl>"""


class TestXBRLParserDebtEquityRatio:
    def test_parser_extracts_ratio_when_present(self):
        """parse_xbrl extracts DebtEquityRatio into debt_equity_ratio field (DC6)."""
        result = parse_xbrl(_XBRL_WITH_RATIO)
        assert result.debt_equity_ratio == pytest.approx(0.45)

    def test_parser_returns_none_when_ratio_absent(self):
        """parse_xbrl returns None for debt_equity_ratio when tag is absent (DC7)."""
        result = parse_xbrl(_XBRL_WITHOUT_RATIO)
        assert result.debt_equity_ratio is None

    def test_ratio_absence_not_in_unmapped_items(self):
        """Absent DebtEquityRatio is NOT logged as unmapped — it's a supplementary field (DC7)."""
        result = parse_xbrl(_XBRL_WITHOUT_RATIO)
        assert "debt_equity_ratio" not in result.unmapped_items

    def test_ratio_presence_does_not_affect_unmapped_items(self):
        """DebtEquityRatio presence is never listed in unmapped_items either (DC6)."""
        result = parse_xbrl(_XBRL_WITH_RATIO)
        assert "debt_equity_ratio" not in result.unmapped_items

    def test_zero_ratio_parsed_correctly(self):
        """Zero D/E ratio (zero-debt company) parses to 0.0, not None (DC4 at parser level)."""
        xbrl = _XBRL_WITH_RATIO.replace("0.45", "0.00")
        result = parse_xbrl(xbrl)
        assert result.debt_equity_ratio == pytest.approx(0.0)

    def test_xbrlparseresult_has_debt_equity_ratio_field(self):
        """XBRLParseResult dataclass has debt_equity_ratio field (schema guard)."""
        r = XBRLParseResult()
        assert hasattr(r, "debt_equity_ratio")
        assert r.debt_equity_ratio is None
