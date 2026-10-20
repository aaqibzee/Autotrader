"""The single public-visibility rule, and `listed_at` (Feature 02 §5).

Search (07), the detail page (08), alerts (11) and sitemaps (13) all filter with
`publicly_visible()`; no feature writes its own status filter. Every transition that can
change visibility (Feature 05 publish/unpublish/reserve, Feature 14 hold release) calls
`on_change()` afterwards.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, func
from sqlalchemy.orm import Session

from app.modules.listings.models import Listing, is_visible, visible_predicate
from app.modules.listings.services import system_update


def publicly_visible() -> ColumnElement[bool]:
    """`status IN ('active','reserved') AND moderation_status = 'clear' AND archived_at IS NULL`.

    Built by the same function as the partial indexes' predicate, so Postgres can match
    a query using it to those indexes.
    """
    return visible_predicate(Listing.status, Listing.moderation_status, Listing.archived_at)


def is_publicly_visible(listing: Listing) -> bool:
    """The same rule for a loaded row (tested against `publicly_visible()` on every state)."""
    return is_visible(listing.status, listing.moderation_status, listing.archived_at)


def on_change(session: Session, listing: Listing) -> bool:
    """Set `listed_at` the first time `listing` is publicly visible. True if it was set now.

    Decided by the database row, not the Python object: pending changes are flushed, then
    one conditional UPDATE sets `listed_at` only if the row is visible and has none. Two
    concurrent calls cannot both set it, and it is never reset, so unpublish -> republish
    cannot move a car back to the top of "newest first". Written through `system_update`,
    so it does not invalidate the dealer's lock token.
    """
    session.flush()
    return system_update(
        session,
        listing.id,
        where=(publicly_visible(), Listing.listed_at.is_(None)),
        listed_at=func.now(),
    )
