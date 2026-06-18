"""Run the full bhavcopy pipeline (2017-01-01 → today).

Usage (from any directory):
    backend/venv/bin/python backend/app/data/bhavcopy/fetch.py
"""

import logging
import sys
from pathlib import Path

# Ensure the `backend/` directory is on sys.path so `app.*` imports resolve
# regardless of the working directory from which this script is invoked.
_backend_dir = Path(__file__).resolve().parents[3]  # …/backend/
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.data.bhavcopy.build import run_build  # noqa: E402

report = run_build("2017-01-01", "2026-06-13")
print(report.summary())
