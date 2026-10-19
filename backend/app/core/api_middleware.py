from __future__ import annotations

import re
import uuid
from urllib.parse import urlsplit

import sentry_sdk
import structlog
from fastapi import Request
from opentelemetry import trace
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.client_ip import resolve_client_ip
from app.core.config import settings
from app.core.errors import ProblemCode, problem_response
from app.core.http_client import request_id_context, trace_context
from app.db.uuid7 import uuid7

_REQUEST_ID = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')
_TRACEPARENT = re.compile(
    r'^([\da-f]{2})-([\da-f]{32})-([\da-f]{16})-([\da-f]{2})(?:-([\da-f]{2,}))?$'
)
_JSON_CONTENT_TYPE = 'application/json'
_BODY_LIMIT = 1_048_576


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope['headers']}
        incoming_id = headers.get(b'x-request-id', b'').decode('latin-1')
        request_id = incoming_id if _REQUEST_ID.fullmatch(incoming_id) else str(uuid7())
        trace_parent = headers.get(b'traceparent', b'').decode('latin-1')
        trace_match = _TRACEPARENT.fullmatch(trace_parent)
        valid_traceparent = bool(
            trace_match
            and trace_match.group(1) != 'ff'
            and trace_match.group(2) != '0' * 32
            and trace_match.group(3) != '0' * 16
            and (trace_match.group(1) != '00' or trace_match.group(5) is None)
        )
        if valid_traceparent and trace_match:
            trace_id = trace_match.group(2)
        else:
            trace_id = uuid.uuid4().hex
            span_id = uuid.uuid4().hex[:16]
            trace_parent = f'00-{trace_id}-{span_id}-00'

        active_span_context = trace.get_current_span().get_span_context()
        if active_span_context.is_valid:
            trace_id = f'{active_span_context.trace_id:032x}'
            if not valid_traceparent:
                trace_parent = (
                    f'00-{trace_id}-{active_span_context.span_id:016x}'
                    f'-{int(active_span_context.trace_flags):02x}'
                )
        headers[b'traceparent'] = trace_parent.encode('ascii')
        scope['headers'] = [
            (key, value) for key, value in scope['headers'] if key.lower() != b'traceparent'
        ] + [(b'traceparent', trace_parent.encode('ascii'))]
        state = scope.setdefault('state', {})
        state['request_id'] = request_id
        state['trace_id'] = trace_id
        state['traceparent'] = trace_parent
        peer = scope.get('client')
        state['client_ip'] = resolve_client_ip(
            peer[0] if peer else None,
            headers.get(b'x-verified-cloudflare-peer', b'').decode('latin-1'),
            headers.get(b'cf-connecting-ip', b'').decode('latin-1'),
        )

        async def send_with_context(message: Message) -> None:
            if message['type'] == 'http.response.start':
                response_headers = list(message.get('headers', []))
                response_headers.extend(
                    [
                        (b'x-request-id', request_id.encode('ascii')),
                        (b'x-trace-id', trace_id.encode('ascii')),
                    ]
                )
                message['headers'] = response_headers
            await send(message)

        with (
            request_id_context(request_id),
            trace_context(
                trace_id,
                trace_parent,
            ),
            structlog.contextvars.bound_contextvars(
                request_id=request_id,
                trace_id=trace_id,
                client_ip=state['client_ip'],
            ),
            sentry_sdk.isolation_scope() as sentry_scope,
        ):
            sentry_scope.set_tag('request_id', request_id)
            sentry_scope.set_tag('trace_id', trace_id)
            await self.app(scope, receive, send_with_context)


class JsonBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: int = _BODY_LIMIT) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope['headers']}
        content_type = headers.get(b'content-type', b'').split(b';', 1)[0].strip().lower()
        if content_type != _JSON_CONTENT_TYPE.encode():
            await self.app(scope, receive, send)
            return

        content_length = headers.get(b'content-length')
        if content_length:
            try:
                if int(content_length) > self.limit:
                    await self._too_large(scope, receive, send)
                    return
            except ValueError:
                await self._too_large(scope, receive, send)
                return

        chunks = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunks.extend(message.get('body', b''))
            if len(chunks) > self.limit:
                await self._too_large(scope, receive, send)
                return
            if not message.get('more_body', False):
                break

        delivered = False

        async def replay_body() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(chunks), 'more_body': False}
            return await receive()

        await self.app(scope, replay_body, send)

    async def _too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive)
        response = problem_response(
            request,
            status_code=413,
            detail='JSON request body exceeds the 1 MB limit.',
            code=ProblemCode.BAD_REQUEST,
            title='Payload Too Large',
        )
        await response(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def add_headers(message: Message) -> None:
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers.extend(
                    [
                        (b'x-content-type-options', b'nosniff'),
                        (b'referrer-policy', b'strict-origin-when-cross-origin'),
                        (b'x-frame-options', b'DENY'),
                    ]
                )
                if settings.ENVIRONMENT != 'local':
                    headers.append(
                        (b'strict-transport-security', b'max-age=31536000; includeSubDomains')
                    )
                message['headers'] = headers
            await send(message)

        await self.app(scope, receive, add_headers)


class CookieOriginMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        expected = urlsplit(settings.FRONTEND_URL)
        self.expected_origin = f'{expected.scheme}://{expected.netloc}'

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.headers.get('cookie'):
            source = request.headers.get('origin') or request.headers.get('referer')
            parsed = urlsplit(source) if source else None
            supplied_origin = f'{parsed.scheme}://{parsed.netloc}' if parsed else ''
            if supplied_origin != self.expected_origin:
                response = problem_response(
                    request,
                    status_code=403,
                    detail='The request origin is not allowed.',
                    code=ProblemCode.BAD_REQUEST,
                    title='Forbidden',
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
