import os

from celery import Celery
from celery.schedules import crontab

redis_url = os.getenv("REDIS_URL", "redis://localhost:6380/0")

celery_app = Celery(
    "stock_ai", broker=redis_url, backend=redis_url, include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    beat_schedule={
        "daily-pipeline-at-4pm": {
            "task": "app.tasks.execute_pipeline_task",
            "schedule": crontab(day_of_week="1-5", hour=16, minute=5),
        },
        "nightly-cleanup-at-2am": {
            "task": "app.tasks.execute_cleanup_task",
            "schedule": crontab(hour=2, minute=30),
        },
        # v3/11 §4c — S3 forward paper book; weekday post-close, after bhavcopy publishes.
        "s3-paper-daily-postclose": {
            "task": "app.tasks.execute_paper_daily_task",
            "schedule": crontab(day_of_week="1-5", hour=19, minute=30),
        },
    },
)
