"""T07.1 — classify liquid terminated-no-successor ISINs by sub-type.

A *termination* is an ISIN that stops trading well before the store edge with no
face-value successor (``06`` stitches those onto one ``instrument_id``). A held
position in such a name has no forward price → it is carried as an MTM-frozen ghost
(``07`` §1). This module is a **read-only audit**: it reproduces the blast-radius
liquid set (``scripts/merger_ghost_blast_radius.py`` / ``07`` §3) and partitions it
into the four ``07`` sub-types so a cold session — and ``validate.py`` (T07.4) —
can reason about each.

The hard constraint (``07`` §5): the persisted CA feed carries only
split/dividend/bonus — **no merger / amalgamation / delisting event** — and the
free-text ``ca_unmatched`` "Scheme of Arrangement" rows do **not** cover the actual
merged names (HDFC, INOXLEISUR, TATAMTRDVR have none). So sub-type is *not*
authoritatively derivable from on-disk data. We therefore classify in two tiers:

  * **curated** — a small seed of fates already *documented in ``07`` §3* (in-repo
    knowledge / public record). Authoritative; carries the acquirer where known.
  * **heuristic** — data-derived inference for the rest, from two clean axes the
    data *does* give:
      - ``last_peak_ratio`` (last close ÷ all-time peak close): value **destroyed**
        (< 0.5) ⇒ delisting/insolvency; value **preserved** ⇒ merger/acquisition
        (the holder's value migrated to an acquirer, unconfirmed without §5 data).
      - a shared ``last_date`` cluster near the edge ⇒ a data-ingest gap, not a
        real delisting (real delistings do not co-occur on one calendar day for
        dozens of names). This resolves the §3 2026-05-18 false-positive cluster.
      - the ``DVR`` symbol suffix ⇒ a differential-voting-rights cancellation.

``confidence`` is recorded on every row so no heuristic guess is mistaken for fact
(Rule 12). No external data is fetched; no engine state is mutated.
"""

from __future__ import annotations

import pandas as pd

# Sub-type labels (mirror 07 §3's four buckets).
MERGER = "merger"
CANCELLATION = "cancellation"
DELISTING_INSOLVENCY = "delisting_insolvency"
DATA_GAP_SUSPECT = "data_gap_suspect"

# Thresholds (all overridable for tests).
LIQUIDITY_FLOOR = 5e7  # ₹5cr — the S3 liquidity floor (06 §11); adv_20 is in rupees.
TERM_CUTOFF_DAYS = 15  # last trade > this many days before edge ⇒ terminated (07 §3).
DATA_GAP_NEAR_EDGE_DAYS = 60  # a "termination" this close to the edge is gap-suspect.
DATA_GAP_MIN_CLUSTER = 5  # ...if >= this many ISINs share its exact last_date.
INSOLVENCY_PEAK_RATIO = 0.5  # last close < half the peak ⇒ value destroyed.

# Curated fates documented in 07 §3 (and the 3 T06.5 ghosts). Authoritative; the
# acquirer string is the destination named in §3 (informational — approach-A
# write-off does not need it; approach-B remap is data-gated & out of scope).
# Keyed by the dead ISIN.
KNOWN_FATES: dict[str, tuple[str, str]] = {
    "INE001A01036": (MERGER, "HDFCBANK"),  # HDFC → HDFC Bank (share swap, 2023)
    "INE312H01016": (MERGER, "PVRINOX"),  # INOXLEISUR → PVR INOX (share swap, 2023)
    "IN9155A01020": (CANCELLATION, ""),  # TATAMTRDVR — DVR shares cancelled (2024)
    "INE018I01017": (MERGER, "LTIMINDTREE"),  # MINDTREE → LTIMindtree
    "INE043D01016": (MERGER, "IDFCFIRSTB"),  # IDFC → IDFC First Bank
    "INE264A01014": (MERGER, "HINDUNILVR"),  # GSKCONS → HUL
    "INE180K01011": (MERGER, "INDUSINDBK"),  # BHARATFIN → IndusInd
    "INE580B01029": (MERGER, "BANDHANBNK"),  # GRUH → Bandhan
    "INE910H01017": (MERGER, "VEDL"),  # CAIRN → Vedanta
    "INE069A01017": (MERGER, "GRASIM"),  # ABIRLANUVO → Grasim
    "INE824B01021": (MERGER, "TATASTEEL"),  # TATASTLBSL → Tata Steel
    "INE334L01012": (MERGER, "UJJIVANSFB"),  # UJJIVAN → Ujjivan SFB
    "INE802G01018": (DELISTING_INSOLVENCY, ""),  # JETAIRWAYS — insolvency
    "INE455F01025": (DELISTING_INSOLVENCY, ""),  # JPASSOCIAT — insolvency
}


