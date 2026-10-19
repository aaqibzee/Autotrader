from __future__ import annotations

import time
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import anyio
import urllib3
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from minio import Minio
from redis import Redis
from sqlalchemy import text

from app.core.config import settings
from app.core.errors import PROBLEM_RESPONSES, ProblemCode, problem_response
from app.db.session import sync_engine

router = APIRouter(prefix='/health', tags=['health'], responses=PROBLEM_RESPONSES)

# Each probe has its own client-side timeout; this is the outer bound per dependency.
_CHECK_TIMEOUT_SECONDS = 2.0
# /ready is public (uptime checks, the deploy script). Caching the verdict briefly means
# a burst of probes costs one round of dependency checks, not one per request.
_READY_CACHE_SECONDS = 1.0
_ready_cache: tuple[float, tuple[str, ...]] | None = None
_ready_lock = anyio.Lock()


@router.get('/live')
async def health_live() -> dict[str, str]:
    return {'status': 'live'}


@lru_cache(maxsize=1)
def _expected_migration_heads() -> frozenset[str]:
    # Scripts on disk only change with a deploy (which restarts the process), so parse once.
    config = Config(str(Path(__file__).resolve().parents[4] / 'alembic.ini'))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def _check_database_and_migrations() -> None:
    with sync_engine.connect() as connection:
        connection.execute(text("SET LOCAL statement_timeout = '1500ms'"))
        connection.execute(text('SELECT 1'))
        current_heads = set(MigrationContext.configure(connection).get_current_heads())
    if current_heads != _expected_migration_heads():
        raise RuntimeError('database migrations are not at head')


def _check_redis(url: str) -> None:
    client = Redis.from_url(url, socket_connect_timeout=0.75, socket_timeout=0.75)
    try:
        if not client.ping():
            raise RuntimeError('Redis ping failed')
    finally:
        client.close()


def _check_storage_bucket() -> None:
    # The S3 SDK's default pool has no timeout, so a hung endpoint would hang /ready.
    http_client = urllib3.PoolManager(
        timeout=urllib3.Timeout(connect=0.75, read=1.0),
        retries=urllib3.Retry(total=0),
    )
    try:
        client = Minio(
            settings.S3_ENDPOINT,
            access_key=settings.S3_ACCESS_KEY,
            secret_key=settings.S3_SECRET_KEY,
            secure=settings.S3_SECURE,
            region=settings.S3_REGION,
            http_client=http_client,
        )
        if not client.bucket_exists(settings.S3_BUCKET):
            raise RuntimeError('configured object-storage bucket does not exist')
    finally:
        http_client.clear()


def _checks() -> tuple[tuple[str, Callable[[], None]], ...]:
    # Looked up at call time so tests can monkeypatch the module-level check functions.
    return (
        ('db', _check_database_and_migrations),
        ('redis_broker', lambda: _check_redis(settings.REDIS_BROKER_URL)),
        ('redis_cache', lambda: _check_redis(settings.REDIS_CACHE_URL)),
        ('storage', _check_storage_bucket),
    )


async def _failed_dependencies() -> tuple[str, ...]:
    failed: set[str] = set()

    async def run(name: str, check: Callable[[], None]) -> None:
        try:
            with anyio.fail_after(_CHECK_TIMEOUT_SECONDS):
                # Blocking I/O must never run on the event loop.
                await anyio.to_thread.run_sync(check, abandon_on_cancel=True)
        except Exception:  # noqa: BLE001 - any failed dependency probe means not ready
            failed.add(name)

    async with anyio.create_task_group() as group:
        for name, check in _checks():
            group.start_soon(run, name, check)
    # Stable order, so the response names dependencies predictably.
    return tuple(name for name, _ in _checks() if name in failed)


def reset_ready_cache() -> None:
    global _ready_cache
    _ready_cache = None


@router.get('/ready', response_model=dict[str, str])
async def health_ready(request: Request) -> dict[str, str] | JSONResponse:
    global _ready_cache
    async with _ready_lock:
        now = time.monotonic()
        if _ready_cache is None or _ready_cache[0] <= now:
            _ready_cache = (now + _READY_CACHE_SECONDS, await _failed_dependencies())
        failed = _ready_cache[1]

    if failed:
        return problem_response(
            request,
            status_code=503,
            detail=f'Dependencies unavailable or not ready: {", ".join(failed)}.',
            code=ProblemCode.DEPENDENCY_UNAVAILABLE,
            title='Service Unavailable',
        )
    return {'status': 'ready'}
