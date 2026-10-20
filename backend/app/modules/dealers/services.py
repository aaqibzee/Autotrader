"""The dealers module's public API (Feature 02 A7). Feature 04 adds the account services."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.db.uuid7 import uuid7
from app.modules.dealers.models import Dealer

INSERT_BATCH_SIZE = 1_000


@dataclass(frozen=True)
class DealerLocation:
    id: UUID
    slug: str
    name: str
    postcode: str
    latitude: float | None
    longitude: float | None
    region_code: str | None


def insert_dealers(session: Session, rows: Sequence[dict[str, Any]]) -> list[UUID]:
    """Bulk-insert dealer rows (Core, batches of 1,000); returns their new ids in order."""
    ids = [uuid7() for _ in rows]
    for start in range(0, len(rows), INSERT_BATCH_SIZE):
        batch = [
            {**row, 'id': identifier}
            for row, identifier in zip(
                rows[start : start + INSERT_BATCH_SIZE],
                ids[start : start + INSERT_BATCH_SIZE],
                strict=True,
            )
        ]
        session.execute(insert(Dealer), batch)
    return ids


def demo_dealers(session: Session, region: str | None = None) -> list[DealerLocation]:
    """Every demo dealer (in `region`, a GSS code, if given), sorted by slug."""
    query = (
        select(
            Dealer.id,
            Dealer.slug,
            Dealer.name,
            Dealer.postcode,
            Dealer.latitude,
            Dealer.longitude,
            Dealer.region_code,
        )
        .where(Dealer.is_demo)
        .order_by(Dealer.slug)
    )
    if region is not None:
        query = query.where(Dealer.region_code == region)
    return [DealerLocation(*row) for row in session.execute(query)]


def dealer_slugs(session: Session) -> frozenset[str]:
    """Every dealer slug in use, real or demo (slugs are unique across both)."""
    return frozenset(session.scalars(select(Dealer.slug)))


def delete_demo_dealers(session: Session, region: str | None = None) -> int:
    """Hard-delete demo dealers (in `region` if given); returns how many.

    Only `is_demo` rows: the composite `(dealer_id, is_demo)` FK means a demo dealer can
    only own demo listings, and `ON DELETE CASCADE` removes them (design §9).
    """
    statement = delete(Dealer).where(Dealer.is_demo)
    if region is not None:
        statement = statement.where(Dealer.region_code == region)
    return len(session.execute(statement.returning(Dealer.id)).all())
