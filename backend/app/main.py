from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os
from app.db.session import SessionLocal
from app.pipeline.orchestrator import run_pipeline
from app.routers import stocks, dashboard

# Configure Logging
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, "pipeline.log"))
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Stock AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")

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
