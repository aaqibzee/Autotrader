"""The geo module's public API: the only entry point other modules import (Feature 02 A7)."""

from __future__ import annotations

from app.modules.geo.districts import (
    District,
    all_districts,
    district_for,
    outward_code,
    region_for_postcode,
)
from app.modules.geo.enums import REGION_NAMES, Region

__all__ = [
    'REGION_NAMES',
    'District',
    'Region',
    'all_districts',
    'district_for',
    'outward_code',
    'region_for_postcode',
]
