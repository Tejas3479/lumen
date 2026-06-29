"""
Lumen Celery Application
Async task queue for AI categorization, notifications, and predictions.
"""
from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "lumen",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.services.ai_categorizer",
        "app.services.predictive",
        "app.services.notification",
        "app.services.maintenance",
        "app.services.triage_agent",
        "app.services.escalation_agent",
        "app.services.ward_report_agent",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "regenerate-hotspots-every-6-hours": {
            "task": "app.services.predictive.generate_hotspots_task",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "cleanup-guest-users-daily": {
            "task": "app.services.maintenance.cleanup_guest_users",
            "schedule": crontab(hour=3, minute=0),  # 3 AM IST daily
        },
        "escalation-check-every-30-minutes": {
            "task": "app.services.escalation_agent.run_escalation_check",
            "schedule": crontab(minute="*/30"),  # Every 30 minutes
        },
        "weekly-ward-reports-monday-8am": {
            "task": "app.services.ward_report_agent.generate_weekly_reports",
            "schedule": crontab(hour=8, minute=0, day_of_week=1),  # Monday 8 AM
        },
    },
)
