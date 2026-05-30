import datetime
import logging
import os

from sqlalchemy import Date, case, cast, func, text
from sqlalchemy.orm import Session

from app.db.models import Stock, TechnicalSignal

logger = logging.getLogger(__name__)


def generate_daily_report(db: Session):
    """
    Generates a daily snapshot report of the top scored stocks with multi-timeframe confluence.
    Saves the report as a Markdown file in the 'backend/reports' directory.
    """
    try:
        today = datetime.datetime.utcnow().date()

        # Query top 20 stocks by confluence and score for today
        results = (
            db.query(
                TechnicalSignal.symbol,
                Stock.name,
                func.sum(case((TechnicalSignal.is_bullish, 1), else_=0)).label(
                    "confluence_count"
                ),
                func.max(
                    case(
                        (TechnicalSignal.timeframe == "D", TechnicalSignal.entry_score),
                        else_=0,
                    )
                ).label("daily_score"),
                func.max(
                    case(
                        (TechnicalSignal.timeframe == "D", TechnicalSignal.rsi), else_=0
                    )
                ).label("rsi"),
            )
            .join(Stock, TechnicalSignal.symbol == Stock.symbol)
            .filter(cast(TechnicalSignal.date, Date) == today)
            .group_by(TechnicalSignal.symbol, Stock.name)
            .order_by(text("confluence_count DESC"), text("daily_score DESC"))
            .limit(20)
            .all()
        )

        if not results:
            logger.warning(f"No scores found for {today}, skipping report generation.")
            return None

        # Prepare Report Content
        report_lines = [
            f"# Daily Stock Scan Report - {today}",
            f"Generated at: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "",
            "| Symbol | Name | Confluence | Daily Score | RSI |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]

        for symbol, name, confluence, score, rsi in results:
            confluence_str = f"{int(confluence)}/3"
            report_lines.append(
                f"| {symbol} | {name} | {confluence_str} | {score:.2f} | {rsi:.2f} |"
            )

        report_content = "\n".join(report_lines)

        # Ensure reports directory exists (backend/reports)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # backend/app/pipeline/reporter.py -> backend/reports/
        reports_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "reports"))

        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)

        report_filename = f"report_{today}.md"
        report_path = os.path.join(reports_dir, report_filename)

        with open(report_path, "w") as f:
            f.write(report_content)

        logger.info(f"Daily report generated: {report_path}")
        return str(report_path)

    except Exception as e:
        logger.error(f"Failed to generate daily report: {e}")
        return None
