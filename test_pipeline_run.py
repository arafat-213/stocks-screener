import sys
import os
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.db.session import SessionLocal
from app.pipeline.orchestrator import run_pipeline
import logging

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    db = SessionLocal()
    try:
        print("Starting test pipeline run...")
        run_pipeline(db, limit=10)
        print("Pipeline run completed successfully!")
    except Exception as e:
        print(f"Pipeline run failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
