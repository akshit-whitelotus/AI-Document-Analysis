from celery import Celery
from celery.schedules import crontab
from shared.config.settings import settings

RABBITMQ_URL=(
    f"amqp://{settings.RABBITMQ_USER}:{settings.RABBITMQ_PASSWORD}"
    f"@{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}//"
)
REDIS_BACKEND_URL=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"

celery_app=Celery(
    "ai_document_analysis",
    broker=RABBITMQ_URL,
    backend=REDIS_BACKEND_URL,
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=60*15,
    task_soft_time_limit=60*10,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "cleanup-expired-sessions-every-hour":{
        "task":"cleanup_expired_sessions",
        "schedule":crontab(minute=0),
    },
    "reindex-pending-documents-every-10-miutes":{
        "task":"reindex_pending_documents",
        "schedule":crontab(minute="*/10")
    },
}
