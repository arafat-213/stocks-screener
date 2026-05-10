from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os
from contextlib import asynccontextmanager
from app.db.session import SessionLocal
from app.pipeline.orchestrator import run_pipeline
from app.routers import stocks, dashboard, reports, screens

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

scheduler = BackgroundScheduler()

def scheduled_pipeline():
    db = SessionLocal()
    try:
        run_pipeline(db)
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler.add_job(scheduled_pipeline, 'cron', day_of_week='mon-fri', hour=16, minute=5)
    scheduler.start()
    logger.info("Scheduler started")
    yield
    # Shutdown
    scheduler.shutdown()
    logger.info("Scheduler shutdown")

app = FastAPI(title="Stock AI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(screens.router, prefix="/api")
app.include_router(reports.router)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
