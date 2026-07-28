from shared.messaging.celery_app import celery_app
from app import tasks

celery_app.conf.include = ["app.tasks"]
