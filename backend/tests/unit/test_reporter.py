import datetime
import os
from unittest.mock import MagicMock, patch

from app.pipeline.reporter import generate_daily_report


def test_generate_daily_report(tmp_path):
    # Setup mocks
    mock_db = MagicMock()
    today = datetime.datetime.now(datetime.timezone.utc).date()

    # Mock return value for the aggregate query
    # (symbol, name, confluence, score, rsi)
    mock_results = [
        ("REL", "Reliance", 3, 90.0, 65.0),
        ("INF", "Infosys", 2, 85.0, 55.0),
    ]

    # Query join results - the chain is now query().join().filter().group_by().order_by().limit().all()
    mock_db.query.return_value.join.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = mock_results

    # Mock os.makedirs and open to use tmp_path
    original_join = os.path.join
    with patch(
        "os.path.join",
        side_effect=lambda *args: (
            str(tmp_path) if "reports" in args else original_join(*args)
        ),
    ):
        report_path = generate_daily_report(mock_db)

        assert report_path is not None
        assert os.path.exists(report_path)
        assert f"report_{today}.md" in report_path

        with open(report_path, "r") as f:
            content = f.read()
            assert "# Daily Stock Scan Report" in content
            assert "REL" in content
            assert "Reliance" in content
            assert "3/3" in content
            assert "90.00" in content
            assert "INF" in content
            assert "Infosys" in content
            assert "2/3" in content
            assert "85.00" in content


def test_generate_daily_report_no_data():
    mock_db = MagicMock()
    mock_db.query.return_value.join.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = []

    report_path = generate_daily_report(mock_db)
    assert report_path is None
