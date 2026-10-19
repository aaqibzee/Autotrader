from __future__ import annotations

import argparse
import ipaddress
import os
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from urllib.request import Request, urlopen

_FEEDS = (
    ('https://www.cloudflare.com/ips-v4', 4),
    ('https://www.cloudflare.com/ips-v6', 6),
)
_DEFAULT_OUTPUT = Path('/etc/nginx/autotrader/cloudflare-allowlist.conf')


def _fetch_ranges() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for url, expected_version in _FEEDS:
        request = Request(url, headers={'User-Agent': 'Autotrader-Cloudflare-Allowlist/1.0'})
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise ValueError(f'Cloudflare range feed returned HTTP {response.status}')
            content = response.read().decode('ascii')
        feed_networks = _parse_ranges(content.splitlines(), expected_version)
        networks.extend(feed_networks)

    if not networks:
        raise ValueError('Cloudflare range feeds were empty')
    _validate_ranges(networks)
    return tuple(networks)


def _parse_ranges(
    values: Iterable[str], expected_version: int
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for value in values:
        candidate = value.strip()
        if not candidate:
            continue
        network = ipaddress.ip_network(candidate, strict=True)
        if network.version != expected_version:
            raise ValueError(f'Unexpected IP family in Cloudflare feed: {candidate}')
        minimum_prefix = 13 if network.version == 4 else 29
        if network.prefixlen < minimum_prefix or not network.is_global:
            raise ValueError(f'Unsafe Cloudflare network: {candidate}')
        networks.append(network)
    if not networks:
        raise ValueError(f'Cloudflare IPv{expected_version} range feed was empty')
    return networks


def _validate_ranges(
    networks: Iterable[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> None:
    items = tuple(networks)
    if len(items) > 128:
        raise ValueError('Cloudflare range list is unexpectedly large')
    for index, network in enumerate(items):
        if any(network.overlaps(other) for other in items[index + 1 :]):
            raise ValueError(f'Overlapping Cloudflare network: {network}')


def _render_allowlist(
    networks: Iterable[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> str:
    return ''.join(f'allow {network.with_prefixlen};\n' for network in networks) + 'deny all;\n'


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='ascii', dir=path.parent, delete=False
        ) as temporary_file:
            temporary_path = temporary_file.name
            temporary_file.write(content)
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def refresh(output_path: Path) -> bool:
    allowlist = _render_allowlist(_fetch_ranges())
    previous = output_path.read_text(encoding='ascii')
    if previous == allowlist:
        print('Cloudflare allow-list is unchanged.')
        return False

    _atomic_write(output_path, allowlist)
    validation = subprocess.run(['nginx', '-t'], check=False, capture_output=True, text=True)
    if validation.returncode:
        _atomic_write(output_path, previous)
        raise RuntimeError(
            f'Nginx validation failed; restored prior allow-list. {validation.stderr}'
        )

    reload_result = subprocess.run(
        ['systemctl', 'reload', 'nginx'], check=False, capture_output=True, text=True
    )
    if reload_result.returncode:
        raise RuntimeError(f'Nginx reload failed. {reload_result.stderr}')
    print(f'Installed {len(allowlist.splitlines()) - 1} Cloudflare networks and reloaded Nginx.')
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description='Refresh the Nginx Cloudflare IP allow-list.')
    parser.add_argument('--output', type=Path, default=_DEFAULT_OUTPUT)
    args = parser.parse_args()
    refresh(args.output)


if __name__ == '__main__':
    main()
