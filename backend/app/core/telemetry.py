from __future__ import annotations

import logging
import os
from collections.abc import MutableMapping
from typing import Any, cast

import sentry_sdk
import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor  # type: ignore[attr-defined]
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.types import Event, Hint
from structlog.contextvars import merge_contextvars

from app.core.config import settings
from app.core.http_client import redact_sensitive_data


def redact_sentry_event(event: Event, hint: Hint) -> Event:
    """Remove common request/identity payloads before an event leaves the process."""
    del hint
    event.pop('user', None)
    request = event.get('request')
    if isinstance(request, dict):
        for key in ('data', 'cookies', 'headers', 'query_string', 'env', 'url'):
            request.pop(key, None)
    breadcrumbs = event.get('breadcrumbs')
    if isinstance(breadcrumbs, dict):
        breadcrumbs.pop('values', None)
    exception = event.get('exception')
    if isinstance(exception, dict):
        values = exception.get('values')
        if isinstance(values, list):
            for value in values:
                if not isinstance(value, dict):
                    continue
                stacktrace = value.get('stacktrace')
                if isinstance(stacktrace, dict):
                    frames = stacktrace.get('frames')
                    if isinstance(frames, list):
                        for frame in frames:
                            if isinstance(frame, dict):
                                frame.pop('vars', None)
    tags = event.setdefault('tags', {})
    if isinstance(tags, dict):
        from app.core.http_client import current_request_id, current_trace_id

        request_id = current_request_id()
        trace_id = current_trace_id()
        if request_id:
            tags['request_id'] = request_id
        if trace_id:
            tags['trace_id'] = trace_id
    mutable_event = cast(MutableMapping[str, Any], event)
    return cast(Event, redact_sensitive_data(None, 'sentry', mutable_event))


def configure_logging() -> None:
    timestamper = structlog.processors.TimeStamper(fmt='iso', utc=True)
    shared_processors: list[Any] = [
        merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        redact_sensitive_data,
    ]
    structlog.configure(
        processors=[*shared_processors, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Third-party libraries (Celery, SQLAlchemy, httpx, uvicorn.error) log through stdlib
    # logging. Send them through the same redacting JSON pipeline; otherwise their
    # messages are a side door for personal data into the log store.
    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # uvicorn's access log prints raw paths and query strings; the API logs its own
    # structured line per request instead (RequestMetricsMiddleware), keyed by route template.
    logging.getLogger('uvicorn.access').disabled = True
    # The readiness probe inspects the Alembic revision every few seconds; its INFO
    # chatter ('Context impl PostgresqlImpl') would dominate the log volume.
    logging.getLogger('alembic.runtime.migration').setLevel(logging.WARNING)


_configured_pid: int | None = None
_provider: TracerProvider | None = None


def configure_process_telemetry(service_name: str) -> TracerProvider:
    """Logging, error tracking and tracing for one OS process (API, worker or beat).

    Idempotent per PID: prefork Celery children inherit the parent's state but must
    re-create exporters after fork, so a new PID always re-initialises.
    """
    global _configured_pid, _provider
    if _configured_pid == os.getpid() and _provider is not None:
        return _provider

    configure_logging()
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN or None,
        environment=settings.ENVIRONMENT,
        server_name=service_name,
        send_default_pii=False,
        # Every error is reported; only performance traces are sampled.
        sample_rate=1.0,
        traces_sample_rate=_trace_sample_rate() if settings.SENTRY_DSN else 0.0,
        integrations=[FastApiIntegration(), CeleryIntegration()],
        before_send=redact_sentry_event,
    )

    provider = TracerProvider(
        resource=Resource.create(
            {
                'service.name': service_name,
                'deployment.environment': settings.ENVIRONMENT,
            }
        ),
        # Follow the caller's decision when propagated (SSR -> API -> Celery stay whole).
        sampler=ParentBased(TraceIdRatioBased(_trace_sample_rate())),
    )
    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT))
        )
    trace.set_tracer_provider(provider)

    from app.db.session import sync_engine, worker_engine

    # Instrumentors are singletons: a second instrument() call is a silent no-op, so both
    # engines must be passed in one call.
    _instrument_once(SQLAlchemyInstrumentor(), provider, engines=[sync_engine, worker_engine])
    _instrument_once(HTTPXClientInstrumentor(), provider)
    _instrument_once(CeleryInstrumentor(), provider)
    _instrument_once(RedisInstrumentor(), provider)

    _configured_pid = os.getpid()
    _provider = provider
    return provider


def _trace_sample_rate() -> float:
    return 0.1 if settings.ENVIRONMENT == 'production' else 1.0


def _instrument_once(
    instrumentor: BaseInstrumentor, provider: TracerProvider, **options: Any
) -> None:
    if not instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.instrument(tracer_provider=provider, **options)


def configure_telemetry(app: FastAPI) -> None:
    provider = configure_process_telemetry('autotrader-api')
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    from app.core.celery_app import celery_app

    celery_app.conf.worker_send_task_events = True
