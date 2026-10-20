"""Vehicle enumerations (Feature 02 §1).

Each is stored as a `text` column guarded by a named CHECK built with
`app.db.checks.enum_check`, never a native Postgres enum. Adding a value means a
migration that calls `replace_enum_check`; the enum-drift test fails until it exists.
"""

from __future__ import annotations

from enum import StrEnum


class BodyType(StrEnum):
    HATCHBACK = 'hatchback'
    SALOON = 'saloon'
    ESTATE = 'estate'
    SUV = 'suv'
    COUPE = 'coupe'
    CONVERTIBLE = 'convertible'
    MPV = 'mpv'
    PICKUP = 'pickup'
    VAN = 'van'


class FuelType(StrEnum):
    PETROL = 'petrol'
    DIESEL = 'diesel'
    HYBRID = 'hybrid'
    PLUG_IN_HYBRID = 'plug_in_hybrid'
    ELECTRIC = 'electric'
    OTHER = 'other'


class Transmission(StrEnum):
    MANUAL = 'manual'
    AUTOMATIC = 'automatic'


class Colour(StrEnum):
    BLACK = 'black'
    WHITE = 'white'
    SILVER = 'silver'
    GREY = 'grey'
    BLUE = 'blue'
    RED = 'red'
    GREEN = 'green'
    YELLOW = 'yellow'
    ORANGE = 'orange'
    BROWN = 'brown'
    BEIGE = 'beige'
    GOLD = 'gold'
    PURPLE = 'purple'
    BRONZE = 'bronze'
    OTHER = 'other'
