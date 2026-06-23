"""Email alerts for the S3 paper book (11 §4a/§4b).

Reuses v1's clean ``send_alert_email`` transport (Resend) — the one v1 utility the
prereg blesses as a drop-in (11 §2) — but builds v2-native HTML bodies from a
``ProcessReport``. No alert is a control signal; these are operator notifications.

Three alert kinds:
  * stop alert      — a catastrophic stop was queued today (daily job, §4a.4).
  * rebalance preview — month-end queued buys/sells/trims for next-open (§4b.4).
  * fill confirmation — the prior session's queue executed at today's open (§4b).
"""

from __future__ import annotations

import logging

from app.alerts.email import send_alert_email
from app.paper_v2.live_engine import ProcessReport

log = logging.getLogger(__name__)


def _rows(fills) -> str:
    if not fills:
        return '<tr><td colspan="4" style="padding:6px;color:#888">none</td></tr>'
    out = []
    for f in fills:
        out.append(
            "<tr>"
            f'<td style="padding:4px 8px">{f.symbol}</td>'
            f'<td style="padding:4px 8px">{f.side}</td>'
            f'<td style="padding:4px 8px;text-align:right">{f.qty:,.2f}</td>'
            f'<td style="padding:4px 8px;text-align:right">{f.isin}</td>'
            "</tr>"
        )
    return "".join(out)


def _table(title: str, fills) -> str:
    return (
        f'<h3 style="font-family:sans-serif">{title}</h3>'
        '<table style="border-collapse:collapse;font-family:sans-serif;font-size:13px">'
        '<tr style="background:#f0f0f0">'
        '<th style="padding:4px 8px;text-align:left">Symbol</th>'
        '<th style="padding:4px 8px;text-align:left">Side</th>'
        '<th style="padding:4px 8px;text-align:right">Qty</th>'
        '<th style="padding:4px 8px;text-align:right">ISIN</th></tr>'
        f"{_rows(fills)}</table>"
    )


def build_stop_alert_html(report: ProcessReport) -> str:
    stops = [f for f in report.queued if f.side == "sell"]
    return (
        f'<div><h2 style="font-family:sans-serif;color:#c0392b">'
        f"⚠ Catastrophic stop — {report.process_date}</h2>"
        f"<p style='font-family:sans-serif'>{len(stops)} name(s) breached the 25% "
        f"stop on today's close; sells queued for next-open.</p>"
        f"{_table('Queued stop sells (next-open)', stops)}</div>"
    )


def build_rebalance_preview_html(report: ProcessReport) -> str:
    buys = [f for f in report.queued if f.side == "buy"]
    sells = [f for f in report.queued if f.side == "sell"]
    trims = [f for f in report.queued if f.side == "trim"]
    eq = report.snapshot.equity if report.snapshot else float("nan")
    return (
        f'<div><h2 style="font-family:sans-serif">📋 S3 rebalance preview — '
        f"{report.process_date}</h2>"
        f"<p style='font-family:sans-serif'>Decision at close; fills land next-open. "
        f"Book equity ₹{eq:,.0f}.</p>"
        f"{_table('Buys', buys)}{_table('Sells', sells)}{_table('Trims', trims)}</div>"
    )


def build_fill_confirm_html(report: ProcessReport) -> str:
    return (
        f'<div><h2 style="font-family:sans-serif">✅ Fills executed — '
        f"{report.process_date}</h2>"
        f"{_table('Filled at next-session open', report.fills_executed)}</div>"
    )


def emit_alerts(report: ProcessReport, *, send: bool = True) -> list[str]:
    """Build (and optionally send) the alerts implied by ``report``.

    Returns the list of subjects emitted (so the caller / tests can assert without a
    live Resend key). When ``send`` is False, HTML is built and discarded — used to
    prove rendering in tests without external I/O (Rule 5).
    """
    emitted: list[str] = []
    if report.skipped:
        return emitted

    if report.fills_executed:
        _maybe_send(
            f"S3 paper — fills executed {report.process_date}",
            build_fill_confirm_html(report),
            send,
        )
        emitted.append("fills")

    if report.is_rebalance and report.queued:
        _maybe_send(
            f"S3 paper — rebalance preview {report.process_date}",
            build_rebalance_preview_html(report),
            send,
        )
        emitted.append("rebalance")
    elif report.queued:  # non-rebalance day ⇒ queued fills are catastrophic stops
        _maybe_send(
            f"S3 paper — STOP triggered {report.process_date}",
            build_stop_alert_html(report),
            send,
        )
        emitted.append("stop")

    return emitted


def build_pipeline_failure_html(
    exc: Exception, process_date: str, traceback_str: str
) -> str:
    exc_type = type(exc).__name__
    return (
        '<div style="font-family:sans-serif">'
        '<h2 style="color:#c0392b">🚨 S3 paper pipeline FAILED</h2>'
        f"<p><b>Date being processed:</b> {process_date}</p>"
        f"<p><b>Error:</b> {exc_type}: {exc}</p>"
        "<h3>Traceback</h3>"
        '<pre style="background:#f8f8f8;padding:12px;border:1px solid #ddd;'
        'overflow:auto;font-size:12px;white-space:pre-wrap">'
        f"{traceback_str}</pre>"
        "<p style='color:#888'>Action: check Celery worker logs, fix the issue, then "
        "re-run via <code>execute_paper_daily_task.delay()</code>.</p>"
        "</div>"
    )


def emit_failure_alert(
    exc: Exception, process_date: str, traceback_str: str, *, send: bool = True
) -> None:
    """Send an immediate failure email when the daily paper task crashes.

    Must be called from inside an except block so ``traceback_str`` (from
    ``traceback.format_exc()``) captures the live traceback. The ``send=False``
    path renders HTML without I/O so tests can assert without a live Resend key.
    """
    subject = f"🚨 S3 paper — PIPELINE FAILED {process_date}"
    html = build_pipeline_failure_html(exc, process_date, traceback_str)
    _maybe_send(subject, html, send)


def _maybe_send(subject: str, html: str, send: bool) -> None:
    if send:
        send_alert_email(subject, html)
    else:
        # Build path already exercised by the caller; nothing to do (no I/O).
        log.debug("emit_alerts(send=False): would send %r", subject)