def classify_terminations(
    prices: pd.DataFrame,
    successor_map: pd.DataFrame | None = None,
    *,
    edge: pd.Timestamp | None = None,
    liquidity_floor: float = LIQUIDITY_FLOOR,
    term_cutoff_days: int = TERM_CUTOFF_DAYS,
) -> pd.DataFrame:
    """Return the liquid terminated-no-successor set, classified by sub-type.

    Mirrors ``merger_ghost_blast_radius.py`` for set selection (07 §3): per-ISIN
    lifetimes from ``prices``; terminated = last trade > ``term_cutoff_days`` before
    the edge; exclude asserted-succession old legs and any chain still trading at
    the edge; keep liquid-at-death (adv on the last day >= ``liquidity_floor``).
    Columns match ``store.TERMINATIONS_SCHEMA``.
    """
    p = prices.copy()
    p["date"] = pd.to_datetime(p["date"])
    if edge is None:
        edge = p["date"].max()
    term_cutoff = edge - pd.Timedelta(days=term_cutoff_days)

    life = p.groupby("isin").agg(
        symbol=("symbol", "last"),
        last_date=("date", "max"),
        instrument_id=("instrument_id", "last"),
    )
    last_rows = p.sort_values("date").groupby("isin").tail(1).set_index("isin")
    life["adv_last"] = last_rows["adv_20"]
    # Value-destroyed signal: last raw close vs the ISIN's all-time peak raw close.
    peak = p.groupby("isin")["close_raw"].max()
    last_close = last_rows["close_raw"]
    life["last_peak_ratio"] = (last_close / peak).where(peak > 0)

    asserted_old: set[str] = set()
    if successor_map is not None and not successor_map.empty:
        asserted_old = set(successor_map.loc[successor_map["asserted"], "old_isin"])
    alive_iids = set(p.loc[p["date"] >= term_cutoff, "instrument_id"])

    term = life[life["last_date"] < term_cutoff].copy()
    # cluster_size over ALL terminations (before the succession/alive filters): a
    # shared last_date across many names is the ingest-gap fingerprint.
    cluster = term.groupby("last_date")["symbol"].transform("size")
    term["cluster_size"] = cluster.astype("int64")

    term = term[~term.index.isin(asserted_old)]
    term = term[~term["instrument_id"].isin(alive_iids)]
    liquid = term[term["adv_last"] >= liquidity_floor].copy()

    liquid = liquid.reset_index().rename(columns={"index": "isin"})
    liquid["days_before_edge"] = (edge - liquid["last_date"]).dt.days.astype("int64")

    rows = liquid.apply(lambda r: _classify_row(r, edge), axis=1, result_type="expand")
    liquid[["subtype", "confidence", "acquirer", "evidence"]] = rows

    cols = [
        "isin",
        "symbol",
        "instrument_id",
        "last_date",
        "adv_last",
        "last_peak_ratio",
        "days_before_edge",
        "cluster_size",
        "subtype",
        "confidence",
        "acquirer",
        "evidence",
    ]
    return liquid[cols].sort_values("adv_last", ascending=False).reset_index(drop=True)


def _classify_row(r: pd.Series, edge: pd.Timestamp) -> list:
    """Return ``[subtype, confidence, acquirer, evidence]`` for one terminated ISIN.

    Priority: curated seed > data-gap cluster > DVR cancellation > value-destroyed
    insolvency > value-preserved merger/acquisition. Data-gap is checked before the
    value heuristics so an ingest-gap name is never mislabelled a real event.
    """
    if r["isin"] in KNOWN_FATES:
        subtype, acquirer = KNOWN_FATES[r["isin"]]
        return [subtype, "curated", acquirer, "documented fate (07 §3)"]

    near_edge = r["days_before_edge"] <= DATA_GAP_NEAR_EDGE_DAYS
    if near_edge and r["cluster_size"] >= DATA_GAP_MIN_CLUSTER:
        return [
            DATA_GAP_SUSPECT,
            "heuristic",
            "",
            f"last_date shared by {int(r['cluster_size'])} ISINs, "
            f"{int(r['days_before_edge'])}d before edge — ingest-gap signature",
        ]

    if str(r["symbol"]).upper().endswith("DVR"):
        return [
            CANCELLATION,
            "heuristic",
            "",
            "DVR symbol — differential-voting cancellation",
        ]

    ratio = r["last_peak_ratio"]
    if pd.notna(ratio) and ratio < INSOLVENCY_PEAK_RATIO:
        return [
            DELISTING_INSOLVENCY,
            "heuristic",
            "",
            f"last close {ratio:.0%} of peak — value destroyed",
        ]

    return [
        MERGER,
        "heuristic",
        "",
        f"value-preserved termination (last {ratio:.0%} of peak); "
        "merger/voluntary-delisting inferred — no CA event (07 §5)",
    ]
