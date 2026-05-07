import datetime
import os
import logging
from sqlalchemy.orm import Session
from app.db.models import DailyScore, Stock

logger = logging.getLogger(__name__)

def generate_daily_report(db: Session):
    """
    Generates a daily snapshot report of the top scored stocks.
    Saves the report as a Markdown file in the 'backend/reports' directory.
    """
    try:
        today = datetime.datetime.utcnow().date()
        
        # Query top 20 stocks by score for today
        results = (
            db.query(DailyScore, Stock)
            .join(Stock, DailyScore.symbol == Stock.symbol)
            .filter(DailyScore.date == today)
            .order_by(DailyScore.entry_score.desc())
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
            "| Symbol | Name | Score | RSI | Signal |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]
        
        for score, stock in results:
            signal = f"EMA: {score.ema_signal}, Vol: {score.volume_signal}"
            report_lines.append(
                f"| {score.symbol} | {stock.name} | {score.entry_score:.2f} | {score.rsi:.2f} | {signal} |"
            )
            
        report_content = "\n".join(report_lines)
        
        # Ensure reports directory exists (backend/reports)
        # Get the directory where this file is located (backend/app/pipeline/)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Target backend/reports/
        reports_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "reports"))
        
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)
            
        report_filename = f"report_{today}.md"
        report_path = os.path.join(reports_dir, report_filename)
        
        with open(report_path, "w") as f:
            f.write(report_content)
            
        logger.info(f"Daily report generated: {report_path}")
        return report_path
        
    except Exception as e:
        logger.error(f"Failed to generate daily report: {e}")
        return None
