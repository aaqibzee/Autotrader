from __future__ import annotations

import json
from typing import Self
from unittest.mock import MagicMock

import pytest
from redis.exceptions import RedisError

from app.core import client_ip
from app.tasks import cloudflare_ranges


def test_cloudflare_cidr_parser_requires_global_dual_stack_ranges() -> None:
    cidrs = client_ip.parse_cloudflare_cidrs(['173.245.48.0/20', '2606:4700::/32'])
    assert cidrs == ('173.245.48.0/20', '2606:4700::/32')

    with pytest.raises(ValueError, match='IPv4 and IPv6'):
        client_ip.parse_cloudflare_cidrs(['173.245.48.0/20'])
    with pytest.raises(ValueError, match='unsafe'):
        client_ip.parse_cloudflare_cidrs(['0.0.0.0/0', '2606:4700::/32'])


def test_cloudflare_cidr_lookup_uses_validated_cached_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client = MagicMock()
    redis_client.get.return_value = json.dumps(['173.245.48.0/20', '2606:4700::/32'])
    monkeypatch.setattr(client_ip, 'get_cache_client', lambda: redis_client)

    networks = client_ip._cloudflare_networks()

    assert len(networks) == 2
    assert client_ip._belongs_to(client_ip._parse_ip('173.245.48.10'), networks)
    redis_client.get.assert_called_once_with(client_ip.CLOUDFLARE_CIDRS_CACHE_KEY)


def test_cloudflare_cidr_lookup_falls_back_when_redis_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client = MagicMock()
    redis_client.get.side_effect = RedisError('offline')
    monkeypatch.setattr(client_ip, 'get_cache_client', lambda: redis_client)

    assert client_ip._cloudflare_networks() == client_ip._CLOUDFLARE_FALLBACK_NETWORKS


def test_weekly_refresh_fetches_both_ranges_and_stores_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, text: str) -> None:
            self.text = text

        def raise_for_status(self) -> None:
            return None

    class HttpClient:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, url: str) -> Response:
            if url.endswith('ips-v4'):
                return Response('173.245.48.0/20\n')
            return Response('2606:4700::/32\n')

    redis_client = MagicMock()
    redis_client.set.return_value = True
    monkeypatch.setattr(cloudflare_ranges.httpx, 'Client', lambda **_: HttpClient())
    monkeypatch.setattr(cloudflare_ranges, 'get_cache_client', lambda: redis_client)

    result = cloudflare_ranges.refresh_cloudflare_ranges.run()

    assert result == {'updated': True, 'cidr_count': 2}
    redis_client.set.assert_called_once_with(
        client_ip.CLOUDFLARE_CIDRS_CACHE_KEY,
        json.dumps(['173.245.48.0/20', '2606:4700::/32'], separators=(',', ':')),
        ex=client_ip.CLOUDFLARE_CIDRS_CACHE_TTL_SECONDS,
    )
