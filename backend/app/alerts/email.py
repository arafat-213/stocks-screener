# app/alerts/email.py
import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Ensure env vars are loaded
load_dotenv()


def send_alert_email(subject: str, html_body: str) -> Optional[str]:
    """
    Sends an email via Resend API.
    Returns the Resend message ID on success, None on failure.
    """
    api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("ALERT_FROM_EMAIL", "onboarding@resend.dev")
    to_email = os.getenv("ALERT_TO_EMAIL")

    if not api_key:
        logger.error("RESEND_API_KEY not set — skipping email alert")
        return None
    if not to_email:
        logger.error("ALERT_TO_EMAIL not set — skipping email alert")
        return None

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        message_id = response.json().get("id")
        logger.info("Alert email sent: %s — %s", subject, message_id)
        return message_id
    except httpx.HTTPStatusError as e:
        logger.error("Resend API error %s: %s", e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.error("Failed to send alert email: %s", e)
        return None


def build_signal_email(
    signals: list[dict], signal_date: str, regime_bullish: bool
) -> str:
    """
    Builds the HTML email body for a batch of signals.
    signals: list of dicts with keys: symbol, name, sector, score, signal_tier, ema_signal, rsi, adx, volume_breakout, entry_price, stop_loss, target_price, entry_status, pct_above_ema20, momentum_12m
    """
    regime_badge = (
        '<span style="color:#16a34a;font-weight:bold;">BULLISH ✓</span>'
        if regime_bullish
        else '<span style="color:#dc2626;font-weight:bold;">BEARISH ✗</span>'
    )

    tier1 = [s for s in signals if s.get("signal_tier") == 1]
    tier2 = [s for s in signals if s.get("signal_tier") == 2]

    def entry_badge(status):
        if status == "in_zone":
            return '<span style="color:#16a34a;font-weight:bold;">● In Zone</span>'
        elif status == "extended":
            return '<span style="color:#d97706;font-weight:bold;">● Extended</span>'
        return '<span style="color:#dc2626;">● Chasing</span>'

    def signal_rows(signal_list):
        if not signal_list:
            return "<tr><td colspan='8' style='color:#6b7280;padding:12px;'>None today</td></tr>"

        rows = ""
        for s in signal_list:
            display_symbol = s["symbol"].replace(".NS", "")
            rows += f"""
            <tr style="border-bottom:1px solid #f1f5f9;">
                <td style="padding:10px 8px;font-weight:600;">{display_symbol}</td>
                <td style="padding:10px 8px;font-weight:600;font-family:monospace;">₹{(s.get("close_price") or 0.0):,.2f}</td>
                <td style="padding:10px 8px;color:#475569;font-size:12px;">{s.get("sector", "—")}</td>
                <td style="padding:10px 8px;">{entry_badge(s.get("entry_status", "unknown"))}</td>
                <td style="padding:10px 8px;font-family:monospace;">{(s.get("score") or 0.0):.1f}</td>
                <td style="padding:10px 8px;font-family:monospace;">
                    RSI {(s.get("rsi") or 0.0):.0f} &nbsp;|&nbsp; ADX {(s.get("adx") or 0.0):.0f}
                    {"&nbsp;|&nbsp;<b>VOL✓</b>" if s.get("volume_breakout") else ""}
                </td>
                <td style="padding:10px 8px;font-family:monospace;font-size:12px;">
                    SL: ₹{(s.get("stop_loss") or 0.0):,.2f}<br>
                    T: ₹{(s.get("target_price") or 0.0):,.2f}
                </td>
                <td style="padding:10px 8px;color:#64748b;font-size:12px;">
                    {s.get("pct_above_ema20", 0):+.1f}% vs EMA20<br>
                    12m mom: {s.get("momentum_12m", 0):+.1f}%
                </td>
            </tr>"""
        return rows

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; max-width:900px;margin:0 auto;padding:20px;background:#f8fafc;">
    <div style="background:white;border-radius:12px;padding:24px; box-shadow:0 1px 3px rgba(0,0,0,0.1);">
        <h1 style="margin:0 0 4px;font-size:20px;color:#0f172a;">
            📊 Stock Alerts — {signal_date}
        </h1>
        <p style="margin:0 0 20px;color:#64748b;font-size:14px;">
            Market Regime: {regime_badge} &nbsp;·&nbsp; {len(signals)} signal{"s" if len(signals) != 1 else ""} found
        </p>

        <h2 style="font-size:15px;color:#0f172a;margin:0 0 8px;">
            ⚡ Tier 1 Signals ({len(tier1)}) — Volume + ADX confirmed
        </h2>
        <table width="100%" style="border-collapse:collapse;font-size:13px;margin-bottom:24px;">
            <thead>
                <tr style="background:#f1f5f9;color:#475569;font-size:11px;text-transform:uppercase;">
                    <th style="padding:8px;text-align:left;">Symbol</th>
                    <th style="padding:8px;text-align:left;">Price</th>
                    <th style="padding:8px;text-align:left;">Sector</th>
                    <th style="padding:8px;text-align:left;">Entry</th>
                    <th style="padding:8px;text-align:left;">Score</th>
                    <th style="padding:8px;text-align:left;">Indicators</th>
                    <th style="padding:8px;text-align:left;">Levels</th>
                    <th style="padding:8px;text-align:left;">Context</th>
                </tr>
            </thead>
            <tbody>{signal_rows(tier1)}</tbody>
        </table>

        <h2 style="font-size:15px;color:#0f172a;margin:0 0 8px;">
            🔔 Tier 2 Signals ({len(tier2)}) — Volume OR ADX confirmed
        </h2>
        <table width="100%" style="border-collapse:collapse;font-size:13px;margin-bottom:24px;">
            <thead>
                <tr style="background:#f1f5f9;color:#475569;font-size:11px;text-transform:uppercase;">
                    <th style="padding:8px;text-align:left;">Symbol</th>
                    <th style="padding:8px;text-align:left;">Price</th>
                    <th style="padding:8px;text-align:left;">Sector</th>
                    <th style="padding:8px;text-align:left;">Entry</th>
                    <th style="padding:8px;text-align:left;">Score</th>
                    <th style="padding:8px;text-align:left;">Indicators</th>
                    <th style="padding:8px;text-align:left;">Levels</th>
                    <th style="padding:8px;text-align:left;">Context</th>
                </tr>
            </thead>
            <tbody>{signal_rows(tier2)}</tbody>
        </table>

        <p style="color:#94a3b8;font-size:11px;margin:16px 0 0;border-top:1px solid #f1f5f9;padding-top:12px;">
            Generated by your Stock AI pipeline · Not financial advice · Entry zones valid for ~8 trading days from signal date
        </p>
    </div>
</body>
</html>
"""


def build_exit_alert_email(alerts: list[dict], signal_date: str) -> str:
    """
    Builds HTML email for exit/position alerts.
    alerts: list of dict with symbol, alert_type, urgency, entry_price, current_price, stop_loss, target, unrealised_pct, distance_to_stop_pct, holding_days
    """

    def urgency_badge(urgency):
        colors = {"critical": "#dc2626", "high": "#d97706", "medium": "#2563eb"}
        c = colors.get(urgency, "#6b7280")
        return f'<span style="background:{c};color:white;padding:2px 7px;border-radius:4px;font-size:11px;text-transform:uppercase;font-weight:bold;">{urgency}</span>'

    def type_label(atype):
        labels = {
            "stop_hit": "🔴 Stop Hit",
            "stop_approached": "🟠 Near Stop",
            "target_hit": "🟢 Target Hit",
            "target_approached": "🔵 Near Target",
            "overextended_exit": "🟣 Overextended Exit",
        }
        return labels.get(atype, atype.replace("_", " ").title())

    rows = ""
    for a in alerts:
        display_symbol = a["symbol"].replace(".NS", "")
        pnl_color = "#16a34a" if a["unrealised_pct"] >= 0 else "#dc2626"
        rows += f"""
        <tr style="border-bottom:1px solid #f1f5f9;">
            <td style="padding:12px 8px;font-weight:600;">{display_symbol}</td>
            <td style="padding:12px 8px;">{type_label(a["alert_type"])}</td>
            <td style="padding:12px 8px;">{urgency_badge(a["urgency"])}</td>
            <td style="padding:12px 8px;font-family:monospace;color:{pnl_color};font-weight:bold;">
                {a["unrealised_pct"]:+.2f}%
            </td>
            <td style="padding:12px 8px;font-family:monospace;font-size:12px;">
                Entry: ₹{a["entry_price"]:,}<br>
                CMP: ₹{a["current_price"]:,}
            </td>
            <td style="padding:12px 8px;font-family:monospace;font-size:12px;">
                SL: ₹{(a["stop_loss"] or 0):,}<br>
                T: ₹{(a["target"] or 0):,}
            </td>
            <td style="padding:12px 8px;color:#64748b;font-size:12px;">
                {a["holding_days"]} days held
            </td>
        </tr>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; max-width:800px;margin:0 auto;padding:20px;background:#fef2f2;">
    <div style="background:white;border-radius:12px;padding:24px; box-shadow:0 1px 3px rgba(0,0,0,0.1); border-top: 4px solid #dc2626;">
        <h1 style="margin:0 0 4px;font-size:20px;color:#0f172a;">
            ⚠️ Position Alerts — {signal_date}
        </h1>
        <p style="margin:0 0 20px;color:#64748b;font-size:14px;">
            {len(alerts)} open positions require attention today.
        </p>

        <table width="100%" style="border-collapse:collapse;font-size:13px;">
            <thead>
                <tr style="background:#f1f5f9;color:#475569;font-size:11px;text-transform:uppercase;">
                    <th style="padding:8px;text-align:left;">Symbol</th>
                    <th style="padding:8px;text-align:left;">Event</th>
                    <th style="padding:8px;text-align:left;">Urgency</th>
                    <th style="padding:8px;text-align:left;">Unrealised PnL</th>
                    <th style="padding:8px;text-align:left;">Price</th>
                    <th style="padding:8px;text-align:left;">Plan</th>
                    <th style="padding:8px;text-align:left;">Holding</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>

        <div style="margin-top:24px;padding:16px;background:#fff7ed;border-radius:8px;border:1px solid #ffedd5;">
            <p style="margin:0;font-size:13px;color:#9a3412;line-height:1.5;">
                <strong>Trader Discipline Note:</strong> Exit alerts are generated based on today's High/Low/Close.
                If a Stop was hit, consider closing the position at the next market open or as per your trading rules.
            </p>
        </div>

        <p style="color:#94a3b8;font-size:11px;margin:16px 0 0;border-top:1px solid #f1f5f9;padding-top:12px;">
            Generated by your Stock AI pipeline · Monitor your journal for updates.
        </p>
    </div>
</body>
</html>
"""
