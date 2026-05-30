from sqlalchemy.orm import Session


def get_top_stocks(db: Session, limit: int = 10):
    """Queries the top scored stocks for the dashboard."""
    # TODO: Implement DB query
    return []


def log_pipeline_run(db: Session, run_status: str, fetched: int, scored: int):
    """Logs pipeline execution results."""
    # TODO: Implement DB write
    pass
