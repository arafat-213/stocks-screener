import sys
import os
import time
import logging

# Add the backend directory to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.pipeline.orchestrator import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    db = SessionLocal()
    start_time = time.time()
    logger.info("Starting pipeline run...")
    try:
        run_pipeline(db)
        end_time = time.time()
        duration = end_time - start_time
        logger.info(f"Pipeline completed in {duration:.2f} seconds")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
