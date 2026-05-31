import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import PipelineRun
from app.db.session import get_db
from app.tasks import execute_pipeline_task

router = APIRouter(tags=["screener"])
logger = logging.getLogger(__name__)


class ScreenerRequest(BaseModel):
    limit: int | None = None
    resume_run_id: str | None = None


@router.get("/api/screener/top")
async def get_top_stocks():
    return {"top_stocks": []}


@router.post("/api/screener/run")
def run_screener(
    request: ScreenerRequest = ScreenerRequest(), db: Session = Depends(get_db)
):
    # Concurrency Guard
    existing_run = db.query(PipelineRun).filter(PipelineRun.status == "running").first()
    if existing_run and not request.resume_run_id:
        logger.error(f"Pipeline already running: {existing_run.run_id}")
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    execute_pipeline_task.delay(
        limit=request.limit, resume_run_id=request.resume_run_id
    )
    return {
        "message": "Screener run initiated",
        "limit": request.limit,
        "resume_run_id": request.resume_run_id,
    }


@router.post("/api/pipeline/stop")
def stop_pipeline(db: Session = Depends(get_db)):
    run = db.query(PipelineRun).filter(PipelineRun.status == "running").first()
    if not run:
        raise HTTPException(status_code=404, detail="No running pipeline found")

    run.stop_requested = True
    db.commit()
    return {"message": "Stop signal sent"}
