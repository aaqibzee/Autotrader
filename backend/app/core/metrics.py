from __future__ import annotations

import time
from ipaddress import ip_address
from typing import Any, cast

import structlog
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from redis import Redis
from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_QUEUES = ('default', 'images', 'notifications')
_access_logger = structlog.get_logger('app.access')

REQUESTS = Counter(
    'autotrader_http_requests_total',
    'HTTP requests handled by the API',
    ('method', 'route', 'status'),
)
REQUEST_DURATION = Histogram(
    'autotrader_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ('method', 'route'),
)
DB_POOL = Gauge(
    'autotrader_db_pool_connections',
    'Database connection pool connections by state',
    ('engine', 'state'),
)
CELERY_QUEUE_DEPTH = Gauge(
    'autotrader_celery_queue_depth',
    'Number of messages waiting in a Celery queue',
    ('queue',),
)
TASK_DURATION = Histogram(
    'autotrader_celery_task_duration_seconds',
    'Celery task execution duration in seconds',
    ('task',),
)
TASK_FAILURES = Counter(
    'autotrader_celery_task_failures_total',
    'Celery task failures',
    ('task',),
)
INTEGRATION_DURATION = Histogram(
    'autotrader_integration_call_duration_seconds',
    'Integration call duration in seconds, including retries',
    ('integration',),
)
INTEGRATION_FAILURES = Counter(
    'autotrader_integration_failures_total',
    'Failed integration calls',
    ('integration',),
)
BREAKER_STATE = Gauge(
    'autotrader_integration_circuit_breaker',
    'Circuit breaker state (one for the active state)',
    ('integration', 'state'),
)
COLLECTION_ERRORS = Counter(
    'autotrader_metrics_collection_errors_total',
    'Errors collecting optional backend metrics',
    ('source',),
)
_REGISTRY = CollectorRegistry()
for _metric in (
    REQUESTS,
    REQUEST_DURATION,
    DB_POOL,
    CELERY_QUEUE_DEPTH,
    TASK_DURATION,
    TASK_FAILURES,
    INTEGRATION_DURATION,
    INTEGRATION_FAILURES,
    BREAKER_STATE,
    COLLECTION_ERRORS,
):
    _REGISTRY.register(_metric)

_TASK_STARTS: dict[tuple[str, str], float] = {}


def record_integration_call(integration: str, duration: float, *, failed: bool) -> None:
    INTEGRATION_DURATION.labels(integration).observe(duration)
    if failed:
        INTEGRATION_FAILURES.labels(integration).inc()


def _task_name(task: object) -> str:
    return str(getattr(task, 'name', None) or task.__class__.__name__)


def _record_task_start(
    sender: object = None, task: object = None, task_id: str = '', **_: object
) -> None:
    current_task = task or sender
    if current_task is not None:
        _TASK_STARTS[(task_id, _task_name(current_task))] = time.perf_counter()


def _record_task_finish(
    sender: object = None,
    task: object = None,
    task_id: str = '',
    **_: object,
) -> None:
    current_task = task or sender
    if current_task is None:
        return
    task_name = _task_name(current_task)
    started = _TASK_STARTS.pop((task_id, task_name), None)
    if started is not None:
        TASK_DURATION.labels(task_name).observe(time.perf_counter() - started)


def _record_task_failure(sender: object = None, task_id: str = '', **kwargs: object) -> None:
    task = sender or kwargs.get('task')
    if task is not None:
        TASK_FAILURES.labels(_task_name(task)).inc()


def _install_task_metric_handlers() -> None:
    from celery.signals import task_failure, task_postrun, task_prerun

    task_prerun.connect(_record_task_start, weak=False)
    task_postrun.connect(_record_task_finish, weak=False)
    task_failure.connect(_record_task_failure, weak=False)


_install_task_metric_handlers()


