from __future__ import annotations

import asyncio
import contextvars
import random
import re
import threading
import time
import uuid
from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
import structlog
from opentelemetry import propagate, trace

logger = structlog.get_logger(__name__)
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'autotrader_request_id', default=None
)
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'autotrader_trace_id', default=None
)
_traceparent: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'autotrader_traceparent', default=None
)
_SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE'}
_RETRYABLE_STATUSES = {429, 502, 503, 504}
_RETRYABLE_TRANSPORT_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)
_SENSITIVE_KEYS = re.compile(
    r'(authorization|cookie|password|secret|token|api[_-]?key|email|phone|vrm|postcode)',
    re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.IGNORECASE)
_VRM_PATTERN = re.compile(r'\b[A-Z]{2}\d{2}\s?[A-Z]{3}\b', re.IGNORECASE)
_POSTCODE_PATTERN = re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b', re.IGNORECASE)
_UK_PHONE_PATTERN = re.compile(r'(?<!\w)(?:\+44|0)\s?\d(?:[\s().-]?\d){8,10}(?!\w)')


@contextmanager
def request_id_context(request_id: str | None) -> Iterator[None]:
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


def current_request_id() -> str | None:
    request_id = _request_id.get()
    if request_id:
        return request_id
    from celery import current_task

    task_request = getattr(current_task, 'request', None)
    headers = getattr(task_request, 'headers', None)
    request_id = headers.get('request_id') if isinstance(headers, Mapping) else None
    return request_id if isinstance(request_id, str) else None


@contextmanager
def trace_context(trace_id: str | None, traceparent: str | None) -> Iterator[None]:
    trace_token = _trace_id.set(trace_id)
    parent_token = _traceparent.set(traceparent)
    try:
        yield
    finally:
        _traceparent.reset(parent_token)
        _trace_id.reset(trace_token)


def current_trace_id() -> str | None:
    trace_id = _trace_id.get()
    if trace_id:
        return trace_id
    span_context = trace.get_current_span().get_span_context()
    return f'{span_context.trace_id:032x}' if span_context.is_valid else None


def current_traceparent() -> str | None:
    return _traceparent.get()


def _redact_string(value: str) -> str:
    value = _EMAIL_PATTERN.sub('[redacted-email]', value)
    value = _VRM_PATTERN.sub('[redacted-vrm]', value)
    value = _POSTCODE_PATTERN.sub('[redacted-postcode]', value)
    return _UK_PHONE_PATTERN.sub('[redacted-phone]', value)


def _redact_value(key: str, value: Any) -> Any:
    if _SENSITIVE_KEYS.search(key):
        return '[redacted]'
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Mapping):
        return {
            str(child_key): _redact_value(str(child_key), child)
            for child_key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(key, child) for child in value]
    return value


def redact_sensitive_data(
    logger_: Any,
    method: str,
    event_dict: MutableMapping[str, Any],
) -> dict[str, Any]:
    """Structlog processor interface for local structured-log redaction."""
    return {key: _redact_value(key, value) for key, value in event_dict.items()}


def _safe_endpoint(url: str | httpx.URL) -> str:
    parts = urlsplit(str(url))
    host = parts.hostname or 'unknown-host'
    if parts.port is not None:
        host = f'{host}:{parts.port}'
    safe_parts = []
    for segment in parts.path.split('/'):
        if (
            len(segment) > 32
            or _EMAIL_PATTERN.search(segment)
            or _VRM_PATTERN.search(segment)
            or _POSTCODE_PATTERN.search(segment)
            or _UK_PHONE_PATTERN.search(segment)
        ):
            safe_parts.append(':redacted')
        else:
            safe_parts.append(_redact_string(segment))
    return host + '/'.join(safe_parts)


@dataclass(frozen=True)
class IntegrationConfig:
    connect_timeout: float = 2.0
    read_timeout: float = 4.0
    total_timeout: float = 6.0
    max_retries: int = 2
    transport: httpx.AsyncBaseTransport | None = None


