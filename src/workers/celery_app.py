"""
Celery application configuration.

Provides async task processing for long-running operations.
"""

import os

from celery import Celery

# Get broker URL from environment
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# Create Celery app
app = Celery(
    "lexia_workers",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "src.workers.tasks.transcription",
        "src.workers.tasks.diarization",
        "src.workers.tasks.webhooks",
    ],
)

# Celery configuration
app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # Soft limit at 55 min
    # Result settings
    result_expires=86400,  # Results expire after 24 hours
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    # Retry settings
    task_default_retry_delay=60,  # Retry after 1 minute
    task_max_retries=3,
    # Queue configuration
    task_default_queue="default",
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "transcription": {"exchange": "transcription", "routing_key": "transcription"},
        "diarization": {"exchange": "diarization", "routing_key": "diarization"},
        "webhooks": {"exchange": "webhooks", "routing_key": "webhooks"},
    },
    task_routes={
        "src.workers.tasks.transcription.*": {"queue": "transcription"},
        "src.workers.tasks.diarization.*": {"queue": "diarization"},
        "src.workers.tasks.webhooks.*": {"queue": "webhooks"},
    },
    # Beat schedule (periodic tasks)
    beat_schedule={
        "check-pending-webhooks": {
            "task": "src.workers.tasks.webhooks.send_pending_webhooks",
            "schedule": 60.0,  # Every minute
        },
        "cleanup-old-jobs": {
            "task": "src.workers.tasks.cleanup.cleanup_old_jobs",
            "schedule": 3600.0,  # Every hour
        },
    },
)


def main() -> None:
    """Main entry point for worker."""
    app.start()


if __name__ == "__main__":
    main()
