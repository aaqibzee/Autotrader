"""The single public-visibility rule, and `listed_at` (Feature 02 §5).

Search (07), the detail page (08), alerts (11) and sitemaps (13) all filter with
`publicly_visible()`; no feature writes its own status filter. Every transition that can
change visibility (Feature 05 publish/unpublish/reserve, Feature 14 hold release) calls
`on_change()` afterwards.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, SQLColumnExpression, func, update
from sqlalchemy.orm import Session

from app.modules.listings.models import Listing, is_visible, visible_predicate

STAMP_BATCH_SIZE = 1_000


def publicly_visible() -> ColumnElement[bool]:
    """`status IN ('active','reserved') AND moderation_status = 'clear' AND archived_at IS NULL`.

    Built by the same function as the partial indexes' predicate, so Postgres can match
    a query using it to those indexes.
    """
    return visible_predicate(Listing.status, Listing.moderation_status, Listing.archived_at)


def is_publicly_visible(listing: Listing) -> bool:
    """The same rule for a loaded row (tested against `publicly_visible()` on every state)."""
    return is_visible(listing.status, listing.moderation_status, listing.archived_at)


def stamp_listed_at(
    session: Session, listing_ids: Sequence[UUID], *, at: SQLColumnExpression[Any] | None = None
) -> int:
    """Set `listed_at` on every listing in `listing_ids` that is visible and has none.

    The rule behind `on_change`, for many rows at once (the demo seed). `at` defaults to
    `now()`; the seed passes `Listing.published_at`, since a seeded listing that was never
    held has been visible since it was published. Returns how many rows were stamped.
    """
    stamped = 0
    for start in range(0, len(listing_ids), STAMP_BATCH_SIZE):
        batch = listing_ids[start : start + STAMP_BATCH_SIZE]
        result = session.execute(
            update(Listing)
            .where(Listing.id.in_(batch), publicly_visible(), Listing.listed_at.is_(None))
            # updated_at = updated_at: listed_at is system-owned (see services.system_update).
            .values(listed_at=func.now() if at is None else at, updated_at=Listing.updated_at)
            .returning(Listing.id)
            .execution_options(synchronize_session='fetch')
        )
        stamped += len(result.all())
    return stamped


def on_change(session: Session, listing: Listing) -> bool:
    """Set `listed_at` the first time `listing` is publicly visible. True if it was set now.

    Decided by the database row, not the Python object: pending changes are flushed, then
    one conditional UPDATE sets `listed_at` only if the row is visible and has none. Two
    concurrent calls cannot both set it, and it is never reset, so unpublish -> republish
    cannot move a car back to the top of "newest first". It does not touch `updated_at`, so
    it does not invalidate the dealer's lock token.
    """
    session.flush()
    return stamp_listed_at(session, [listing.id]) == 1
