"""Dealer rows for tests (Feature 02 slice 2.6). Location comes from the district file."""

from __future__ import annotations

from itertools import count
from typing import Any

from sqlalchemy.orm import Session

from app.models import Dealer
from app.modules.dealers.enums import DealerStatus
from app.modules.geo.services import district_for

_sequence = count(1)


def create_dealer(
    session: Session, *, outward_code: str = 'M1', is_demo: bool = True, **overrides: Any
) -> Dealer:
    """An approved dealer at a district centroid, flushed. Names follow A2 (neutral words)."""
    district = district_for(outward_code)
    assert district is not None, f'{outward_code} is not in the district file'
    number = next(_sequence)
    values: dict[str, Any] = {
        'name': f'Example Motors {number}',
        'slug': f'example-motors-{number}-{id(session):x}',
        'postcode': district.outward_code,
        'latitude': district.latitude,
        'longitude': district.longitude,
        'region_code': district.region_code,
        'status': DealerStatus.APPROVED,
        'is_demo': is_demo,
        **overrides,
    }
    dealer = Dealer(**values)
    session.add(dealer)
    session.flush()
    return dealer
