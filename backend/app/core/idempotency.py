"""Idempotency-Key support for side-effecting POSTs (Feature 01 §5).

A client that may retry (lead submit, publish, invite) sends `Idempotency-Key: <uuid>`.
The first response is stored for 24 h and replayed verbatim for any retry with the same
key, so the side effect happens once. Rules, after Stripe's well-tested semantics:

- Keys are scoped to the caller (session cookie, else client IP), so one client can
  never read another's stored response by guessing a key.
- The same key with a different method/path/body is a client bug: 422, never a replay.
- A retry that arrives while the first request is still running gets 409 rather than
  executing twice.
- 5xx responses are not stored: the operation may not have happened, so retrying must
  be allowed to run again.
- If Redis is unavailable the request runs without idempotency (fail open, logged):
  blocking every write site-wide is worse than a rare duplicate during an outage.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import cast

import structlog
from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.cache import get_cache_client
from app.core.errors import ProblemCode, problem_response

logger = structlog.get_logger(__name__)

IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
# Longer than any request can legitimately run, so a crashed request frees its key.
IN_PROGRESS_TTL_SECONDS = 60
MAX_STORED_BODY_BYTES = 256 * 1024
_KEY_PATTERN = re.compile(r'^[\x21-\x7e]{8,255}$')
_REPLAYED_HEADERS = {b'content-type', b'location', b'x-trace-id'}
_IN_PROGRESS = 'in_progress'


def _redis_key(scope_hash: str, key: str) -> str:
    digest = hashlib.sha256(f'{scope_hash}:{key}'.encode()).hexdigest()
    return f'autotrader:idempotency:v1:{digest}'


def _caller_scope(request: Request) -> str:
    # Feature 04 sessions live in the cookie; anonymous callers fall back to client IP.
    cookie = request.headers.get('cookie')
    identity = f'cookie:{cookie}' if cookie else f'ip:{getattr(request.state, "client_ip", "")}'
    return hashlib.sha256(identity.encode()).hexdigest()


def _fingerprint(method: str, path: str, query: bytes, body: bytes) -> str:
    hasher = hashlib.sha256()
    for part in (method.encode(), path.encode(), query, body):
        hasher.update(len(part).to_bytes(8, 'big'))
        hasher.update(part)
    return hasher.hexdigest()


class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or scope['method'] != 'POST':
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        key = request.headers.get('idempotency-key')
        if key is None:
            await self.app(scope, receive, send)
            return
        if not _KEY_PATTERN.fullmatch(key):
            response = problem_response(
                request,
                status_code=400,
                detail='Idempotency-Key must be 8-255 printable ASCII characters.',
                code=ProblemCode.INVALID_INPUT,
            )
            await response(scope, receive, send)
            return

        # Buffer the body (already capped at 1 MB by JsonBodyLimitMiddleware) to fingerprint it.
        body = await request.body()
        fingerprint = _fingerprint(scope['method'], scope['path'], scope['query_string'], body)
        redis_key = _redis_key(_caller_scope(request), key)
        client = get_cache_client()

        try:
            claimed = client.set(
                redis_key,
                json.dumps({'state': _IN_PROGRESS, 'fingerprint': fingerprint}),
                nx=True,
                ex=IN_PROGRESS_TTL_SECONDS,
            )
            existing = None if claimed else cast(str | None, client.get(redis_key))
        except RedisError:
            logger.warning('idempotency_store_unavailable', path=scope['path'])
            await self.app(scope, _replay(body, receive), send)
            return

        if not claimed:
            if existing is None:
                # Expired between SET NX and GET; treat as a conflict and let the client retry.
                await self._conflict(request, scope, receive, send)
                return
            stored = json.loads(existing)
            if stored.get('fingerprint') != fingerprint:
                response = problem_response(
                    request,
                    status_code=422,
                    detail='This Idempotency-Key was already used for a different request.',
                    code=ProblemCode.IDEMPOTENCY_KEY_REUSED,
                )
                await response(scope, receive, send)
                return
            if stored.get('state') == _IN_PROGRESS:
                await self._conflict(request, scope, receive, send)
                return
            await _send_stored(stored, send)
            return

        captured: dict[str, object] = {'chunks': [], 'size': 0, 'too_large': False}

        async def capture(message: Message) -> None:
            if message['type'] == 'http.response.start':
                captured['status'] = message['status']
                captured['headers'] = [
                    [name.decode('latin-1'), value.decode('latin-1')]
                    for name, value in message.get('headers', [])
                    if name.lower() in _REPLAYED_HEADERS
                ]
            elif message['type'] == 'http.response.body':
                chunk = message.get('body', b'')
                size = cast(int, captured['size']) + len(chunk)
                captured['size'] = size
                if size > MAX_STORED_BODY_BYTES:
                    captured['too_large'] = True
                else:
                    cast(list[bytes], captured['chunks']).append(chunk)
            await send(message)

        try:
            await self.app(scope, _replay(body, receive), capture)
        except BaseException:
            _release(client, redis_key)
            raise

        status = cast(int | None, captured.get('status'))
        if status is None or status >= 500 or captured['too_large']:
            _release(client, redis_key)
            return
        record = {
            'state': 'complete',
            'fingerprint': fingerprint,
            'status': status,
            'headers': captured['headers'],
            'body': base64.b64encode(b''.join(cast(list[bytes], captured['chunks']))).decode(),
        }
        try:
            client.set(redis_key, json.dumps(record), ex=IDEMPOTENCY_TTL_SECONDS)
        except RedisError:
            logger.warning('idempotency_store_write_failed', path=scope['path'])

    async def _conflict(self, request: Request, scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(
            request,
            status_code=409,
            detail='A request with this Idempotency-Key is still being processed.',
            code=ProblemCode.IDEMPOTENCY_IN_PROGRESS,
        )
        response.headers['Retry-After'] = '1'
        await response(scope, receive, send)


def _replay(body: bytes, receive: Receive) -> Receive:
    delivered = False

    async def receive_buffered() -> Message:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        return await receive()

    return receive_buffered


def _release(client: object, redis_key: str) -> None:
    try:
        client.delete(redis_key)  # type: ignore[attr-defined]
    except RedisError:
        logger.warning('idempotency_release_failed')


async def _send_stored(stored: dict[str, object], send: Send) -> None:
    headers = [
        (name.encode('latin-1'), value.encode('latin-1'))
        for name, value in cast(list[list[str]], stored['headers'])
    ]
    headers.append((b'idempotent-replayed', b'true'))
    await send({'type': 'http.response.start', 'status': stored['status'], 'headers': headers})
    await send(
        {
            'type': 'http.response.body',
            'body': base64.b64decode(cast(str, stored['body'])),
        }
    )
