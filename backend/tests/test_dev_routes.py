"""Dev-only probe routes (Feature 03 slice 3.4): present locally, absent everywhere else."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.dev import ECHOED_HEADERS, mount_dev_routes


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
