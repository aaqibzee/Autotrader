"""Dev-only probe routes (Feature 03 slice 3.4): present locally, absent everywhere else."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import dev
from app.api.v1.endpoints.dev import (
    ECHOED_HEADERS,
    RATE_LIMIT_RETRY_AFTER_SECONDS,
    mount_dev_routes,
)


def _status(app: FastAPI, path: str = '/api/v1/dev/echo-headers') -> int:
    # Behavioural, not `app.routes`: FastAPI mounts included routers lazily, so a route's
    # listed path does not show the prefix (Feature 01 implementation notes).
    with TestClient(app) as client:
        return client.get(path).status_code


@pytest.mark.parametrize('environment', ['staging', 'production'])
def test_dev_routes_are_never_mounted_outside_local(environment: str) -> None:
    app = FastAPI()
    assert mount_dev_routes(app, environment) is False
    assert _status(app) == 404


def test_dev_routes_mount_locally() -> None:
    app = FastAPI()
    assert mount_dev_routes(app, 'local') is True
    assert _status(app) == 200


def test_dev_routes_are_left_out_of_the_openapi_contract(client: TestClient) -> None:
    # The generated web types must describe production only.
    schema_paths = client.get('/openapi.json').json()['paths']
    assert not any(path.startswith('/api/v1/dev') for path in schema_paths)


def test_echo_headers_reports_names_only(client: TestClient) -> None:
    secret = 'session-value-that-must-not-be-reflected'
    response = client.get(
        '/api/v1/dev/echo-headers',
        headers={'cookie': f'session={secret}', 'x-request-id': 'probe-1'},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(ECHOED_HEADERS)
    assert body['cookie'] is True
    assert body['x-request-id'] is True
    assert body['authorization'] is False
    assert secret not in response.text


def test_echo_headers_without_a_cookie(client: TestClient) -> None:
    assert client.get('/api/v1/dev/echo-headers').json()['cookie'] is False


# --- Form probe (Feature 03 slice 3.10) -------------------------------------------------


@pytest.mark.parametrize('environment', ['staging', 'production'])
def test_form_probe_is_absent_outside_local(environment: str) -> None:
    app = FastAPI()
    mount_dev_routes(app, environment)
    with TestClient(app) as api:
        assert api.get('/api/v1/dev/form-probe/probe-absent').status_code == 404
        assert api.post('/api/v1/dev/form-probe/probe-absent', json={}).status_code == 404


def _probe_id() -> str:
    return f'probe-{uuid.uuid4().hex[:12]}'


def _payload(record: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {
        'name': record['name'],
        'email': record['email'],
        'price_pence': record['price_pence'],
        'updated_at': record['updated_at'],
        **changes,
    }


def test_form_probe_saves_and_rejects_a_stale_token(client: TestClient) -> None:
    probe = _probe_id()
    original = client.get(f'/api/v1/dev/form-probe/{probe}').json()

    saved = client.post(
        f'/api/v1/dev/form-probe/{probe}', json=_payload(original, name='Ford Focus')
    )
    assert saved.status_code == 200
    assert saved.json()['name'] == 'Ford Focus'
    assert saved.json()['updated_at'] != original['updated_at']

    stale = client.post(f'/api/v1/dev/form-probe/{probe}', json=_payload(original, name='Mine'))
    assert stale.status_code == 409
    body = stale.json()
    assert body['code'] == 'stale_update'
    assert body['current'] == saved.json()

    # Re-applying on top of the current token succeeds.
    reapplied = client.post(
        f'/api/v1/dev/form-probe/{probe}',
        json=_payload(original, name='Mine', updated_at=body['current']['updated_at']),
    )
    assert reapplied.status_code == 200


def test_form_probe_touch_makes_the_open_token_stale(client: TestClient) -> None:
    probe = _probe_id()
    original = client.get(f'/api/v1/dev/form-probe/{probe}').json()
    touched = client.post(f'/api/v1/dev/form-probe/{probe}/touch').json()
    assert touched['updated_at'] != original['updated_at']
    response = client.post(f'/api/v1/dev/form-probe/{probe}', json=_payload(original))
    assert response.status_code == 409
    assert response.json()['current']['name'] == touched['name']


def test_form_probe_validation_errors_name_their_fields(client: TestClient) -> None:
    probe = _probe_id()
    record = client.get(f'/api/v1/dev/form-probe/{probe}').json()
    response = client.post(
        f'/api/v1/dev/form-probe/{probe}',
        json=_payload(record, name='x', email='not-an-email', price_pence=-1),
    )
    assert response.status_code == 422
    fields = {error['field'] for error in response.json()['errors']}
    assert fields == {'body.name', 'body.email', 'body.price_pence'}


def test_form_probe_reports_an_error_on_a_field_the_form_does_not_have(client: TestClient) -> None:
    probe = _probe_id()
    record = client.get(f'/api/v1/dev/form-probe/{probe}').json()
    response = client.post(f'/api/v1/dev/form-probe/{probe}', json=_payload(record, name='Taken'))
    assert response.status_code == 422
    assert [error['field'] for error in response.json()['errors']] == [
        'body.name',
        'body.dealer_id',
    ]


def test_form_probe_can_answer_503_or_429(client: TestClient) -> None:
    probe = _probe_id()
    record = client.get(f'/api/v1/dev/form-probe/{probe}').json()

    unavailable = client.post(
        f'/api/v1/dev/form-probe/{probe}', json=_payload(record, mode='unavailable')
    )
    assert unavailable.status_code == 503
    assert unavailable.json()['code'] == 'integration_unavailable'

    limited = client.post(
        f'/api/v1/dev/form-probe/{probe}', json=_payload(record, mode='rate_limited')
    )
    assert limited.status_code == 429
    assert limited.json()['code'] == 'rate_limited'
    assert limited.headers['retry-after'] == str(RATE_LIMIT_RETRY_AFTER_SECONDS)


def test_form_probe_hang_mode_waits_then_answers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dev, 'HANG_SECONDS', 0)
    probe = _probe_id()
    record = client.get(f'/api/v1/dev/form-probe/{probe}').json()
    assert (
        client.post(
            f'/api/v1/dev/form-probe/{probe}', json=_payload(record, mode='hang')
        ).status_code
        == 200
    )


def test_form_probe_runs_once_per_idempotency_key_behind_the_real_middleware(
    client: TestClient,
) -> None:
    probe = _probe_id()
    record = client.get(f'/api/v1/dev/form-probe/{probe}').json()
    key = str(uuid.uuid4())

    first = client.post(
        f'/api/v1/dev/form-probe/{probe}', json=_payload(record), headers={'Idempotency-Key': key}
    )
    retry = client.post(
        f'/api/v1/dev/form-probe/{probe}', json=_payload(record), headers={'Idempotency-Key': key}
    )
    assert first.status_code == retry.status_code == 200
    assert retry.json() == first.json()
    assert retry.headers['idempotent-replayed'] == 'true'

    client.post(f'/api/v1/dev/form-probe/{probe}', json=_payload(first.json()))
    assert client.get(f'/api/v1/dev/form-probe/{probe}/executions').json() == {key: 1, 'none': 1}


def test_form_probe_ids_are_constrained(client: TestClient) -> None:
    assert client.get('/api/v1/dev/form-probe/NOT_VALID').status_code == 422
