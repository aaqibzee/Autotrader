from __future__ import annotations

import atexit
import os
import random
import signal
import threading
from typing import Any

import structlog
from celery import Celery, Task
from celery.schedules import crontab
from celery.signals import beat_init, worker_init, worker_process_init
from kombu import Exchange, Queue
from redis import Redis
from redis.exceptions import LockError, RedisError

from app.core.config import settings
from app.core.http_client import request_id_context

logger = structlog.get_logger(__name__)


class AutotraderTask(Task):
    abstract = True
    acks_late = True
    reject_on_worker_lost = True
    soft_time_limit = 60
    time_limit = 120
    max_retries = 3
    default_retry_delay = 1

    def retry(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        exc: BaseException | None = None,
        throw: bool = True,
        eta: Any = None,
        countdown: float | None = None,
        max_retries: int | None = None,
        **options: Any,
    ) -> Any:
        if countdown is None and eta is None:
            exponent = max(0, self.request.retries)
            countdown = random.uniform(0, min(300, 2**exponent))
        return super().retry(
            args=args,
            kwargs=kwargs,
            exc=exc,
            throw=throw,
            eta=eta,
            countdown=countdown,
            max_retries=max_retries,
            **options,
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        request_id = self.request.get('request_id')
        with (
            request_id_context(request_id),
            structlog.contextvars.bound_contextvars(
                **({'request_id': request_id} if request_id else {})
            ),
        ):
            return super().__call__(*args, **kwargs)


class _BeatProcessLock:
    def __init__(self) -> None:
        self.client = Redis.from_url(settings.REDIS_BROKER_URL)
        self.lock = self.client.lock(
            'autotrader:celery:beat:lock',
            timeout=20,
            thread_local=False,
        )
        self.stop = threading.Event()
        self.heartbeat: threading.Thread | None = None

    def acquire(self) -> None:
        try:
            acquired = self.lock.acquire(blocking=False)
        except RedisError as exc:
            self.client.close()
            logger.exception('celery_beat_lock_unavailable')
            raise SystemExit('Unable to acquire Celery Beat Redis lock') from exc
        if not acquired:
            self.client.close()
            raise SystemExit('Celery Beat lock held by another process')

        self.heartbeat = threading.Thread(
            target=self._heartbeat,
            name='celery-beat-lock-heartbeat',
            daemon=True,
        )
        self.heartbeat.start()

    def _heartbeat(self) -> None:
        while not self.stop.wait(5):
            try:
                self.lock.extend(20, replace_ttl=True)
            except (LockError, RedisError):
                logger.critical('celery_beat_lock_lost')
                os.kill(os.getpid(), signal.SIGTERM)
                return

    def release(self) -> None:
        self.stop.set()
        try:
            self.lock.release()
        except (LockError, RedisError):
            logger.warning('celery_beat_lock_release_failed')
        finally:
            self.client.close()


@worker_init.connect(weak=False)
@worker_process_init.connect(weak=False)
def _configure_worker_telemetry(**_: Any) -> None:
    # Workers never import app.main, so without this their logs skip PII redaction and
    # task errors never reach Sentry. worker_process_init re-runs it after each fork.
    from app.core.telemetry import configure_process_telemetry

    configure_process_telemetry('autotrader-worker')


@beat_init.connect(weak=False)
def _configure_beat_telemetry(**_: Any) -> None:
    from app.core.telemetry import configure_process_telemetry

    configure_process_telemetry('autotrader-beat')


_beat_process_lock: _BeatProcessLock | None = None


@beat_init.connect(weak=False)
def _acquire_beat_process_lock(**_: Any) -> None:
    global _beat_process_lock
    if _beat_process_lock is not None:
        return
    lock = _BeatProcessLock()
    lock.acquire()
    _beat_process_lock = lock


def _release_beat_process_lock(**_: Any) -> None:
    global _beat_process_lock
    if _beat_process_lock is not None:
        _beat_process_lock.release()
        _beat_process_lock = None


atexit.register(_release_beat_process_lock)

celery_app = Celery(
    'autotrader',
    broker=settings.REDIS_BROKER_URL,
    backend=None,
)
celery_app.Task = AutotraderTask

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    timezone='Europe/London',
    enable_utc=True,
    task_queues=(
        Queue('notifications', Exchange('notifications'), routing_key='notifications'),
        Queue('images', Exchange('images'), routing_key='images'),
        Queue('default', Exchange('default'), routing_key='default'),
    ),
    task_default_queue='default',
    task_default_exchange='default',
    task_default_routing_key='default',
    task_routes={
        'app.tasks.notifications.*': {'queue': 'notifications'},
        'app.tasks.images.*': {'queue': 'images'},
        'app.tasks.*': {'queue': 'default'},
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=60,
    task_time_limit=120,
    task_ignore_result=True,
    task_default_retry_delay=1,
    broker_connection_retry_on_startup=True,
    # Keep our redacting JSON root handler (configure_logging) instead of Celery's.
    worker_hijack_root_logger=False,
)

celery_app.conf.beat_schedule = {
    'refresh-cloudflare-ranges-weekly': {
        'task': 'app.tasks.cloudflare_ranges.refresh_cloudflare_ranges',
        'schedule': crontab(day_of_week='sunday', hour=3, minute=0),
    },
}
celery_app.autodiscover_tasks(['app.tasks'])
