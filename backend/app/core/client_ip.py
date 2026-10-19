from __future__ import annotations

import ipaddress
import json
from collections.abc import Iterable
from functools import lru_cache
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from typing import cast

import structlog
from fastapi import Request
from redis.exceptions import RedisError

from app.core.cache import cache_key, get_cache_client
from app.core.config import settings

IPNetwork = IPv4Network | IPv6Network
IPAddress = IPv4Address | IPv6Address
logger = structlog.get_logger(__name__)

_CLOUDFLARE_FALLBACK_CIDRS = (
    '173.245.48.0/20',
    '103.21.244.0/22',
    '103.22.200.0/22',
    '103.31.4.0/22',
    '141.101.64.0/18',
    '108.162.192.0/18',
    '190.93.240.0/20',
    '188.114.96.0/20',
    '197.234.240.0/22',
    '198.41.128.0/17',
    '162.158.0.0/15',
    '104.16.0.0/13',
    '104.24.0.0/14',
    '172.64.0.0/13',
    '131.0.72.0/22',
    '2400:cb00::/32',
    '2606:4700::/32',
    '2803:f800::/32',
    '2405:b500::/32',
    '2405:8100::/32',
    '2a06:98c0::/29',
    '2c0f:f248::/32',
)
_CLOUDFLARE_FALLBACK_NETWORKS = tuple(
    ipaddress.ip_network(value) for value in _CLOUDFLARE_FALLBACK_CIDRS
)
CLOUDFLARE_CIDRS_CACHE_KEY = cache_key('cidrs', namespace='app.core.client_ip')
CLOUDFLARE_CIDRS_CACHE_TTL_SECONDS = 8 * 24 * 60 * 60


@lru_cache(maxsize=1)
def _trusted_proxy_networks() -> tuple[IPNetwork, ...]:
    networks = []
    for value in settings.TRUSTED_PROXY_CIDRS.split(','):
        try:
            networks.append(ipaddress.ip_network(value.strip(), strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _cloudflare_networks() -> tuple[IPNetwork, ...]:
    try:
        cached = cast(
            str | bytes | bytearray | None,
            get_cache_client().get(CLOUDFLARE_CIDRS_CACHE_KEY),
        )
    except (RedisError, OSError):
        logger.warning('cloudflare_cidr_cache_read_failed')
        return _CLOUDFLARE_FALLBACK_NETWORKS

    if cached is None:
        return _CLOUDFLARE_FALLBACK_NETWORKS

    try:
        values = json.loads(cached)
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValueError('cached Cloudflare CIDRs must be a list of strings')
        return tuple(
            ipaddress.ip_network(value, strict=True) for value in parse_cloudflare_cidrs(values)
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning('cloudflare_cidr_cache_invalid')
        return _CLOUDFLARE_FALLBACK_NETWORKS


def parse_cloudflare_cidrs(values: Iterable[str]) -> tuple[str, ...]:
    networks: list[IPNetwork] = []
    for value in values:
        candidate = value.strip()
        if not candidate:
            continue
        network = ipaddress.ip_network(candidate, strict=True)
        minimum_prefix = 13 if network.version == 4 else 29
        if network.prefixlen < minimum_prefix or not network.is_global:
            raise ValueError(f'unsafe Cloudflare network: {candidate}')
        if any(existing.overlaps(network) for existing in networks):
            raise ValueError(f'overlapping Cloudflare network: {candidate}')
        networks.append(network)

    versions = {network.version for network in networks}
    if versions != {4, 6}:
        raise ValueError('Cloudflare CIDR list must contain IPv4 and IPv6 networks')
    if len(networks) > 128:
        raise ValueError('Cloudflare CIDR list is unexpectedly large')
    return tuple(network.with_prefixlen for network in networks)


def _parse_ip(value: str | None) -> IPAddress | None:
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _belongs_to(address: IPAddress, networks: tuple[IPNetwork, ...]) -> bool:
    return any(address.version == network.version and address in network for network in networks)


def resolve_client_ip(
    peer_value: str | None,
    verified_proxy_value: str | None,
    forwarded_client_value: str | None,
) -> str:
    peer = _parse_ip(peer_value)
    if peer is None:
        return 'unknown'
    if not _belongs_to(peer, _trusted_proxy_networks()):
        return peer.compressed

    proxy_peer = _parse_ip(verified_proxy_value)
    if proxy_peer is None or not _belongs_to(proxy_peer, _cloudflare_networks()):
        return peer.compressed

    client = _parse_ip(forwarded_client_value)
    return client.compressed if client is not None else peer.compressed


def get_client_ip(request: Request) -> str:
    return resolve_client_ip(
        request.client.host if request.client else None,
        request.headers.get('x-verified-cloudflare-peer'),
        request.headers.get('cf-connecting-ip'),
    )


def is_loopback_peer(request: Request) -> bool:
    peer = _parse_ip(request.client.host if request.client else None)
    return bool(peer and peer.is_loopback)