def _collect_db_pool_metrics() -> None:
    try:
        from app.db.session import async_engine, sync_engine, worker_engine

        pools = cast(
            dict[str, Any],
            {
                'sync': sync_engine.pool,
                'worker': worker_engine.pool,
                'async': async_engine.sync_engine.pool,
            },
        )
        for engine, pool in pools.items():
            DB_POOL.labels(engine, 'size').set(pool.size())
            DB_POOL.labels(engine, 'checked_in').set(pool.checkedin())
            DB_POOL.labels(engine, 'checked_out').set(pool.checkedout())
            DB_POOL.labels(engine, 'overflow').set(pool.overflow())
    except (AttributeError, NotImplementedError):
        COLLECTION_ERRORS.labels('database').inc()


def _collect_queue_metrics() -> None:
    from app.core.config import settings

    client: Redis | None = None
    try:
        client = Redis.from_url(
            settings.REDIS_BROKER_URL,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
            retry_on_timeout=False,
        )
        pipeline = client.pipeline(transaction=False)
        for queue in _QUEUES:
            pipeline.llen(queue)
        for queue, depth in zip(_QUEUES, pipeline.execute(), strict=True):
            CELERY_QUEUE_DEPTH.labels(queue).set(depth)
    except (RedisError, OSError, TimeoutError):
        COLLECTION_ERRORS.labels('redis').inc()
    finally:
        if client is not None:
            client.close()


def _collect_breaker_metrics() -> None:
    from app.core.http_client import breaker_snapshots

    for integration, active_state in breaker_snapshots().items():
        for state in ('closed', 'open', 'half_open'):
            BREAKER_STATE.labels(integration, state).set(float(state == active_state))


def route_template_for(scope: Scope) -> str:
    """Full route template (e.g. `/api/v1/listings/{listing_id}`) for labels and logs.

    FastAPI >= 0.13x mounts included routers lazily, so `scope['route'].path` is relative
    to the innermost router and loses outer prefixes such as `/api/v1`. The relative
    template is always a suffix of the concrete path, so the outer prefix is recovered
    from the concrete path's leading segments. Never returns the raw path: that would
    leak personal data into logs and explode metric cardinality.
    """
    route = scope.get('route')
    relative = getattr(route, 'path', None)
    if not isinstance(relative, str):
        return 'unmatched'
    if ':path}' in relative:
        # A path converter spans a variable number of segments; the suffix trick can't
        # apply, and the relative template is still safe to emit.
        return relative
    concrete = str(scope.get('path', ''))
    concrete_segments = concrete.rstrip('/').split('/')
    # The relative template's leading '' (from its leading '/') is not a real segment.
    relative_segments = relative.strip('/').split('/')
    prefix_length = len(concrete_segments) - len(relative_segments)
    if prefix_length <= 0:
        return relative
    return '/'.join(concrete_segments[:prefix_length]) + relative


class RequestMetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or scope.get('path') == '/metrics':
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500

        async def record_status(message: Message) -> None:
            nonlocal status
            if message['type'] == 'http.response.start':
                status = int(message['status'])
            await send(message)

        try:
            await self.app(scope, receive, record_status)
        finally:
            route_template = route_template_for(scope)
            method = scope.get('method', 'UNKNOWN')
            duration = time.perf_counter() - started
            REQUESTS.labels(method, route_template, str(status)).inc()
            REQUEST_DURATION.labels(method, route_template).observe(duration)
            # One structured access line per request (Feature 01 §12). The route *template*
            # is logged, never the raw path/query, which can carry postcodes, VRMs or emails.
            _access_logger.info(
                'http_request',
                method=method,
                route=route_template,
                status=status,
                duration_ms=round(duration * 1000, 2),
            )


def metrics_response(request: Request) -> Response:
    peer = request.client.host if request.client else ''
    try:
        internal_peer = ip_address(peer).is_loopback
    except ValueError:
        internal_peer = False
    if not internal_peer:
        return Response(status_code=404)
    _collect_db_pool_metrics()
    _collect_queue_metrics()
    _collect_breaker_metrics()
    return Response(generate_latest(_REGISTRY), media_type=CONTENT_TYPE_LATEST)
