from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.session import get_db
from app.db.models import TechnicalSignal, PipelineRun
from app.pipeline.orchestrator import run_pipeline

router = APIRouter()

@router.get("/stocks/top")
def get_top_stocks(db: Session = Depends(get_db)):
    scores = db.query(TechnicalSignal).filter(TechnicalSignal.timeframe == 'D').order_by(desc(TechnicalSignal.entry_score)).limit(20).all()
    return [{"symbol": s.symbol, "score": s.entry_score, "rsi": s.rsi, "signal": s.ema_signal} for s in scores]

@router.post("/screener/run")
def trigger_screener(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    background_tasks.add_task(run_pipeline, db)
    return {"message": "Pipeline started"}

@router.get("/pipeline/status")
def get_pipeline_status(db: Session = Depends(get_db)):
    run = db.query(PipelineRun).order_by(desc(PipelineRun.timestamp)).first()
    if not run: return {"status": "idle"}
    return {"status": run.status, "last_run": run.timestamp, "scored": run.stocks_scored}
