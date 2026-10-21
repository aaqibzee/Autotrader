"""Problem codes are a typed contract between the API and the web app (Feature 03 A5)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import ProblemCode, install_exception_handlers


def test_openapi_exports_every_problem_code_as_an_enum(client: TestClient) -> None:
    schemas = client.get('/openapi.json').json()['components']['schemas']
    code = schemas['ProblemDetails']['properties']['code']
    assert code == {'$ref': '#/components/schemas/ProblemCode'}
    # The web app's problem-ui table is typed from this list.
    assert sorted(schemas['ProblemCode']['enum']) == sorted(member.value for member in ProblemCode)


def test_codes_raised_by_later_features_exist() -> None:
    assert ProblemCode.RATE_LIMITED.value == 'rate_limited'
    assert ProblemCode.INTEGRATION_UNAVAILABLE.value == 'integration_unavailable'


def test_rate_limited_responses_are_documented(client: TestClient) -> None:
    ready = client.get('/openapi.json').json()['paths']['/api/v1/health/ready']['get']
    assert '429' in ready['responses']


def _app_raising(status_code: int) -> TestClient:
    app = FastAPI()
    install_exception_handlers(app)

    @app.get('/boom')
    def boom() -> None:
        raise HTTPException(status_code=status_code)

    return TestClient(app, raise_server_exceptions=False)


def test_unknown_route_is_not_found_not_bad_request() -> None:
    response = _app_raising(400).get('/no-such-route')
    assert response.status_code == 404
    assert response.json()['code'] == 'not_found'


def test_http_exception_codes_by_status() -> None:
    assert _app_raising(404).get('/boom').json()['code'] == 'not_found'
    assert _app_raising(405).get('/boom').json()['code'] == 'bad_request'
    assert _app_raising(502).get('/boom').json()['code'] == 'internal_error'
