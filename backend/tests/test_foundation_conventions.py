from __future__ import annotations

import threading
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.api_middleware import JsonBodyLimitMiddleware, RequestContextMiddleware
from app.core.concurrency import ensure_not_stale
from app.core.errors import install_exception_handlers
from app.core.idempotency import IdempotencyMiddleware
from app.core.pagination import (
    CursorPage,
    Page,
    PageParams,
    decode_cursor,
    encode_cursor,
    page_params,
)
from app.db.base import SoftDeleteMixin


class LeadIn(BaseModel):
    message: str


@pytest.fixture
def side_effects() -> list[str]:
    return []


@pytest.fixture
def gate() -> threading.Event:
    return threading.Event()


@pytest.fixture
def api(side_effects: list[str], gate: threading.Event) -> Generator[TestClient, None, None]:
    app = FastAPI()
    install_exception_handlers(app)

    @app.post('/leads', status_code=201)
    def submit_lead(payload: LeadIn) -> dict[str, object]:
        side_effects.append(payload.message)
        return {'lead_number': len(side_effects), 'message': payload.message}

    @app.post('/slow')
    def slow() -> dict[str, bool]:
        side_effects.append('slow')
        gate.wait(5)
        return {'done': True}

    @app.post('/flaky')
    def flaky() -> dict[str, bool]:
        side_effects.append('flaky')
        raise RuntimeError('downstream exploded')

    @app.get('/items')
    def items(params: Annotated[PageParams, Depends(page_params)]) -> Page[int]:
        everything = list(range(1, 46))
        window = everything[params.offset : params.offset + params.page_size]
        return Page[int](items=window, page=params.page, page_size=params.page_size, total=45)

    @app.get('/stale')
    def stale() -> None:
        stored = datetime(2026, 10, 1, tzinfo=UTC)
        ensure_not_stale(stored, stored - timedelta(seconds=1), {'id': 'abc', 'price': 1000})

    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(JsonBodyLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _key() -> str:
    return str(uuid.uuid4())


def test_retry_with_same_key_replays_response_without_repeating_side_effect(
    api: TestClient, side_effects: list[str]
) -> None:
    key = _key()
    first = api.post(
        '/leads', json={'message': 'Is it available?'}, headers={'Idempotency-Key': key}
    )
    retry = api.post(
        '/leads', json={'message': 'Is it available?'}, headers={'Idempotency-Key': key}
    )

    assert first.status_code == retry.status_code == 201
    assert retry.json() == first.json() == {'lead_number': 1, 'message': 'Is it available?'}
    assert retry.headers['idempotent-replayed'] == 'true'
    assert 'idempotent-replayed' not in first.headers
    assert side_effects == ['Is it available?']


def test_requests_without_a_key_are_not_deduplicated(
    api: TestClient, side_effects: list[str]
) -> None:
    api.post('/leads', json={'message': 'a'})
    api.post('/leads', json={'message': 'a'})
    assert side_effects == ['a', 'a']


def test_same_key_with_different_body_is_rejected(api: TestClient, side_effects: list[str]) -> None:
    key = _key()
    api.post('/leads', json={'message': 'first'}, headers={'Idempotency-Key': key})
    reused = api.post('/leads', json={'message': 'second'}, headers={'Idempotency-Key': key})

    assert reused.status_code == 422
    assert reused.json()['code'] == 'idempotency_key_reused'
    assert side_effects == ['first']


def test_keys_are_scoped_to_the_caller(api: TestClient, side_effects: list[str]) -> None:
    key = _key()
    # Different session cookies: one caller must never receive the other's stored response.
    origin = {'Origin': 'http://127.0.0.1:3000'}
    api.post(
        '/leads',
        json={'message': 'm'},
        headers={'Idempotency-Key': key, 'Cookie': 'session=alice', **origin},
    )
    other = api.post(
        '/leads',
        json={'message': 'm'},
        headers={'Idempotency-Key': key, 'Cookie': 'session=bob', **origin},
    )
    assert 'idempotent-replayed' not in other.headers
    assert side_effects == ['m', 'm']


def test_concurrent_duplicate_gets_conflict_instead_of_running_twice(
    api: TestClient, side_effects: list[str], gate: threading.Event
) -> None:
    key = _key()
    results: dict[str, int] = {}

    def first_request() -> None:
        results['first'] = api.post('/slow', headers={'Idempotency-Key': key}).status_code

    worker = threading.Thread(target=first_request)
    worker.start()
    try:
        for _ in range(100):
            if side_effects:
                break
            threading.Event().wait(0.02)
        duplicate = api.post('/slow', headers={'Idempotency-Key': key})
    finally:
        gate.set()
        worker.join(5)

    assert duplicate.status_code == 409
    assert duplicate.json()['code'] == 'idempotency_in_progress'
    assert duplicate.headers['retry-after'] == '1'
    assert results['first'] == 200
    assert side_effects == ['slow']


def test_server_errors_are_not_stored_so_a_retry_runs_again(
    api: TestClient, side_effects: list[str]
) -> None:
    key = _key()
    assert api.post('/flaky', headers={'Idempotency-Key': key}).status_code == 500
    assert api.post('/flaky', headers={'Idempotency-Key': key}).status_code == 500
    assert side_effects == ['flaky', 'flaky']


def test_malformed_idempotency_key_is_rejected(api: TestClient, side_effects: list[str]) -> None:
    response = api.post('/leads', json={'message': 'x'}, headers={'Idempotency-Key': 'short'})
    assert response.status_code == 400
    assert side_effects == []


def test_idempotency_fails_open_when_redis_is_down(
    api: TestClient, side_effects: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from redis import Redis

    from app.core import idempotency

    dead = Redis.from_url('redis://127.0.0.1:6381/15', socket_connect_timeout=0.2)
    monkeypatch.setattr(
        dead, 'set', lambda *a, **k: (_ for _ in ()).throw(idempotency.RedisError())
    )
    monkeypatch.setattr(idempotency, 'get_cache_client', lambda: dead)
    response = api.post('/leads', json={'message': 'x'}, headers={'Idempotency-Key': _key()})
    assert response.status_code == 201
    assert side_effects == ['x']


def test_offset_pagination_envelope_and_bounds(api: TestClient) -> None:
    body = api.get('/items', params={'page': 3, 'page_size': 20}).json()
    assert body == {'items': [41, 42, 43, 44, 45], 'page': 3, 'page_size': 20, 'total': 45}

    too_big = api.get('/items', params={'page_size': 101})
    assert too_big.status_code == 422
    assert too_big.json()['errors'][0]['field'] == 'query.page_size'
    assert api.get('/items', params={'page': 0}).status_code == 422


def test_cursor_round_trip_and_tamper_rejection() -> None:
    position = {'created_at': '2026-10-19T10:00:00+00:00', 'id': '01a1-uuid'}
    assert decode_cursor(encode_cursor(position)) == position
    assert CursorPage[int](items=[1], next_cursor=None).next_cursor is None
    with pytest.raises(Exception, match='cursor is invalid'):
        decode_cursor('!!not-base64!!')
    with pytest.raises(Exception, match='cursor is invalid'):
        decode_cursor('W10')  # base64url('[]'): valid JSON, but not an object


def test_stale_update_returns_409_with_current_representation(api: TestClient) -> None:
    response = api.get('/stale')
    assert response.status_code == 409
    body = response.json()
    assert body['code'] == 'stale_update'
    assert body['current'] == {'id': 'abc', 'price': 1000}
    assert body['status'] == 409  # extension members never override standard ones


def test_soft_delete_mixin_reports_archival() -> None:
    class Listing(SoftDeleteMixin):
        pass

    listing = Listing()
    listing.archived_at = None
    assert listing.is_archived is False
    listing.archived_at = datetime.now(UTC)
    assert listing.is_archived is True
