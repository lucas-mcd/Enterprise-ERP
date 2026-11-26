from datetime import datetime, timezone
from redis import Redis
from erp.config import settings
from erp.workers.celery_app import app


def heartbeat() -> None:
    """Infrastructure smoke task. Accounting schedules need business calendars."""
    with Redis.from_url(settings().redis_url, socket_timeout=3) as client:
        client.set(
            "operations:worker:heartbeat",
            datetime.now(timezone.utc).isoformat(),
            ex=180,
        )


app.task(name="erp.heartbeat")(heartbeat)
