from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeVar, cast

import structlog
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = structlog.get_logger(__name__)
T = TypeVar('T')
CACHE_SCHEMA_VERSION = 1
_client: Redis | None = None


def get_cache_client() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.REDIS_CACHE_URL,
            decode_responses=True,
            socket_connect_timeout=0.75,
            socket_timeout=0.75,
        )
    return _client


def configure_cache_client(client: Redis | None) -> None:
    """Inject a client for tests or replace the lazy default client."""
    global _client
    _client = client


def cache_key(key: str, *, namespace: str, version: int = CACHE_SCHEMA_VERSION) -> str:
    if not namespace or not namespace.strip():
        raise ValueError('namespace must not be empty')
    if version < 1:
        raise ValueError('version must be a positive integer')
    return f'autotrader:cache:v{version}:{namespace}:{key}'


def get_or_set(
    key: str,
    ttl: int,
    fn: Callable[[], T],
    *,
    namespace: str | None = None,
    version: int = CACHE_SCHEMA_VERSION,
) -> T:
    """Return a cached JSON value, computing and caching it on a miss."""
    if ttl < 1:
        raise ValueError('ttl must be a positive number of seconds')
    module_namespace = namespace or fn.__module__
    redis_key = cache_key(key, namespace=module_namespace, version=version)
    client = get_cache_client()

    try:
        cached = cast(str | bytes | bytearray | None, client.get(redis_key))
    except RedisError:
        logger.warning('cache_read_failed', namespace=module_namespace)
        return fn()

    if cached is not None:
        try:
            return json.loads(cached)
        except (TypeError, json.JSONDecodeError):
            logger.warning('cache_value_invalid', namespace=module_namespace)
            try:
                client.delete(redis_key)
            except RedisError:
                logger.debug('cache_invalid_value_delete_failed', namespace=module_namespace)

    value = fn()
    try:
        encoded = json.dumps(value, separators=(',', ':'), ensure_ascii=False)
    except (TypeError, ValueError):
        return value

    try:
        stored = client.set(redis_key, encoded, ex=ttl, nx=True)
        if not stored:
            winner = cast(str | bytes | bytearray | None, client.get(redis_key))
            if winner is not None:
                return json.loads(winner)
    except (RedisError, TypeError, json.JSONDecodeError):
        logger.warning('cache_write_failed', namespace=module_namespace)
    return value
