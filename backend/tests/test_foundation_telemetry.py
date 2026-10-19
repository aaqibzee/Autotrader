from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Generator
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import httpx
import pytest
from celery.signals import task_failure, task_postrun, task_prerun
from fastapi.testclient import TestClient
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, TraceState
from sentry_sdk.types import Event
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core import metrics
from app.core.api_middleware import RequestContextMiddleware
from app.core.http_client import (
    IntegrationUnavailable,
    aclose_clients,
    breaker_snapshots,
    configure_integration,
    current_request_id,
    current_trace_id,
    request,
    request_id_context,
    trace_context,
)
from app.core.jobs import dispatch
from app.core.telemetry import redact_sentry_event


@pytest.fixture(autouse=True)
def isolate_otel_context() -> Generator[None, None, None]:
    token = otel_context.attach(otel_context.Context())
    try:
        yield
    finally:
        otel_context.detach(token)


def test_metrics_scrape_includes_pool_queue_task_and_integration_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePipeline:
        def __init__(self) -> None:
            self.queues: list[str] = []

        def llen(self, queue: str) -> FakePipeline:
            self.queues.append(queue)
            return self

        def execute(self) -> list[int]:
            return [2, 3, 4]

    class FakeRedis:
        def __init__(self) -> None:
            self.pipeline_instance = FakePipeline()

        def pipeline(self, *, transaction: bool) -> FakePipeline:
            assert transaction is False
            return self.pipeline_instance

        def close(self) -> None:
            pass

    redis_client = FakeRedis()
    monkeypatch.setattr(metrics.Redis, 'from_url', lambda *args, **kwargs: redis_client)
    task = MagicMock()
    task_name = f'telemetry-test-{uuid.uuid4()}'
    task.name = task_name
    task_id = str(uuid.uuid4())
    task_prerun.send(sender=task, task=task, task_id=task_id)
    task_failure.send(sender=task, task=task, task_id=task_id)
    task_postrun.send(sender=task, task=task, task_id=task_id)
    metrics.record_integration_call('telemetry-test', 0.125, failed=True)

    response = metrics.metrics_response(
        Request(
            {
                'type': 'http',
                'method': 'GET',
                'path': '/metrics',
                'headers': [],
                'client': ('127.0.0.1', 1234),
                'server': ('127.0.0.1', 8000),
                'scheme': 'http',
                'query_string': b'',
            }
        )
    )
    rendered = bytes(response.body).decode()
    assert 'autotrader_db_pool_connections' in rendered
    assert 'autotrader_celery_queue_depth{queue="default"} 2.0' in rendered
    assert 'autotrader_celery_queue_depth{queue="images"} 3.0' in rendered
    assert f'autotrader_celery_task_duration_seconds_count{{task="{task_name}"}} 1.0' in rendered
    assert f'autotrader_celery_task_failures_total{{task="{task_name}"}} 1.0' in rendered
    assert (
        'autotrader_integration_call_duration_seconds_count{integration="telemetry-test"} 1.0'
        in rendered
    )
    assert 'autotrader_integration_failures_total{integration="telemetry-test"} 1.0' in rendered
    denied = metrics.metrics_response(
        Request(
            {
                'type': 'http',
                'method': 'GET',
                'path': '/metrics',
                'headers': [],
                'client': ('203.0.113.10', 1234),
                'server': ('127.0.0.1', 8000),
                'scheme': 'http',
                'query_string': b'',
            }
        )
    )
    assert denied.status_code == 404


@pytest.mark.parametrize(
    ('incoming', 'expected'),
    [
        ('00-' + '1' * 32 + '-' + '2' * 16 + '-01', '00-' + '1' * 32 + '-' + '2' * 16 + '-01'),
        (None, None),
    ],
)
def test_request_middleware_preserves_or_generates_valid_traceparent(
    incoming: str | None,
    expected: str | None,
) -> None:
    async def run() -> tuple[str, str, str, str]:
        seen: dict[str, str] = {}

        async def app(scope, _receive, send) -> None:
            scope_headers = dict(scope['headers'])
            seen['traceparent'] = scope_headers[b'traceparent'].decode()
            seen['request_id'] = scope['state']['request_id']
            seen['trace_id'] = scope['state']['trace_id']
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'ok'})

        headers = [(b'x-request-id', b'caller-request')]
        if incoming is not None:
            headers.append((b'traceparent', incoming.encode()))
        scope = {
            'type': 'http',
            'method': 'GET',
            'path': '/unit',
            'headers': headers,
            'client': ('127.0.0.1', 1234),
            'server': ('127.0.0.1', 8000),
            'scheme': 'http',
            'query_string': b'',
        }
        output = []

        async def send(message) -> None:
            output.append(message)

        async def receive() -> dict[str, object]:
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        await RequestContextMiddleware(app)(scope, receive, send)
        response_headers = dict(output[0]['headers'])
        assert response_headers[b'x-request-id'] == b'caller-request'
        assert response_headers[b'x-trace-id'].decode() == seen['trace_id']
        return (
            seen['traceparent'],
            seen['request_id'],
            seen['trace_id'],
            response_headers[b'x-trace-id'].decode(),
        )

    traceparent, request_id, trace_id, response_trace_id = asyncio.run(run())
    assert request_id == 'caller-request'
    assert trace_id == response_trace_id
    if expected is not None:
        assert traceparent == expected
    else:
        assert re.fullmatch(r'00-[0-9a-f]{32}-[0-9a-f]{16}-00', traceparent)
        assert trace_id == traceparent.split('-')[1]


