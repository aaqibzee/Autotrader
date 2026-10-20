"""Offline postcode-district lookup (Feature 02 §8, slice 2.3).

Backed by `backend/data/geo/postcode_districts.csv`, which
`scripts/build_postcode_districts.py` derives from the ONS Postcode Directory. The file
is a few thousand rows, read once per process and kept in a dict. It covers Great Britain;
Northern Ireland gets a region but no centroid (`region_for_postcode`).

Postcodes are personal data (playbook §5): nothing here logs, and no error message
carries the postcode it was given. Unparseable or unknown input returns `None`.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.modules.geo.enums import REGION_NAMES, Region

DEFAULT_DISTRICTS_FILE = (
    Path(__file__).resolve().parents[3] / 'data' / 'geo' / 'postcode_districts.csv'
)
COLUMNS = ('outward_code', 'latitude', 'longitude', 'region_code', 'area_name')

# Every ONS region/nation code, with its name (Northern Ireland has no rows in the file and
# is reached by rule, see `region_for_postcode`).
REGIONS = REGION_NAMES

NORTHERN_IRELAND = Region.NORTHERN_IRELAND

OUTWARD_PATTERN = re.compile(r'[A-Z]{1,2}[0-9][A-Z0-9]?')
_NORTHERN_IRELAND_AREA = re.compile(r'BT[0-9]{1,2}')
_INWARD_PATTERN = re.compile(r'[0-9][A-Z]{2}')
_WHITESPACE = re.compile(r'\s+')


@dataclass(frozen=True)
class District:
    outward_code: str
    latitude: float
    longitude: float
    region_code: str
    area_name: str


def outward_code(postcode: str | None) -> str | None:
    """The outward code of a full postcode or an outward code, any case and spacing.

    `'sw1a 1aa'`, `'SW1A1AA'` and `'Sw1a'` all give `'SW1A'`; anything else gives `None`.
    """
    if not postcode:
        return None
    compact = _WHITESPACE.sub('', postcode).upper()
    if OUTWARD_PATTERN.fullmatch(compact):
        return compact
    # An outward code is at most four characters and an inward code exactly three, so a
    # five-to-seven character string can only be a full postcode.
    outward, inward = compact[:-3], compact[-3:]
    if OUTWARD_PATTERN.fullmatch(outward) and _INWARD_PATTERN.fullmatch(inward):
        return outward
    return None


def read_districts(path: Path = DEFAULT_DISTRICTS_FILE) -> dict[str, District]:
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f'{path.name}: header must be {",".join(COLUMNS)}')
        return {
            row['outward_code']: District(
                outward_code=row['outward_code'],
                latitude=float(row['latitude']),
                longitude=float(row['longitude']),
                region_code=row['region_code'],
                area_name=row['area_name'],
            )
            for row in reader
        }


@lru_cache(maxsize=1)
def _districts() -> dict[str, District]:
    return read_districts()


def all_districts() -> tuple[District, ...]:
    """Every district, sorted by outward code (the demo seed spreads dealers over these)."""
    return tuple(_districts().values())


def district_for(postcode_or_outward: str | None) -> District | None:
    code = outward_code(postcode_or_outward)
    return _districts().get(code) if code else None


def region_for_postcode(postcode: str | None) -> str | None:
    """ONS region (or nation) code for a postcode or outward code; `None` if unknown.

    Northern Ireland has no rows in the file (not under the Open Government Licence; see
    `scripts/build_postcode_districts.py`), but the `BT` postcode area is exactly Northern
    Ireland, so any well-formed `BT` code maps to it by rule.
    """
    code = outward_code(postcode)
    if code is None:
        return None
    if _NORTHERN_IRELAND_AREA.fullmatch(code):
        return NORTHERN_IRELAND
    district = _districts().get(code)
    return district.region_code if district else None
