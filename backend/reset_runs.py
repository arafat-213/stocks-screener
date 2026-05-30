from app.db.models import PipelineRun
from app.db.session import SessionLocal


def reset_runs():
    db = SessionLocal()
    try:
        db.query(PipelineRun).filter(PipelineRun.status == "running").update(
            {"status": "failed"}
        )
        db.commit()
        print("Reset all 'running' runs to 'failed'.")
    except Exception as e:
        print(f"Error resetting runs: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    reset_runs()
