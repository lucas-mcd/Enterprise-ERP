from celery import Celery
from erp.config import settings

cfg = settings()
app = Celery(
    "erp",
    broker=cfg.broker_url,
    include=["erp.workers.tasks", "erp.workers.reports", "erp.workers.fiscal"],
)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    task_soft_time_limit=240,
    task_time_limit=300,
    beat_schedule={
        "fiscal-dispatch": {"task": "erp.fiscal.dispatch", "schedule": 5.0},
        "report-dispatch": {"task": "erp.reports.dispatch", "schedule": 10.0},
        "infrastructure-heartbeat": {"task": "erp.heartbeat", "schedule": 60.0},
    },
)
