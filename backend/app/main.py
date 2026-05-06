from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from app.db.session import SessionLocal
from app.pipeline.orchestrator import run_pipeline
from app.routers import stocks

app = FastAPI(title="Stock AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router, prefix="/api")

scheduler = BackgroundScheduler()

def scheduled_pipeline():
    db = SessionLocal()
    try:
        run_pipeline(db)
    finally:
        db.close()

@app.on_event("startup")
def start_scheduler():
    scheduler.add_job(scheduled_pipeline, 'cron', day_of_week='mon-fri', hour=16, minute=5)
    scheduler.start()

@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
