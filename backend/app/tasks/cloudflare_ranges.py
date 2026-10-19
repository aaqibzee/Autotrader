from __future__ import annotations

import json

import httpx
import structlog
from celery import Task
from redis.exceptions import RedisError

from app.core.cache import get_cache_client
from app.core.celery_app import celery_app
from app.core.client_ip import (
    CLOUDFLARE_CIDRS_CACHE_KEY,
    CLOUDFLARE_CIDRS_CACHE_TTL_SECONDS,
    parse_cloudflare_cidrs,
)

logger = structlog.get_logger(__name__)
_CLOUDFLARE_IPV4_URL = 'https://www.cloudflare.com/ips-v4'
_CLOUDFLARE_IPV6_URL = 'https://www.cloudflare.com/ips-v6'


@celery_app.task(bind=True, name='app.tasks.cloudflare_ranges.refresh_cloudflare_ranges')
def refresh_cloudflare_ranges(self: Task) -> dict[str, int | bool]:
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            ipv4_response = client.get(_CLOUDFLARE_IPV4_URL)
            ipv4_response.raise_for_status()
            ipv6_response = client.get(_CLOUDFLARE_IPV6_URL)
            ipv6_response.raise_for_status()

        cidrs = parse_cloudflare_cidrs(
            (*ipv4_response.text.splitlines(), *ipv6_response.text.splitlines())
        )
        encoded = json.dumps(cidrs, separators=(',', ':'))
        stored = get_cache_client().set(
            CLOUDFLARE_CIDRS_CACHE_KEY,
            encoded,
            ex=CLOUDFLARE_CIDRS_CACHE_TTL_SECONDS,
        )
        if not stored:
            raise RedisError('Cloudflare CIDR cache write was not acknowledged')
    except (httpx.HTTPError, ValueError, RedisError, OSError) as exc:
        logger.warning('cloudflare_cidr_refresh_failed', error_type=type(exc).__name__)
        raise self.retry(exc=exc)

    logger.info('cloudflare_cidr_refresh_succeeded', cidr_count=len(cidrs))
    return {'updated': True, 'cidr_count': len(cidrs)}
