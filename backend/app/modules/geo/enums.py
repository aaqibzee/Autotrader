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
