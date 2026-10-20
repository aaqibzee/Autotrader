"""Seed deterministic demo inventory (Feature 02 §8). Never run on deploy.

    uv run python -m scripts.seed_demo [--listings N] [--random-seed S] [--profile perf]

Requires the taxonomy (`scripts.load_taxonomy`). One transaction: on any failure,
including a row that fails `verify_listing_invariants`, nothing is written. Prints the
SeedReport as one JSON log line. Region scope, `--reset` and production controls arrive
in slice 2.8.
"""

from __future__ import annotations

import argparse
import sys
import time

import structlog

from app.core.telemetry import configure_logging
from app.db.session import SyncSessionLocal
from app.modules.listings.demo_seed import (
    DEFAULT_LISTINGS,
    DEFAULT_RANDOM_SEED,
    PERF_LISTINGS,
    DemoSeedError,
    seed_demo,
)

logger = structlog.get_logger('scripts.seed_demo')


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be at least 1')
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Seed deterministic demo inventory.')
    size = parser.add_mutually_exclusive_group()
    size.add_argument('--listings', type=_positive, default=DEFAULT_LISTINGS)
    size.add_argument(
        '--profile', choices=('perf',), help=f'perf: {PERF_LISTINGS:,} listings (Feature 07)'
    )
    parser.add_argument('--random-seed', type=int, default=DEFAULT_RANDOM_SEED)
    arguments = parser.parse_args(argv)
    listings = PERF_LISTINGS if arguments.profile == 'perf' else arguments.listings

    configure_logging()
    started = time.monotonic()
    try:
        with SyncSessionLocal.begin() as session:
            report = seed_demo(session, listings=listings, random_seed=arguments.random_seed)
    except DemoSeedError as error:
        logger.error('demo_seed_failed', reason=str(error))
        return 1

    logger.info(
        'demo_seeded',
        dealers=report.dealers,
        listings=report.listings,
        statuses=report.statuses,
        listed=report.listed,
        random_seed=report.random_seed,
        seconds=round(time.monotonic() - started, 1),
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
