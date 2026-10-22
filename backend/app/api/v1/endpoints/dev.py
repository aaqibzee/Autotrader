"""Dev-only probe endpoints for the web app's e2e tests (Feature 03 slice 3.4).

Mounted only when `ENVIRONMENT=local` (local dev, the test suite and the CI e2e job),
never in staging or production, and left out of the OpenAPI schema so the generated web
contract stays production-only.

The form probe (slice 3.10) is a tiny editable record that lets the web app's e2e suite
prove `useApiForm` against the real middleware stack: validation (422 with `errors[]`),
optimistic locking (409 `stale_update` with `current`), idempotent retries (it counts how
often it really ran per `Idempotency-Key`), and on request a 503, a 429 or a hang.
Records live in Redis under a caller-chosen probe id, so parallel tests never share one.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, cast

from fastapi import APIRouter, FastAPI, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.cache import get_cache_client
from app.core.concurrency import ensure_not_stale
from app.core.errors import ProblemCode, problem_response

router = APIRouter(prefix='/dev', tags=['dev'], include_in_schema=False)

# The headers the web app's server clients may or may not forward (web/lib/api/forwarding.ts).
ECHOED_HEADERS = ('cookie', 'authorization', 'x-request-id', 'traceparent', 'x-forwarded-for')


@router.get('/echo-headers')
def echo_headers(request: Request) -> dict[str, bool]:
    """Which of `ECHOED_HEADERS` arrived. Names only: values (a session cookie) are never
    reflected back, even on a dev-only route."""
    return {name: name in request.headers for name in ECHOED_HEADERS}


# --- Form probe (Feature 03 slice 3.10) ---------------------------------------------------

PROBE_TTL_SECONDS = 60 * 60
# Long enough that the web client's 10 s time limit always fires first.
HANG_SECONDS = 15
RATE_LIMIT_RETRY_AFTER_SECONDS = 3
ProbeId = Annotated[str, Path(pattern=r'^[a-z0-9-]{8,64}$')]


class ProbeMode(StrEnum):
    OK = 'ok'
    UNAVAILABLE = 'unavailable'
    RATE_LIMITED = 'rate_limited'
    HANG = 'hang'


class FormProbeIn(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=2, max_length=60)
    email: str = Field(pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', max_length=254)
    price_pence: int = Field(ge=0, le=100_000_000)
    updated_at: datetime
    mode: ProbeMode = ProbeMode.OK


def _record_key(probe_id: str) -> str:
    return f'autotrader:dev:form-probe:{probe_id}'


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load(probe_id: str) -> dict[str, Any]:
    client = get_cache_client()
    raw = cast(str | None, client.get(_record_key(probe_id)))
    if raw is not None:
        return cast(dict[str, Any], json.loads(raw))
    record = {
        'name': 'Ford Fiesta',
        'email': 'sales@example.com',
        'price_pence': 1_249_500,
        'updated_at': _now(),
    }
    _save(probe_id, record)
    return record


def _save(probe_id: str, record: dict[str, Any]) -> None:
    get_cache_client().set(_record_key(probe_id), json.dumps(record), ex=PROBE_TTL_SECONDS)


@router.get('/form-probe/{probe_id}')
def read_form_probe(probe_id: ProbeId) -> dict[str, Any]:
    return _load(probe_id)


@router.post('/form-probe/{probe_id}/touch')
def touch_form_probe(probe_id: ProbeId) -> dict[str, Any]:
    """Someone else saves the record, so the next save with the old token is stale."""
    record = _load(probe_id)
    record.update(
        name=f'{record["name"]} (edited)',
        price_pence=record['price_pence'] + 50_000,
        updated_at=_now(),
    )
    _save(probe_id, record)
    return record


@router.get('/form-probe/{probe_id}/executions')
def form_probe_executions(probe_id: ProbeId) -> dict[str, int]:
    """How many times the save really ran, per Idempotency-Key ("none" without one)."""
    counts = cast(dict[str, str], get_cache_client().hgetall(f'{_record_key(probe_id)}:executions'))
    return {key: int(count) for key, count in counts.items()}


@router.post('/form-probe/{probe_id}', response_model=None)
async def save_form_probe(
    probe_id: ProbeId, body: FormProbeIn, request: Request
) -> dict[str, Any] | JSONResponse:
    client = get_cache_client()
    executions = f'{_record_key(probe_id)}:executions'
    client.hincrby(executions, request.headers.get('idempotency-key', 'none'), 1)
    client.expire(executions, PROBE_TTL_SECONDS)

    if body.mode is ProbeMode.HANG:
        await asyncio.sleep(HANG_SECONDS)
    if body.mode is ProbeMode.UNAVAILABLE:
        return problem_response(
            request,
            status_code=503,
            detail='The lookup service is not responding.',
            code=ProblemCode.INTEGRATION_UNAVAILABLE,
        )
    if body.mode is ProbeMode.RATE_LIMITED:
        response = problem_response(
            request,
            status_code=429,
            detail='Too many attempts.',
            code=ProblemCode.RATE_LIMITED,
        )
        response.headers['Retry-After'] = str(RATE_LIMIT_RETRY_AFTER_SECONDS)
        return response
    if body.name.strip().lower() == 'taken':
        # A server-side rule, plus an error on a field the form does not have: the web
        # client must show that one at form level rather than drop it.
        return problem_response(
            request,
            status_code=422,
            detail='One or more request fields are invalid.',
            code=ProblemCode.INVALID_INPUT,
            errors=[
                {'field': 'body.name', 'code': 'taken', 'message': 'That name is already in use.'},
                {
                    'field': 'body.dealer_id',
                    'code': 'missing',
                    'message': 'Choose a dealership before saving.',
                },
            ],
        )

    record = _load(probe_id)
    ensure_not_stale(datetime.fromisoformat(record['updated_at']), body.updated_at, record)
    saved = {
        'name': body.name,
        'email': body.email,
        'price_pence': body.price_pence,
        'updated_at': _now(),
    }
    _save(probe_id, saved)
    return saved


def mount_dev_routes(app: FastAPI, environment: str) -> bool:
    """Adds the dev routes under `/api/v1` when `environment` is `local`. Returns whether it did."""
    if environment != 'local':
        return False
    app.include_router(router, prefix='/api/v1')
    return True
