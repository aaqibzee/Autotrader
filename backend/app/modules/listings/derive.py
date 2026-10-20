"""Derived listing values: one pure function each (Feature 02 §6).

Feature 05's write path and the demo seed (slice 2.7) both derive through these, so
seeded rows can never differ from real ones, and `verify_listing_invariants` (2.6)
recomputes every row with them. No database, no I/O.
"""

from __future__ import annotations

import re
from datetime import date

from app.modules.geo.services import region_for_postcode
from app.modules.listings.models import TITLE_MAX_LENGTH
from app.modules.taxonomy.enums import FuelType
from app.modules.taxonomy.naming import slugify

__all__ = [
    'SLUG_MAX_LENGTH',
    'build_title',
    'derive_ulez',
    'listing_slug',
    'normalise_vrm',
    'region_for_postcode',
]

SLUG_MAX_LENGTH = 80
# Used only when a title has nothing usable in a URL (a draft, or a title of symbols).
_FALLBACK_SLUG = 'car'

# ULEZ approximations (§6, A8): Euro 4 petrol is roughly 2006 on, Euro 6 diesel roughly
# September 2015 on. The UI says "Likely" and links to TfL's checker.
PETROL_ULEZ_FROM = date(2006, 1, 1)
DIESEL_ULEZ_FROM = date(2015, 9, 1)
_PETROL_RULE = frozenset({FuelType.PETROL, FuelType.HYBRID, FuelType.PLUG_IN_HYBRID})

_WHITESPACE = re.compile(r'\s+')
_NON_ALPHANUMERIC = re.compile(r'[^A-Z0-9]')
VRM_MIN_LENGTH, VRM_MAX_LENGTH = 2, 7


def _clean(part: str | int | None) -> str:
    return _WHITESPACE.sub(' ', str(part)).strip() if part is not None else ''


def build_title(year: int | None, make: str | None, model: str | None, variant: str | None) -> str:
    """`2019 Ford Fiesta 1.0 EcoBoost ST-Line 5dr`, at most 160 characters.

    Missing parts are skipped (a draft may have none, giving ''). An over-long title is
    cut at the last whole word that fits; a single word longer than the limit is cut.
    """
    title = ' '.join(part for part in map(_clean, (year, make, model, variant)) if part)
    if len(title) <= TITLE_MAX_LENGTH:
        return title
    cut = title[: TITLE_MAX_LENGTH + 1].rsplit(' ', 1)[0]
    return cut if len(cut) <= TITLE_MAX_LENGTH else title[:TITLE_MAX_LENGTH]


def listing_slug(title: str) -> str:
    """URL slug for the detail page (Feature 08 §1), at most 80 characters.

    Cosmetic only: the id in the URL is authoritative, so a slug may change with the
    title and an outdated one redirects. Cut at a word boundary when too long.
    """
    try:
        slug = slugify(title)
    except ValueError:
        return _FALLBACK_SLUG
    if len(slug) <= SLUG_MAX_LENGTH:
        return slug
    cut = slug[: SLUG_MAX_LENGTH + 1].rsplit('-', 1)[0]
    return cut if len(cut) <= SLUG_MAX_LENGTH else slug[:SLUG_MAX_LENGTH].rstrip('-')


def derive_ulez(fuel_type: str | None, registration_date: date | None) -> bool | None:
    """Likely ULEZ compliance; `None` while the inputs a draft lacks are unknown."""
    if fuel_type == FuelType.ELECTRIC:
        return True
    if fuel_type == FuelType.OTHER:
        return False
    if fuel_type is None or registration_date is None:
        return None
    if fuel_type in _PETROL_RULE:
        return registration_date >= PETROL_ULEZ_FROM
    if fuel_type == FuelType.DIESEL:
        return registration_date >= DIESEL_ULEZ_FROM
    raise ValueError(f'unknown fuel type {fuel_type!r}')


def normalise_vrm(raw: str | None) -> str | None:
    """`'za19 kxr'` -> `'ZA19KXR'`: upper case, letters and digits only, 2-7 long.

    Returns `None` for anything else. Every VRM comparison (duplicates, lookups, Feature 14
    checks) uses this form, and `ck_listings_vrm_normalised` refuses any other.
    """
    if raw is None:
        return None
    vrm = _NON_ALPHANUMERIC.sub('', raw.upper())
    return vrm if VRM_MIN_LENGTH <= len(vrm) <= VRM_MAX_LENGTH else None
