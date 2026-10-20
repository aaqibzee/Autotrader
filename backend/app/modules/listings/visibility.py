"""The single public-visibility rule (Feature 02 §5).

Search (07), the detail page (08), alerts (11) and sitemaps (13) all filter with
`publicly_visible()`; no feature writes its own status filter. Slice 2.6 adds
`on_change()` (the `listed_at` rule) and the table test over every state combination.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement

from app.modules.listings.models import Listing, visible_predicate


def publicly_visible() -> ColumnElement[bool]:
    """`status IN ('active','reserved') AND moderation_status = 'clear' AND archived_at IS NULL`.

    Built by the same function as the partial indexes' predicate, so Postgres can match
    a query using it to those indexes.
    """
    return visible_predicate(Listing.status, Listing.moderation_status, Listing.archived_at)