class IntegrationUnavailable(RuntimeError):
    def __init__(
        self,
        integration: str,
        message: str = 'integration is temporarily unavailable',
        *,
        retry_after: float | None = None,
    ) -> None:
        self.integration = integration
        self.retry_after = retry_after
        super().__init__(f'{integration}: {message}')


class _RetryableStatusError(RuntimeError):
    def __init__(self, status_code: int, retry_after: float | None = None) -> None:
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f'transient HTTP status {status_code}')


class _CircuitBreaker:
    def __init__(self) -> None:
        self.failures = 0
        self.open_until = 0.0
        self.probe_in_progress = False
        self.lock = threading.Lock()

    def before_request(self, integration: str) -> bool:
        with self.lock:
            now = time.monotonic()
            if self.open_until > now:
                raise IntegrationUnavailable(
                    integration,
                    'circuit breaker is open',
                    retry_after=self.open_until - now,
                )
            if self.open_until:
                if self.probe_in_progress:
                    raise IntegrationUnavailable(
                        integration,
                        'circuit breaker recovery probe is already running',
                        retry_after=1.0,
                    )
                self.probe_in_progress = True
                return True
            return False

    def record_success(self, is_probe: bool) -> None:
        with self.lock:
            self.failures = 0
            self.open_until = 0.0
            if is_probe:
                self.probe_in_progress = False

    def record_failure(self, is_probe: bool) -> None:
        with self.lock:
            self.failures = max(5, self.failures) if is_probe else self.failures + 1
            if self.failures >= 5:
                self.open_until = time.monotonic() + 30.0
            self.probe_in_progress = False

    def abandon_probe(self, is_probe: bool) -> None:
        if is_probe:
            with self.lock:
                self.probe_in_progress = False

    def snapshot(self) -> str:
        with self.lock:
            if self.open_until > time.monotonic():
                return 'open'
            if self.open_until:
                return 'half_open'
            return 'closed'


_configs: dict[str, IntegrationConfig] = {}
_clients: dict[str, httpx.AsyncClient] = {}
_breakers: dict[str, _CircuitBreaker] = {}
_registry_lock = threading.Lock()


def breaker_snapshots() -> dict[str, str]:
    with _registry_lock:
        breakers = list(_breakers.items())
    return {integration: breaker.snapshot() for integration, breaker in breakers}


def configure_integration(
    integration: str,
    *,
    connect_timeout: float = 2.0,
    read_timeout: float = 4.0,
    total_timeout: float = 6.0,
    max_retries: int = 2,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    if not integration.strip():
        raise ValueError('integration name must not be empty')
    if min(connect_timeout, read_timeout, total_timeout) <= 0:
        raise ValueError('HTTP timeouts must be positive')
    if max_retries < 0:
        raise ValueError('max_retries must not be negative')
    with _registry_lock:
        if integration in _clients:
            raise RuntimeError(f'{integration} client has already been created')
        _configs[integration] = IntegrationConfig(
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            total_timeout=total_timeout,
            max_retries=max_retries,
            transport=transport,
        )


def _integration_config(integration: str) -> IntegrationConfig:
    with _registry_lock:
        return _configs.get(integration, IntegrationConfig())


def get_client(integration: str) -> httpx.AsyncClient:
    with _registry_lock:
        client = _clients.get(integration)
        if client is None:
            config = _configs.get(integration, IntegrationConfig())
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=config.connect_timeout,
                    read=config.read_timeout,
                    write=config.read_timeout,
                    pool=config.connect_timeout,
                ),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                headers={'User-Agent': 'Autotrader/1.0'},
                transport=config.transport,
            )
            _clients[integration] = client
        return client


def _breaker(integration: str) -> _CircuitBreaker:
    with _registry_lock:
        return _breakers.setdefault(integration, _CircuitBreaker())


def _retry_after(response: httpx.Response, attempt: int) -> float:
    value = response.headers.get('Retry-After')
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return random.uniform(0.0, min(2.0, 0.25 * (2**attempt)))


