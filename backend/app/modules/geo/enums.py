"""Geography enumerations (Feature 02 §2, §8)."""

from __future__ import annotations

from enum import StrEnum


class Region(StrEnum):
    """The 12 ONS regions and nations, by GSS code.

    Nine English regions, then Wales, Scotland and Northern Ireland, which have no region
    tier and use their country code. Stored in `dealers.region_code` behind an enum CHECK.
    """

    NORTH_EAST = 'E12000001'
    NORTH_WEST = 'E12000002'
    YORKSHIRE_AND_THE_HUMBER = 'E12000003'
    EAST_MIDLANDS = 'E12000004'
    WEST_MIDLANDS = 'E12000005'
    EAST_OF_ENGLAND = 'E12000006'
    LONDON = 'E12000007'
    SOUTH_EAST = 'E12000008'
    SOUTH_WEST = 'E12000009'
    WALES = 'W92000004'
    SCOTLAND = 'S92000003'
    NORTHERN_IRELAND = 'N92000002'


REGION_NAMES: dict[Region, str] = {
    Region.NORTH_EAST: 'North East',
    Region.NORTH_WEST: 'North West',
    Region.YORKSHIRE_AND_THE_HUMBER: 'Yorkshire and The Humber',
    Region.EAST_MIDLANDS: 'East Midlands',
    Region.WEST_MIDLANDS: 'West Midlands',
    Region.EAST_OF_ENGLAND: 'East of England',
    Region.LONDON: 'London',
    Region.SOUTH_EAST: 'South East',
    Region.SOUTH_WEST: 'South West',
    Region.WALES: 'Wales',
    Region.SCOTLAND: 'Scotland',
    Region.NORTHERN_IRELAND: 'Northern Ireland',
}

# Short operator codes for CLI flags (`seed_demo --region NW`).
REGION_SHORT_CODES: dict[Region, str] = {
    Region.NORTH_EAST: 'NE',
    Region.NORTH_WEST: 'NW',
    Region.YORKSHIRE_AND_THE_HUMBER: 'YH',
    Region.EAST_MIDLANDS: 'EM',
    Region.WEST_MIDLANDS: 'WM',
    Region.EAST_OF_ENGLAND: 'EE',
    Region.LONDON: 'LON',
    Region.SOUTH_EAST: 'SE',
    Region.SOUTH_WEST: 'SW',
    Region.WALES: 'WAL',
    Region.SCOTLAND: 'SCO',
    Region.NORTHERN_IRELAND: 'NI',
}


def _key(text: str) -> str:
    return ''.join(character for character in text.upper() if character.isalnum())


_REGION_LOOKUP: dict[str, Region] = {
    _key(spelling): region
    for region in Region
    for spelling in (region.value, region.name, REGION_NAMES[region], REGION_SHORT_CODES[region])
}


def parse_region(text: str) -> Region:
    """A region from its short code, GSS code or name, ignoring case, spaces and hyphens."""
    try:
        return _REGION_LOOKUP[_key(text)]
    except KeyError:
        codes = ', '.join(REGION_SHORT_CODES.values())
        raise ValueError(f'unknown region {text!r}: use one of {codes} or a GSS code') from None
