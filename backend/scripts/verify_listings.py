"""Check every listing's derived columns (Feature 02 §6). Used by CI after the seed smoke.

    uv run python -m scripts.verify_listings

Read-only. Logs the number of listings whose `title`, `ulez_compliant`, `vrm` or
`listed_at` differ from what derive.py computes now, with the first few; exits 1 on any.
"""

from __future__ import annotations

import sys

import structlog
from sqlalchemy import func, select

from app.core.telemetry import configure_logging
from app.db.session import SyncSessionLocal
from app.models import Listing
from app.modules.listings.services import verify_listing_invariants

SHOWN_MISMATCHES = 20

logger = structlog.get_logger('scripts.verify_listings')


def main(argv: list[str] | None = None) -> int:
    del argv  # no options; the signature matches the other scripts
    configure_logging()
    with SyncSessionLocal() as session:
        listings = session.scalar(select(func.count()).select_from(Listing)) or 0
        mismatches = verify_listing_invariants(session)
    if mismatches:
        logger.error(
            'listing_invariants_failed',
            listings=listings,
            mismatches=len(mismatches),
            first=[
                {'listing_id': str(m.listing_id), 'column': m.column}
                for m in mismatches[:SHOWN_MISMATCHES]
            ],
        )
        return 1
    logger.info('listing_invariants_ok', listings=listings)
    return 0


if __name__ == '__main__':
    sys.exit(main())
