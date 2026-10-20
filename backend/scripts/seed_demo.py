"""Seed or remove deterministic demo inventory (Feature 02 §8-§9). Never run on deploy.

    uv run python -m scripts.seed_demo [--listings N | --profile perf] [--random-seed S]
                                       [--region R] [--confirm-production]
    uv run python -m scripts.seed_demo --reset [--region R] [--confirm-production]

Requires the taxonomy (`scripts.load_taxonomy`). `--region` takes a short code (NW, LON,
SCO, ...), a GSS code or a region name. One transaction: on any failure, including a row
that fails `verify_listing_invariants`, nothing is written. `--reset` hard-deletes demo
dealers (in `--region` if given) and their listings; real rows are never touched.

In production a run needs `--region` and `--confirm-production`, and `--profile perf` is
refused; the check happens before any database session opens. Every run logs the
operator (OS user), host, flags and counts as JSON lines.
"""

from __future__ import annotations

import argparse
import getpass
import socket
import sys
import time
from typing import Any

import structlog

from app.core.config import settings
from app.core.telemetry import configure_logging
from app.db.session import SyncSessionLocal
from app.modules.geo.services import Region, parse_region
from app.modules.listings.demo_seed import (
    DEFAULT_LISTINGS,
    DEFAULT_RANDOM_SEED,
    PERF_LISTINGS,
    DemoSeedError,
    production_refusal,
    reset_demo,
    seed_demo,
)

logger = structlog.get_logger('scripts.seed_demo')


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be at least 1')
    return number


def _region(value: str) -> Region:
    try:
        return parse_region(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _operator() -> str:
    try:
        return getpass.getuser()
    except (KeyError, OSError):  # no login name (some containers)
        return 'unknown'


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Seed or remove deterministic demo inventory.')
    size = parser.add_mutually_exclusive_group()
    size.add_argument('--listings', type=_positive, help=f'default {DEFAULT_LISTINGS:,}')
    size.add_argument(
        '--profile', choices=('perf',), help=f'perf: {PERF_LISTINGS:,} listings (Feature 07)'
    )
    parser.add_argument('--random-seed', type=int, default=DEFAULT_RANDOM_SEED)
    parser.add_argument('--region', type=_region, help='only this ONS region (NW, LON, ...)')
    parser.add_argument(
        '--reset', action='store_true', help='remove demo dealers and their listings'
    )
    parser.add_argument(
        '--confirm-production', action='store_true', help='required when ENVIRONMENT=production'
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.reset and (arguments.listings or arguments.profile):
        parser.error('--reset removes demo data; it takes no --listings or --profile')
    region: Region | None = arguments.region

    configure_logging()
    context: dict[str, Any] = {
        'operator': _operator(),
        'host': socket.gethostname(),
        'environment': settings.ENVIRONMENT,
        'flags': {
            'listings': arguments.listings,
            'profile': arguments.profile,
            'random_seed': arguments.random_seed,
            'region': region,
            'reset': arguments.reset,
            'confirm_production': arguments.confirm_production,
        },
    }
    refusal = production_refusal(
        environment=settings.ENVIRONMENT,
        region=region,
        confirmed=arguments.confirm_production,
        perf=arguments.profile == 'perf',
    )
    if refusal:
        logger.error('demo_seed_refused', reason=refusal, **context)
        return 2

    started = time.monotonic()
    counts: dict[str, Any]
    try:
        with SyncSessionLocal.begin() as session:
            if arguments.reset:
                reset = reset_demo(session, region)
                event, counts = 'demo_reset', {'dealers': reset.dealers, 'listings': reset.listings}
            else:
                listings = PERF_LISTINGS if arguments.profile else arguments.listings
                report = seed_demo(
                    session,
                    listings=listings or DEFAULT_LISTINGS,
                    random_seed=arguments.random_seed,
                    region=region,
                )
                event, counts = (
                    'demo_seeded',
                    {
                        'dealers': report.dealers,
                        'listings': report.listings,
                        'statuses': report.statuses,
                        'listed': report.listed,
                    },
                )
    except DemoSeedError as error:
        logger.error('demo_seed_failed', reason=str(error), **context)
        return 1

    logger.info(event, **counts, seconds=round(time.monotonic() - started, 1), **context)
    return 0


if __name__ == '__main__':
    sys.exit(main())
