from __future__ import annotations

import asyncio
import secrets
from collections.abc import Generator

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.api.v1.endpoints import health
from app.core.api_middleware import (
    CookieOriginMiddleware,
    JsonBodyLimitMiddleware,
    RequestContextMiddleware,
)
from app.core.config import Settings
from app.core.errors import AppError, ProblemCode, install_exception_handlers
from app.core.metrics import metrics_response


def _raise_database_unavailable() -> None:
    raise ConnectionError('database is offline')


@pytest.fixture
def isolated_client() -> Generator[TestClient, None, None]:
    app = FastAPI()
    install_exception_handlers(app)

    @app.get('/broken')
    async def broken() -> None:
        raise RuntimeError('internal stack detail')

    @app.get('/app-error')
    async def app_error() -> None:
        raise AppError('safe detail', code=ProblemCode.BAD_REQUEST)

    @app.get('/validation')
    async def validation(value: int) -> dict[str, int]:
        return {'value': value}

    @app.get('/forbidden')
    async def forbidden() -> None:
        raise HTTPException(status_code=403, detail='not allowed')

    @app.post('/body')
    async def body(request: Request) -> dict[str, str]:
        return {'size': str(len(await request.body()))}

    app.add_middleware(JsonBodyLimitMiddleware)
    app.add_middleware(CookieOriginMiddleware)
    app.add_middleware(RequestContextMiddleware)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture(autouse=True)
def _fresh_readiness_cache() -> Generator[None, None, None]:
    health.reset_ready_cache()
    yield
    health.reset_ready_cache()


def test_live_health_does_not_depend_on_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, '_check_database_and_migrations', _raise_database_unavailable)
    response = client.get('/api/v1/health/live')
    assert response.status_code == 200
    assert response.json() == {'status': 'live'}


def test_readiness_names_first_unavailable_dependency(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health, '_check_database_and_migrations', _raise_database_unavailable)
    response = client.get('/api/v1/health/ready')
    assert response.status_code == 503
    assert response.headers['content-type'].startswith('application/problem+json')
    assert 'db' in response.json()['detail']
    assert response.json()['request_id']


def test_readiness_returns_ready_when_all_dependencies_pass(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        '_check_database_and_migrations',
        '_check_storage_bucket',
    ):
        monkeypatch.setattr(health, name, lambda: None)
    monkeypatch.setattr(health, '_check_redis', lambda _: None)
    response = client.get('/api/v1/health/ready')
    assert response.status_code == 200
    assert response.json() == {'status': 'ready'}


def test_readiness_names_every_failing_dependency(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health, '_check_database_and_migrations', _raise_database_unavailable)
    monkeypatch.setattr(health, '_check_storage_bucket', _raise_database_unavailable)
    monkeypatch.setattr(health, '_check_redis', lambda _: None)
    response = client.get('/api/v1/health/ready')
    assert response.status_code == 503
    assert response.json()['detail'] == 'Dependencies unavailable or not ready: db, storage.'


