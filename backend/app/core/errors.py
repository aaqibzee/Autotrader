from __future__ import annotations

from enum import Enum
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class ProblemCode(str, Enum):
    BAD_REQUEST = 'bad_request'
    INVALID_INPUT = 'invalid_input'
    STALE_UPDATE = 'stale_update'
    IDEMPOTENCY_KEY_REUSED = 'idempotency_key_reused'
    IDEMPOTENCY_IN_PROGRESS = 'idempotency_in_progress'
    INVALID_CURSOR = 'invalid_cursor'
    DEALER_NOT_APPROVED = 'dealer_not_approved'
    PAGE_LIMIT_EXCEEDED = 'page_limit_exceeded'
    DEPENDENCY_UNAVAILABLE = 'dependency_unavailable'
    INTERNAL_ERROR = 'internal_error'


class ProblemValidationError(BaseModel):
    field: str
    code: str
    message: str


class ProblemDetails(BaseModel):
    # Problem types may add members (RFC 9457 §3.2), e.g. `current` on a 409 stale_update.
    model_config = ConfigDict(extra='allow')

    type: str
    title: str
    status: int
    detail: str
    code: str
    request_id: str | None = None
    instance: str
    errors: list[ProblemValidationError] | None = None


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {
        'model': ProblemDetails,
        'description': HTTPStatus(status).phrase,
        'content': {'application/problem+json': {}},
    }
    for status in (400, 403, 404, 409, 413, 422, 500, 503)
}


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: ProblemCode | str = ProblemCode.BAD_REQUEST,
        status_code: int = 400,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.extra = extra or {}
        self.code = code.value if isinstance(code, ProblemCode) else str(code)
        self.status_code = status_code
        super().__init__(message)


def problem_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
    code: ProblemCode | str,
    title: str | None = None,
    errors: list[dict[str, str]] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', None)
    body: dict[str, Any] = {
        'type': 'about:blank',
        'title': title or HTTPStatus(status_code).phrase,
        'status': status_code,
        'detail': detail,
        'code': code.value if isinstance(code, ProblemCode) else str(code),
        'request_id': request_id,
        'instance': request.url.path,
    }
    if errors:
        body['errors'] = errors
    if extra:
        # Extension members never override the standard ones.
        body.update({key: value for key, value in extra.items() if key not in body})
    headers = {'X-Request-ID': request_id} if request_id else None
    return JSONResponse(
        body,
        status_code=status_code,
        media_type='application/problem+json',
        headers=headers,
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem_response(
            request,
            status_code=exc.status_code,
            detail=exc.message,
            code=exc.code,
            extra=exc.extra,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
        return problem_response(
            request,
            status_code=exc.status_code,
            detail=detail,
            code=ProblemCode.BAD_REQUEST if exc.status_code < 500 else ProblemCode.INTERNAL_ERROR,
            title=HTTPStatus(exc.status_code).phrase,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = [
            {
                'field': '.'.join(str(part) for part in error.get('loc', ())),
                'code': str(error.get('type', 'invalid')),
                'message': str(error.get('msg', 'Invalid value')),
            }
            for error in exc.errors()
        ]
        return problem_response(
            request,
            status_code=422,
            detail='One or more request fields are invalid.',
            code=ProblemCode.INVALID_INPUT,
            errors=errors,
        )

    @app.exception_handler(DBAPIError)
    async def handle_database_error(request: Request, exc: DBAPIError) -> JSONResponse:
        sqlstate = getattr(exc.orig, 'sqlstate', None) or getattr(exc.orig, 'pgcode', None)
        if sqlstate == '57014':
            return problem_response(
                request,
                status_code=503,
                detail='The database query exceeded its execution time limit.',
                code=ProblemCode.DEPENDENCY_UNAVAILABLE,
                title='Service Unavailable',
            )
        logger.exception(
            'database_request_failed',
            request_id=getattr(request.state, 'request_id', None),
            sqlstate=sqlstate,
        )
        return problem_response(
            request,
            status_code=500,
            detail='A database operation failed.',
            code=ProblemCode.INTERNAL_ERROR,
            title='Internal Server Error',
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            'unhandled_request_exception',
            request_id=getattr(request.state, 'request_id', None),
            path=request.url.path,
        )
        return problem_response(
            request,
            status_code=500,
            detail='An unexpected error occurred.',
            code=ProblemCode.INTERNAL_ERROR,
            title='Internal Server Error',
        )
