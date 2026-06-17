"""
data_config — the locked Track-B data-layer thresholds (TB0).

Field set is LOCKED to specs/v3/02_TRACK_B_DATA.md §8 ("Locked decisions,
Arafat 2026-06-17 — pre-committed before any ingest"). These constants are
transcribed VERBATIM from the spec and frozen BEFORE any ingest so no later
session can tune the §6 data-acceptance gate (TB7) to whatever the ingest
happens to yield — the v1 data-mining sin applied to data.

TB7 reads these and MAY NOT introduce a new or loosened threshold (Rule 12).
Changing any value here requires re-opening §8 of the spec, not a code edit.
"""

from __future__ import annotations

from datetime import date

# ---------------------------------------------------------------------------
# §8.1 — Exchange priority & dedup: NSE-primary, BSE fallback
# ---------------------------------------------------------------------------
# NSE's filing is canonical per ISIN-period; BSE is read ONLY where NSE has no
# record. First element is canonical; the rest are fallbacks, in order. No
# cross-exchange reconciliation in this build.
#
# Escalation (NOT HARKing): if TB7's by-name floor fails specifically due to
# BSE-only gaps, upgrading to full both-exchange ingest is a sanctioned remedy —
# it pulls more INPUT against an UNCHANGED threshold, so it does not move the
# measuring stick.
EXCHANGE_PRIORITY: tuple[str, ...] = ("NSE", "BSE")

# ---------------------------------------------------------------------------
# §8.2 — Coverage gate (dual; BOTH must hold) — §6.1
# ---------------------------------------------------------------------------
# The weight floor certifies large-cap coverage; the by-name floor guards
# breadth so a cap-heavy/name-thin panel (which would pass weight-only) fails
# here rather than silently crippling the de-concentrated portfolio Track B
# exists to test. 75% by name (not higher) tolerates the sparse SME filing tail.
# Denominator is pinned in TB7 to the liquidity-eligible DISCOVERY universe
# (names passing the v2 entry-gate adv_20 floor) — NOT raw universe_membership.
COVERAGE_THRESHOLD_WEIGHT: float = 0.90  # ≥ 90% by market-cap weight
COVERAGE_THRESHOLD_NAME: float = 0.75  # AND ≥ 75% by name

# ---------------------------------------------------------------------------
# §8.3 — Reconciliation spot-audit — §6.5
# ---------------------------------------------------------------------------
# Enough samples to catch systematic parse / tag-mapping errors; ±2% absorbs
# rounding/units noise without hiding a real mismatch.
RECON_SAMPLE_N: int = 30  # random ISIN-quarters
RECON_TOLERANCE: float = 0.02  # ±2% per line item

# ---------------------------------------------------------------------------
# §8.4 — Safety lag (zero look-ahead insurance) — §3.5
# ---------------------------------------------------------------------------
# The as-of reader serves a filing only once available_date <= D − lag.
# Revised up from the initially-chosen 1 day on review: fundamentals are
# quarterly so the extra day's staleness is immaterial, while the second day is
# cheap insurance against available_date timestamp imprecision (date-only
# stamps, dissemination lag). Zero look-ahead is the entire reason this layer
# exists (the v1 yfinance ban, §1.1).
SAFETY_LAG_TRADING_DAYS: int = 2

# ---------------------------------------------------------------------------
# §8.5 — Restatement policy — §3.4
# ---------------------------------------------------------------------------
# Keep EVERY version keyed by available_date; the reader returns the latest
# version with available_date <= D − lag. "As of latest version known" at the
# decision date — never a single overwritten figure.
RESTATEMENT_POLICY: str = "as-of-latest-version-known"

# ---------------------------------------------------------------------------
# §8.6 — Scope cap: historical PIT panel only (no live / daily refresh)
# ---------------------------------------------------------------------------
# Target is the DISCOVERY panel + the one-shot FINAL_OOS window — nothing live.
SCOPE: str = "historical-panel-only"

# ---------------------------------------------------------------------------
# Panel start — in-window start for TTM lookback (TB0 "Do")
# ---------------------------------------------------------------------------
# Ingest must reach back far enough before DISCOVERY (2018-02-06) that a
# trailing-twelve-month fundamentals window is fully populated at the first
# rebalance — i.e. ~2017-01. Not a §8 threshold; a lookback boundary.
PANEL_START: date = date(2017, 1, 1)