def test_readiness_times_out_a_hung_dependency_without_blocking_the_loop(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading
    import time

    release = threading.Event()
    monkeypatch.setattr(health, '_CHECK_TIMEOUT_SECONDS', 0.3)
    monkeypatch.setattr(health, '_check_storage_bucket', lambda: release.wait(5))
    started = time.monotonic()
    try:
        response = client.get('/api/v1/health/ready')
    finally:
        release.set()
    assert time.monotonic() - started < 2
    assert response.status_code == 503
    assert 'storage' in response.json()['detail']


def test_readiness_verdict_is_cached_briefly(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    for name in ('_check_database_and_migrations', '_check_storage_bucket'):
        monkeypatch.setattr(health, name, lambda: calls.append(1))
    monkeypatch.setattr(health, '_check_redis', lambda _: None)
    for _ in range(5):
        assert client.get('/api/v1/health/ready').status_code == 200
    assert len(calls) == 2


def test_readiness_against_real_test_stack(client: TestClient) -> None:
    response = client.get('/api/v1/health/ready')
    assert response.status_code == 200, response.text


def test_unhandled_exception_returns_generic_problem_without_stack(
    isolated_client: TestClient,
) -> None:
    response = isolated_client.get('/broken')
    assert response.status_code == 500
    assert response.headers['content-type'].startswith('application/problem+json')
    assert response.headers['x-request-id'] == response.json()['request_id']
    assert 'internal stack detail' not in response.text
    assert response.json()['code'] == 'internal_error'


def test_validation_errors_include_each_field(isolated_client: TestClient) -> None:
    response = isolated_client.get('/validation?value=not-an-integer')
    assert response.status_code == 422
    assert response.json()['code'] == 'invalid_input'
    assert response.json()['errors'] == [
        {
            'field': 'query.value',
            'code': 'int_parsing',
            'message': 'Input should be a valid integer, unable to parse string as an integer',
        }
    ]


def test_application_and_http_errors_use_problem_details(isolated_client: TestClient) -> None:
    app_error = isolated_client.get('/app-error')
    http_error = isolated_client.get('/forbidden')
    assert app_error.status_code == 400
    assert app_error.json()['detail'] == 'safe detail'
    assert http_error.status_code == 403
    assert http_error.json()['detail'] == 'not allowed'


def test_spoofed_cloudflare_ip_is_ignored_from_untrusted_peer() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get('/client-ip')
    async def client_ip(request: Request) -> dict[str, str]:
        return {'ip': request.state.client_ip}

    with TestClient(app, client=('198.51.100.20', 1234)) as client:
        response = client.get('/client-ip', headers={'CF-Connecting-IP': '203.0.113.22'})
    assert response.json() == {'ip': '198.51.100.20'}


def test_forwarded_cloudflare_ip_is_accepted_only_from_local_proxy() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get('/client-ip')
    async def client_ip(request: Request) -> dict[str, str]:
        return {'ip': request.state.client_ip}

    with TestClient(app, client=('127.0.0.1', 1234)) as client:
        response = client.get(
            '/client-ip',
            headers={
                'X-Verified-Cloudflare-Peer': '173.245.48.10',
                'CF-Connecting-IP': '203.0.113.22',
            },
        )
        spoofed_proxy = client.get(
            '/client-ip',
            headers={
                'X-Verified-Cloudflare-Peer': '192.0.2.10',
                'CF-Connecting-IP': '203.0.113.22',
            },
        )
    assert response.json() == {'ip': '203.0.113.22'}
    assert spoofed_proxy.json() == {'ip': '127.0.0.1'}


def test_json_body_limit_rejects_payload_over_one_megabyte(isolated_client: TestClient) -> None:
    response = isolated_client.post(
        '/body',
        content=b'x' * (1_048_576 + 1),
        headers={'Content-Type': 'application/json'},
    )
    assert response.status_code == 413
    assert response.headers['content-type'].startswith('application/problem+json')


def test_cookie_mutation_requires_same_origin(isolated_client: TestClient) -> None:
    blocked = isolated_client.post('/body', json={'ok': True}, headers={'Cookie': 'session=test'})
    allowed = isolated_client.post(
        '/body',
        json={'ok': True},
        headers={
            'Cookie': 'session=test',
            'Origin': 'http://127.0.0.1:3000',
        },
    )
    assert blocked.status_code == 403
    assert allowed.status_code == 200


# Random per run: realistic non-placeholder values without committing anything that a
# secret scanner (rightly) flags as a credential.
_DB_PASSWORD = secrets.token_hex(16)
_STRONG_PRODUCTION_SETTINGS = {
    'ENVIRONMENT': 'production',
    'SECRET_KEY': secrets.token_hex(32),
    'POSTGRES_PASSWORD': _DB_PASSWORD,
    'DATABASE_URL': f'postgresql+psycopg://app:{_DB_PASSWORD}@127.0.0.1:5432/autotrader',
    'S3_ACCESS_KEY': secrets.token_hex(10),
    'S3_SECRET_KEY': secrets.token_hex(20),
}


def test_production_accepts_non_placeholder_secrets() -> None:
    assert Settings.model_validate(_STRONG_PRODUCTION_SETTINGS).ENVIRONMENT == 'production'


@pytest.mark.parametrize(
    ('key', 'placeholder', 'reported_as'),
    [
        ('SECRET_KEY', 'local-only-change-this-secret-key', 'SECRET_KEY'),
        ('POSTGRES_PASSWORD', 'local-only-postgres-password', 'POSTGRES_PASSWORD'),
        (
            'DATABASE_URL',
            'postgresql+psycopg://app:local-only-postgres-password@127.0.0.1:5432/autotrader',
            'DATABASE_URL password',
        ),
        ('S3_ACCESS_KEY', 'replace-me', 'S3_ACCESS_KEY'),
        ('S3_SECRET_KEY', 'local-autotrader-secret-change-me', 'S3_SECRET_KEY'),
    ],
)
def test_production_rejects_each_placeholder_secret_by_name(
    key: str, placeholder: str, reported_as: str
) -> None:
    with pytest.raises(ValueError, match=reported_as):
        Settings.model_validate({**_STRONG_PRODUCTION_SETTINGS, key: placeholder})


def test_metrics_endpoint_is_internal_only() -> None:
    app = FastAPI()
    app.add_api_route('/metrics', metrics_response, methods=['GET'])
    with TestClient(app, client=('127.0.0.1', 1234)) as internal:
        assert internal.get('/metrics').status_code == 200
    with TestClient(app, client=('198.51.100.20', 1234)) as external:
        assert external.get('/metrics').status_code == 404


def test_app_database_url_uses_worker_specific_test_database() -> None:
    from app.db.session import sync_engine

    assert sync_engine.url.database is not None
    assert '_test_gw' in sync_engine.url.database


def test_app_connections_carry_five_second_statement_timeout() -> None:
    from app.db.session import async_engine, sync_engine, worker_engine

    for engine in (sync_engine, worker_engine):
        with engine.connect() as connection:
            assert connection.execute(text('SHOW statement_timeout')).scalar_one() == '5s'

    async def async_timeout() -> str:
        try:
            async with async_engine.connect() as connection:
                return (await connection.execute(text('SHOW statement_timeout'))).scalar_one()
        finally:
            await async_engine.dispose()

    # psycopg's async driver needs a selector loop (Windows defaults to Proactor).
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        assert runner.run(async_timeout()) == '5s'


def test_app_rw_can_write_rows_but_cannot_run_ddl() -> None:
    from app.db.session import sync_engine

    with sync_engine.connect() as connection:
        connection.execute(text('SET ROLE app_rw'))
        # DML on application tables is granted...
        connection.execute(text('SELECT count(*) FROM feature_flags')).scalar_one()
        # ...but DDL is not.
        with pytest.raises(DBAPIError) as raised:
            connection.execute(text('CREATE TABLE public.foundation_ddl_probe (id integer)'))
        assert getattr(raised.value.orig, 'sqlstate', None) == '42501'
        connection.rollback()


def test_statement_timeout_returns_clean_service_unavailable() -> None:
    from app.core.api_middleware import RequestContextMiddleware
    from app.core.errors import install_exception_handlers
    from app.db.session import sync_engine

    app = FastAPI()
    install_exception_handlers(app)

    @app.get('/slow-query')
    def slow_query() -> dict[str, bool]:
        with sync_engine.begin() as connection:
            connection.execute(text('SET ROLE app_rw'))
            # Shrink the budget so the test is fast; the cancellation path is identical.
            connection.execute(text("SET LOCAL statement_timeout = '100ms'"))
            connection.execute(text('SELECT pg_sleep(2)'))
        return {'completed': True}

    app.add_middleware(RequestContextMiddleware)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get('/slow-query')

    assert response.status_code == 503
    assert response.headers['content-type'].startswith('application/problem+json')
    body = response.json()
    assert body['code'] == 'dependency_unavailable'
    assert body['request_id']
    assert 'pg_sleep' not in response.text
