from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import anyio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints.dev import mount_dev_routes
from app.api.v1.endpoints.health import (
    health_live as health_live_endpoint,
)
from app.api.v1.endpoints.health import (
    health_ready as health_ready_endpoint,
)
from app.api.v1.endpoints.health import (
    router as health_router,
)
from app.api.v1.router import api_router
from app.core.api_middleware import (
    CookieOriginMiddleware,
    JsonBodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.config import settings
from app.core.errors import PROBLEM_RESPONSES, install_exception_handlers
from app.core.idempotency import IdempotencyMiddleware
from app.core.metrics import RequestMetricsMiddleware, metrics_response
from app.core.telemetry import configure_telemetry


@asynccontextmanager
async def lifespan(_: FastAPI):
    anyio.to_thread.current_default_thread_limiter().total_tokens = settings.THREADPOOL_SIZE
    yield


app = FastAPI(
    title='Autotrader API',
    version='0.1.0',
    lifespan=lifespan,
    responses=PROBLEM_RESPONSES,
)
app.include_router(api_router, prefix='/api/v1')
app.include_router(health_router)
# Probe endpoints for the web e2e suite; local only, never in staging or production.
mount_dev_routes(app, settings.ENVIRONMENT)
install_exception_handlers(app)

if settings.ENVIRONMENT == 'local':
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, 'http://localhost:3000'],
        allow_credentials=True,
        allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
        allow_headers=['Accept', 'Content-Type', 'X-Request-ID', 'Idempotency-Key'],
        expose_headers=['X-Request-ID', 'X-Trace-ID'],
    )
# Innermost first: idempotency runs after the origin check, so a cross-site POST is
# rejected before it can claim or replay a key.
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(CookieOriginMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(JsonBodyLimitMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS.split(','))
app.add_middleware(RequestMetricsMiddleware)
app.add_middleware(RequestContextMiddleware)

configure_telemetry(app)

_default_openapi = app.openapi


def _openapi_with_problem_media_type() -> dict[str, Any]:
    schema = _default_openapi()
    for path_item in schema.get('paths', {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.get('responses', {})
            if not isinstance(responses, dict):
                continue
            for response in responses.values():
                if not isinstance(response, dict):
                    continue
                content = response.get('content')
                if isinstance(content, dict) and 'application/problem+json' in content:
                    # Move (not drop) the ProblemDetails schema FastAPI generated under
                    # application/json, or every error response is typed `unknown` in the
                    # generated web client.
                    json_body = content.pop('application/json', None)
                    if isinstance(json_body, dict) and 'schema' in json_body:
                        content['application/problem+json'].setdefault(
                            'schema', json_body['schema']
                        )
    return schema


app.openapi = _openapi_with_problem_media_type


@app.get('/metrics', include_in_schema=False)
async def metrics(request: Request):
    return metrics_response(request)


@app.get('/health/live', include_in_schema=False)
async def health_live_compat():
    return await health_live_endpoint()


@app.get('/health/ready', response_model=dict[str, str], include_in_schema=False)
async def health_ready_compat(request: Request) -> dict[str, str] | JSONResponse:
    return await health_ready_endpoint(request)


@app.get('/')
async def root() -> dict[str, str]:
    return {'status': 'ok', 'environment': settings.ENVIRONMENT}