async def request(
    integration: str,
    method: str,
    url: str | httpx.URL,
    *,
    idempotent: bool | None = None,
    request_id: str | None = None,
    **request_options: Any,
) -> httpx.Response:
    config = _integration_config(integration)
    breaker = _breaker(integration)
    started_at = time.monotonic()
    from app.core.metrics import record_integration_call

    try:
        is_probe = breaker.before_request(integration)
    except IntegrationUnavailable:
        record_integration_call(integration, time.monotonic() - started_at, failed=True)
        raise
    method = method.upper()
    may_retry = method in _SAFE_METHODS if idempotent is None else idempotent
    headers = dict(request_options.pop('headers', {}) or {})
    existing_id = None
    for name in list(headers):
        if name.lower() == 'x-request-id':
            existing_id = existing_id or headers.pop(name)
    propagated_id = request_id or existing_id or current_request_id() or str(uuid.uuid4())
    headers['X-Request-ID'] = propagated_id
    supplied_traceparent = next(
        (value for name, value in headers.items() if name.lower() == 'traceparent'),
        None,
    )
    for name in list(headers):
        if name.lower() == 'traceparent':
            headers.pop(name)
    explicit_traceparent = current_traceparent() or supplied_traceparent
    if explicit_traceparent:
        headers['traceparent'] = explicit_traceparent
    else:
        propagate.inject(headers)
    endpoint = _safe_endpoint(url)
    retry_count = config.max_retries if may_retry else 0
    last_retry_after: float | None = None

    try:
        async with asyncio.timeout(config.total_timeout):
            for attempt in range(retry_count + 1):
                try:
                    response = await get_client(integration).request(
                        method,
                        url,
                        headers=headers,
                        **request_options,
                    )
                except _RETRYABLE_TRANSPORT_ERRORS:
                    if attempt >= retry_count:
                        raise
                    await asyncio.sleep(random.uniform(0.0, min(2.0, 0.25 * (2**attempt))))
                    continue

                if response.status_code in _RETRYABLE_STATUSES:
                    last_retry_after = _retry_after(response, attempt)
                    if attempt < retry_count:
                        await response.aclose()
                        await asyncio.sleep(last_retry_after)
                        continue
                    status_error = _RetryableStatusError(
                        response.status_code,
                        retry_after=last_retry_after,
                    )
                    await response.aclose()
                    raise status_error

                if response.status_code >= 500:
                    breaker.record_failure(is_probe)
                else:
                    breaker.record_success(is_probe)
                record_integration_call(
                    integration,
                    time.monotonic() - started_at,
                    failed=response.status_code >= 500,
                )
                _log_call(
                    integration,
                    endpoint,
                    response.status_code,
                    started_at,
                    propagated_id,
                )
                return response
    except asyncio.CancelledError:
        breaker.abandon_probe(is_probe)
        raise
    except (TimeoutError, httpx.TransportError, _RetryableStatusError) as exc:
        breaker.record_failure(is_probe)
        record_integration_call(integration, time.monotonic() - started_at, failed=True)
        status = exc.status_code if isinstance(exc, _RetryableStatusError) else None
        _log_call(
            integration,
            endpoint,
            status,
            started_at,
            propagated_id,
            error=type(exc).__name__,
        )
        reason = 'request timed out' if isinstance(exc, TimeoutError) else 'request failed'
        retry_after = exc.retry_after if isinstance(exc, _RetryableStatusError) else None
        raise IntegrationUnavailable(
            integration,
            reason,
            retry_after=retry_after,
        ) from exc
    except BaseException:
        breaker.abandon_probe(is_probe)
        raise

    breaker.abandon_probe(is_probe)
    raise IntegrationUnavailable(integration)


def _log_call(
    integration: str,
    endpoint: str,
    status: int | None,
    started_at: float,
    request_id: str,
    *,
    error: str | None = None,
) -> None:
    fields: dict[str, Any] = {
        'integration': integration,
        'endpoint': endpoint,
        'status': status,
        'latency_ms': round((time.monotonic() - started_at) * 1000, 2),
        'request_id': request_id,
    }
    if error:
        fields['error'] = error
    logger.info('outbound_http', **redact_sensitive_data(logger, 'info', fields))


async def aclose_clients() -> None:
    with _registry_lock:
        clients = list(_clients.values())
        _clients.clear()
    for client in clients:
        await client.aclose()
