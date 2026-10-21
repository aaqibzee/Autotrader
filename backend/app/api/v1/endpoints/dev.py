"""Dev-only probe endpoints for the web app's e2e tests (Feature 03 slice 3.4).

Mounted only when `ENVIRONMENT=local` (local dev, the test suite and the CI e2e job),
never in staging or production, and left out of the OpenAPI schema so the generated web
contract stays production-only. Feature 03 slice 3.10 adds the form probe here.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request

router = APIRouter(prefix='/dev', tags=['dev'], include_in_schema=False)

# The headers the web app's server clients may or may not forward (web/lib/api/forwarding.ts).
ECHOED_HEADERS = ('cookie', 'authorization', 'x-request-id', 'traceparent', 'x-forwarded-for')


@router.get('/echo-headers')
def echo_headers(request: Request) -> dict[str, bool]:
    """Which of `ECHOED_HEADERS` arrived. Names only: values (a session cookie) are never
    reflected back, even on a dev-only route."""
    return {name: name in request.headers for name in ECHOED_HEADERS}


def mount_dev_routes(app: FastAPI, environment: str) -> bool:
    """Adds the dev routes under `/api/v1` when `environment` is `local`. Returns whether it did."""
    if environment != 'local':
        return False
    app.include_router(router, prefix='/api/v1')
    return True
