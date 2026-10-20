"""Listing rows for tests (Feature 02 slice 2.6).

Derived columns are always computed by `derive.py` and `listed_at` is always stamped by
`visibility.on_change`, never set by hand (playbook §2): a factory that hand-set them
would let tests pass on rows the real write path can never produce.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.uuid7 import uuid7
from app.models import Dealer, Listing, Make, VehicleModel
from app.modules.listings.derive import build_title, derive_ulez, normalise_vrm
from app.modules.listings.enums import ListingStatus, ModerationStatus
from app.modules.listings.visibility import on_change
from app.modules.taxonomy.naming import slugify


@dataclass(frozen=True)
class Vehicle:
    make_id: UUID
    model_id: UUID
    make_name: str
    model_name: str


def create_vehicle(session: Session, make: str = 'Ford', model: str = 'Fiesta') -> Vehicle:
    """A fresh make and model (unique slugs), so tests never depend on the loaded taxonomy."""
    suffix = uuid7().hex[-12:]
    make_row = Make(name=make, slug=f'{slugify(make)}-{suffix}')
    session.add(make_row)
    session.flush()
    model_row = VehicleModel(
        make_id=make_row.id, name=model, slug=slugify(model), body_types=['hatchback']
    )
    session.add(model_row)
    session.flush()
    return Vehicle(make_row.id, model_row.id, make, model)


def create_listing(
    session: Session,
    dealer: Dealer,
    vehicle: Vehicle,
    *,
    status: ListingStatus = ListingStatus.ACTIVE,
    moderation_status: ModerationStatus = ModerationStatus.CLEAR,
    **overrides: Any,
) -> Listing:
    """A complete listing in `status`, with the timestamps that state requires.

    `moderation_status` is applied before `on_change`, as Feature 05's publish pipeline
    does, so a listing created `held` gets no `listed_at`.
    """
    fields: dict[str, Any] = {
        'year': 2019,
        'registration_date': date(2019, 3, 1),
        'mileage': 42_000,
        'price_pence': 1_099_500,
        'body_type': 'hatchback',
        'fuel_type': 'petrol',
        'transmission': 'manual',
        'colour': 'blue',
        'doors': 5,
        'seats': 5,
        'variant': '1.0 EcoBoost ST-Line 5dr',
        'vrm': 'za19 kxr',
        'description': 'One careful owner.',
        **overrides,
    }
    now = session.scalar(select(func.now()))
    lifecycle: dict[str, Any] = {}
    if status != ListingStatus.DRAFT:
        lifecycle['published_at'] = now
    if status == ListingStatus.SOLD:
        lifecycle['sold_at'] = now
    if status == ListingStatus.ARCHIVED:
        lifecycle['archived_at'] = now

    listing = Listing(
        dealer_id=dealer.id,
        is_demo=dealer.is_demo,
        status=status,
        moderation_status=moderation_status,
        make_id=vehicle.make_id,
        model_id=vehicle.model_id,
        latitude=dealer.latitude,
        longitude=dealer.longitude,
        **fields,
        **lifecycle,
    )
    listing.vrm = normalise_vrm(listing.vrm)
    listing.title = build_title(
        listing.year, vehicle.make_name, vehicle.model_name, listing.variant
    )
    listing.ulez_compliant = derive_ulez(listing.fuel_type, listing.registration_date)
    session.add(listing)
    on_change(session, listing)
    return listing
