from __future__ import annotations

import asyncio
import socket
import uuid
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.http_client import (
    IntegrationUnavailable,
    aclose_clients,
    configure_integration,
    redact_sensitive_data,
    request,
)
from app.core.jobs import dispatch


def test_task_dispatch_waits_for_commit_and_row_visibility() -> None:
    engine = create_engine('sqlite://')
    task = MagicMock()
    task.name = 'test_task'
    observed: list[bool] = []
    task.apply_async.side_effect = lambda **_: observed.append(
        engine.connect().execute(text('SELECT COUNT(*) FROM committed_rows')).scalar_one() == 1
    )
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE committed_rows (id INTEGER PRIMARY KEY)'))

    with Session(engine) as session:
        session.begin()
        session.execute(text('INSERT INTO committed_rows (id) VALUES (1)'))
        dispatch(task, 'row-1', session=session)
        assert task.apply_async.call_count == 0
        session.commit()

    assert observed == [True]
    engine.dispose()


def test_task_dispatch_is_discarded_on_rollback() -> None:
    engine = create_engine('sqlite://')
    task = MagicMock()
    task.name = 'test_task'
    with Session(engine) as session:
        session.begin()
        dispatch(task, 'row-1', session=session)
        session.rollback()
    task.apply_async.assert_not_called()
    engine.dispose()


def test_task_dispatch_requires_an_active_transaction() -> None:
    engine = create_engine('sqlite://')
    task = MagicMock()
    with Session(engine) as session, pytest.raises(RuntimeError, match='active'):
        dispatch(task, session=session)
    engine.dispose()


def test_idempotent_http_requests_retry_transient_responses() -> None:
    async def run() -> None:
        calls = 0

        async def respond(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, headers={'Retry-After': '0'})
            return httpx.Response(200, json={'ok': True})

        name = f'retry-{uuid.uuid4()}'
        configure_integration(name, transport=httpx.MockTransport(respond))
        try:
            response = await request(name, 'GET', 'https://unit.test/path')
            assert response.status_code == 200
            assert response.json() == {'ok': True}
            assert calls == 2
        finally:
            await aclose_clients()

    asyncio.run(run())


def test_non_idempotent_http_request_is_not_retried() -> None:
    async def run() -> None:
        calls = 0

        async def respond(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503)

        name = f'post-{uuid.uuid4()}'
        configure_integration(name, transport=httpx.MockTransport(respond))
        try:
            with pytest.raises(IntegrationUnavailable):
                await request(name, 'POST', 'https://unit.test/lead', json={'name': 'buyer'})
            assert calls == 1
        finally:
            await aclose_clients()

    asyncio.run(run())


def test_five_integration_failures_open_the_circuit_breaker() -> None:
    async def run() -> None:
        calls = 0

        async def respond(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503, headers={'Retry-After': '0'})

        name = f'breaker-{uuid.uuid4()}'
        configure_integration(name, max_retries=0, transport=httpx.MockTransport(respond))
        try:
            for _ in range(5):
                with pytest.raises(IntegrationUnavailable):
                    await request(name, 'GET', 'https://unit.test/unstable')
            with pytest.raises(IntegrationUnavailable, match='circuit breaker is open'):
                await request(name, 'GET', 'https://unit.test/unstable')
            assert calls == 5
        finally:
            await aclose_clients()

    asyncio.run(run())


def test_outbound_request_propagates_request_id() -> None:
    async def run() -> None:
        observed: list[str | None] = []

        async def respond(request_: httpx.Request) -> httpx.Response:
            observed.append(request_.headers.get('X-Request-ID'))
            return httpx.Response(200)

        name = f'request-id-{uuid.uuid4()}'
        configure_integration(name, transport=httpx.MockTransport(respond))
        try:
            await request(name, 'GET', 'https://unit.test/path', request_id='trace-probe')
            assert observed == ['trace-probe']
        finally:
            await aclose_clients()

    asyncio.run(run())


def test_structured_log_redaction_masks_personal_data() -> None:
    event = {
        'message': 'Buyer alex@example.com called +44 7700 900123 about AB12 CDE at SW1A 1AA',
        'authorization': 'Bearer sensitive-token',
    }
    redacted = redact_sensitive_data(None, 'info', event)
    rendered = str(redacted)
    for private_value in (
        'alex@example.com',
        '+44 7700 900123',
        'AB12 CDE',
        'SW1A 1AA',
        'sensitive-token',
    ):
        assert private_value not in rendered


def test_unstubbed_external_network_connection_is_blocked() -> None:
    with pytest.raises(OSError, match='Unstubbed outbound network access blocked'):
        socket.create_connection(('203.0.113.10', 443), timeout=0.1)