def test_request_context_uses_active_otel_trace_for_generated_traceparent() -> None:
    trace_id = int('8' * 32, 16)
    span_id = int('9' * 16, 16)
    span_context = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=False,
        trace_flags=TraceFlags(1),
        trace_state=TraceState(),
    )
    seen: dict[str, str] = {}

    async def app(scope, _receive, send) -> None:
        seen['trace_id'] = scope['state']['trace_id']
        seen['traceparent'] = dict(scope['headers'])[b'traceparent'].decode()
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    scope = {
        'type': 'http',
        'method': 'GET',
        'path': '/unit',
        'headers': [],
        'client': ('127.0.0.1', 1234),
        'server': ('127.0.0.1', 8000),
        'scheme': 'http',
        'query_string': b'',
    }
    output = []

    async def send(message) -> None:
        output.append(message)

    async def receive() -> dict[str, object]:
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def run() -> None:
        with trace.use_span(NonRecordingSpan(span_context), end_on_exit=False):
            await RequestContextMiddleware(app)(scope, receive, send)

    asyncio.run(run())
    expected_trace_id = f'{trace_id:032x}'
    expected_traceparent = f'00-{expected_trace_id}-{span_id:016x}-01'
    assert seen == {'trace_id': expected_trace_id, 'traceparent': expected_traceparent}
    assert dict(output[0]['headers'])[b'x-trace-id'] == expected_trace_id.encode()


def test_after_commit_celery_publish_carries_request_and_trace_context() -> None:
    engine = create_engine('sqlite://')
    task = MagicMock()
    task.name = 'telemetry_test_task'
    request_id = 'request-correlation-1'
    trace_id = '3' * 32
    span_id = '4' * 16
    traceparent = f'00-{trace_id}-{span_id}-00'
    with (
        Session(engine) as session,
        request_id_context(request_id),
        trace_context(
            trace_id,
            traceparent,
        ),
    ):
        session.begin()
        dispatch(task, session=session)
        task.apply_async.assert_not_called()
        session.commit()
    headers = task.apply_async.call_args.kwargs['headers']
    assert headers['request_id'] == request_id
    assert headers['traceparent'] == traceparent
    engine.dispose()


def test_correlation_accessors_read_celery_headers_and_active_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import celery

    task = SimpleNamespace(request=SimpleNamespace(headers={'request_id': 'celery-request'}))
    monkeypatch.setattr(celery, 'current_task', task)
    assert current_request_id() == 'celery-request'

    trace_id = int('a' * 32, 16)
    span_context = SpanContext(
        trace_id=trace_id,
        span_id=int('b' * 16, 16),
        is_remote=False,
        trace_flags=TraceFlags(0),
        trace_state=TraceState(),
    )
    with trace.use_span(NonRecordingSpan(span_context), end_on_exit=False):
        assert current_trace_id() == f'{trace_id:032x}'


def test_outbound_http_propagates_request_id_and_traceparent() -> None:
    async def run() -> None:
        observed: list[tuple[str | None, str | None]] = []

        async def respond(request_: httpx.Request) -> httpx.Response:
            observed.append(
                (request_.headers.get('X-Request-ID'), request_.headers.get('traceparent'))
            )
            return httpx.Response(200)

        name = f'trace-propagation-{uuid.uuid4()}'
        trace_id = '5' * 32
        span_id = '6' * 16
        expected_traceparent = f'00-{trace_id}-{span_id}-00'
        configure_integration(name, transport=httpx.MockTransport(respond))
        try:
            with (
                request_id_context('outbound-request'),
                trace_context(
                    trace_id,
                    expected_traceparent,
                ),
            ):
                await request(name, 'GET', 'https://unit.test/path')
            assert observed == [('outbound-request', expected_traceparent)]
        finally:
            await aclose_clients()

    asyncio.run(run())


