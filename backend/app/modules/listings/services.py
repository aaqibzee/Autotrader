"""Listing writes that are not the dealer's, and the derived-column audit (Feature 02 §5-§6).

`system_update` is the only way to write a system-owned column. Feature 05 owns every
dealer-owned field; this module never touches those.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, select, update
from sqlalchemy.orm import Session

from app.modules.listings.derive import build_title, derive_ulez, normalise_vrm
from app.modules.listings.models import Listing, is_visible
from app.modules.taxonomy.services import make_names, model_names

# Columns written by background, admin or system work (design §5). Anything else is
# dealer-owned and goes through Feature 05, which bumps the lock token on purpose.
SYSTEM_COLUMNS = frozenset(
    {'moderation_status', 'listed_at', 'photo_count', 'latitude', 'longitude'}
)
INVARIANT_BATCH_SIZE = 1_000


class SystemColumnError(ValueError):
    """`system_update` was asked to write a column it does not own."""


def system_update(
    session: Session,
    listing_id: UUID,
    *,
    where: Iterable[ColumnElement[bool]] = (),
    **columns: Any,
) -> bool:
    """Write system-owned columns without touching the `updated_at` lock token.

    A Core UPDATE that also sets `updated_at = updated_at`, so the column's `onupdate`
    cannot fire and a dealer's open edit form is not invalidated (Feature 01 §5; Yaqlo was
    hit by exactly this twice). Optional `where` conditions make the write conditional.
    Returns True if a row was updated. Session objects for the row are refreshed.
    """
    if not columns:
        raise SystemColumnError('no columns to update')
    refused = sorted(set(columns) - SYSTEM_COLUMNS)
    if refused:
        raise SystemColumnError(f'not system-owned: {", ".join(refused)}')
    statement = (
        update(Listing)
        .where(Listing.id == listing_id, *where)
        .values(**columns, updated_at=Listing.updated_at)
        .returning(Listing.id)
        .execution_options(synchronize_session='fetch')
    )
    return session.execute(statement).first() is not None


@dataclass(frozen=True)
class InvariantMismatch:
    listing_id: UUID
    column: str
    stored: Any
    expected: Any


_AUDITED = (
    Listing.id,
    Listing.status,
    Listing.moderation_status,
    Listing.archived_at,
    Listing.make_id,
    Listing.model_id,
    Listing.year,
    Listing.variant,
    Listing.title,
    Listing.fuel_type,
    Listing.registration_date,
    Listing.ulez_compliant,
    Listing.vrm,
    Listing.listed_at,
)


def _check_batch(session: Session, rows: list[Any]) -> list[InvariantMismatch]:
    makes = make_names(session, (row.make_id for row in rows if row.make_id))
    models = model_names(session, (row.model_id for row in rows if row.model_id))
    mismatches: list[InvariantMismatch] = []

    def compare(row: Any, column: str, stored: Any, expected: Any) -> None:
        if stored != expected:
            mismatches.append(InvariantMismatch(row.id, column, stored, expected))

    for row in rows:
        title = build_title(row.year, makes.get(row.make_id), models.get(row.model_id), row.variant)
        compare(row, 'title', row.title, title)
        compare(
            row,
            'ulez_compliant',
            row.ulez_compliant,
            derive_ulez(row.fuel_type, row.registration_date),
        )
        if row.vrm is not None:
            compare(row, 'vrm', row.vrm, normalise_vrm(row.vrm))
        # A visible listing must have been stamped by on_change (never reset after that).
        if is_visible(row.status, row.moderation_status, row.archived_at) and row.listed_at is None:
            compare(row, 'listed_at', None, 'a timestamp')
    return mismatches


def verify_listing_invariants(
    session: Session, *, batch_size: int = INVARIANT_BATCH_SIZE
) -> list[InvariantMismatch]:
    """Every listing whose derived columns differ from what derive.py computes now.

    Checks `title`, `ulez_compliant`, the VRM normal form and the `listed_at` rule (a
    visible listing has one). Walks the table in id order, `batch_size` rows at a time, so
    it runs over the 50k perf dataset without loading it whole. Used by the demo seed
    (2.7, fails the run on any mismatch) and by Feature 05's tests.
    """
    mismatches: list[InvariantMismatch] = []
    last_id: UUID | None = None
    while True:
        query = select(*_AUDITED).order_by(Listing.id).limit(batch_size)
        if last_id is not None:
            query = query.where(Listing.id > last_id)
        rows = list(session.execute(query))
        if not rows:
            return mismatches
        mismatches += _check_batch(session, rows)
        last_id = rows[-1].id