def test_breaker_snapshot_reports_open_after_five_failures() -> None:
    async def run() -> None:
        async def respond(_: httpx.Request) -> httpx.Response:
            return httpx.Response(503, headers={'Retry-After': '0'})

        name = f'trace-breaker-{uuid.uuid4()}'
        configure_integration(name, max_retries=0, transport=httpx.MockTransport(respond))
        try:
            for _ in range(5):
                with pytest.raises(IntegrationUnavailable):
                    await request(name, 'GET', 'https://unit.test/path')
            assert breaker_snapshots()[name] == 'open'
            metrics._collect_breaker_metrics()
            rendered = metrics.generate_latest(metrics._REGISTRY).decode()
            assert (
                f'autotrader_integration_circuit_breaker{{integration="{name}",state="open"}} 1.0'
            ) in rendered
        finally:
            await aclose_clients()

    asyncio.run(run())


def test_sentry_event_scrubbing_removes_payloads_and_adds_correlation_tags() -> None:
    event = cast(
        Event,
        {
            'user': {'email': 'buyer@example.com'},
            'request': {
                'url': 'https://api.example.test/path?email=buyer@example.com',
                'headers': {'authorization': 'Bearer sensitive-token'},
                'data': {'phone': '+44 7700 900123'},
            },
            'exception': {
                'values': [{'stacktrace': {'frames': [{'vars': {'email': 'buyer@example.com'}}]}}]
            },
        },
    )
    with request_id_context('sentry-request'), trace_context('7' * 32, None):
        redacted = redact_sentry_event(event, {})
    rendered = str(redacted)
    for private_value in ('buyer@example.com', 'sensitive-token', '+44 7700 900123'):
        assert private_value not in rendered
    assert 'user' not in redacted
    assert redacted.get('tags') == {'request_id': 'sentry-request', 'trace_id': '7' * 32}


def test_access_and_third_party_logs_never_carry_raw_personal_data(
    client: TestClient, capfd: pytest.CaptureFixture[str]
) -> None:
    import json
    import logging

    from app.core.telemetry import configure_logging

    # Re-install inside this test's capture window: StreamHandler binds sys.stderr at
    # creation, and pytest swaps that object between phases.
    configure_logging()
    pii = {
        'email': 'jane.doe@example.com',
        'phone': '07700 900123',
        'vrm': 'AB12 CDE',
        'postcode': 'SW1A 1AA',
    }
    response = client.get(
        '/api/v1/health/live', params=pii, headers={'X-Request-ID': 'log-redaction-probe'}
    )
    assert response.status_code == 200
    logging.getLogger('some.thirdparty.lib').warning(
        'delivery failed for %s / %s / %s / %s', *pii.values()
    )

    output = capfd.readouterr()
    combined = output.out + output.err
    for raw in pii.values():
        assert raw not in combined
    access_lines = [
        json.loads(line)
        for line in output.out.splitlines()
        if '"http_request"' in line and 'log-redaction-probe' in line
    ]
    assert len(access_lines) == 1
    access = access_lines[0]
    assert access['route'] == '/api/v1/health/live'
    assert access['status'] == 200
    assert isinstance(access['duration_ms'], float)
    assert access['trace_id']
    assert '[redacted-email]' in combined  # the third-party line was kept, just masked


def test_route_template_restores_outer_router_prefixes_without_raw_values() -> None:
    from fastapi import APIRouter, FastAPI

    from app.core.metrics import route_template_for

    seen: list[str] = []
    inner = APIRouter(prefix='/listings')

    @inner.get('/{listing_id}/photos/{photo_id}')
    def photo(listing_id: str, photo_id: int) -> dict[str, bool]:
        return {'ok': True}

    outer = APIRouter()
    outer.include_router(inner)
    app = FastAPI()
    app.include_router(outer, prefix='/api/v1')

    @app.middleware('http')
    async def capture(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        seen.append(route_template_for(request.scope))
        return response

    with TestClient(app) as test_client:
        test_client.get('/api/v1/listings/AB12CDE/photos/3')
        test_client.get('/api/v1/nope/SW1A1AA')

    assert seen == ['/api/v1/listings/{listing_id}/photos/{photo_id}', 'unmatched']
