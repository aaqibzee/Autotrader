"""Derived listing values (Feature 02 §6, slice 2.5). Pure functions; one database check."""

from __future__ import annotations

import re
from datetime import date

import pytest
from sqlalchemy import text

from app.db.session import sync_engine
from app.modules.geo.services import region_for_postcode as geo_region_for_postcode
from app.modules.listings import derive
from app.modules.listings.derive import (
    SLUG_MAX_LENGTH,
    build_title,
    derive_ulez,
    listing_slug,
    normalise_vrm,
)
from app.modules.listings.models import TITLE_MAX_LENGTH, VRM_PATTERN
from app.modules.taxonomy.enums import FuelType

# --- build_title ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ('parts', 'title'),
    [
        (
            (2019, 'Ford', 'Fiesta', '1.0 EcoBoost ST-Line 5dr'),
            '2019 Ford Fiesta 1.0 EcoBoost ST-Line 5dr',
        ),
        ((2021, 'Citroën', 'Ë-C4', None), '2021 Citroën Ë-C4'),
        (
            (2018, 'Škoda', 'Octavia', '  2.0 TDI   vRS\tEstate '),
            '2018 Škoda Octavia 2.0 TDI vRS Estate',
        ),
        (
            (2020, 'Mercedes-Benz', 'A-Class', 'A180 AMG Line (Premium)'),
            '2020 Mercedes-Benz A-Class A180 AMG Line (Premium)',
        ),
        ((None, 'Ford', None, ''), 'Ford'),
        ((None, None, None, None), ''),
        ((None, '  ', '', '\n'), ''),
    ],
)
def test_build_title(
    parts: tuple[int | None, str | None, str | None, str | None], title: str
) -> None:
    assert build_title(*parts) == title


def test_long_title_is_cut_at_a_word_boundary() -> None:
    variant = ' '.join(['Exclusive'] * 30)
    title = build_title(2019, 'Ford', 'Fiesta', variant)
    assert len(title) <= TITLE_MAX_LENGTH
    assert title.endswith('Exclusive')
    assert title.startswith('2019 Ford Fiesta Exclusive')


def test_title_exactly_at_the_limit_is_kept() -> None:
    prefix = '2019 Ford Fiesta '
    variant = 'x' * (TITLE_MAX_LENGTH - len(prefix))
    assert build_title(2019, 'Ford', 'Fiesta', variant) == prefix + variant


def test_single_word_longer_than_the_limit_is_cut() -> None:
    title = build_title(None, None, None, 'x' * 500)
    assert title == 'x' * TITLE_MAX_LENGTH


# --- listing_slug --------------------------------------------------------------------


@pytest.mark.parametrize(
    ('title', 'slug'),
    [
        ('2019 Ford Fiesta 1.0 EcoBoost ST-Line 5dr', '2019-ford-fiesta-1-0-ecoboost-st-line-5dr'),
        ('2021 Citroën Ë-C4', '2021-citroen-e-c4'),
        (
            '2020 Mercedes-Benz A-Class A180 AMG Line (Premium)',
            '2020-mercedes-benz-a-class-a180-amg-line-premium',
        ),
        ('2017 Ford Ka+ 1.2', '2017-ford-ka-plus-1-2'),
        ('', 'car'),
        ('!!! ???', 'car'),
    ],
)
def test_listing_slug(title: str, slug: str) -> None:
    assert listing_slug(title) == slug


def test_long_slug_is_cut_at_a_hyphen_and_stays_well_formed() -> None:
    slug = listing_slug(build_title(2019, 'Ford', 'Fiesta', ' '.join(['Exclusive'] * 30)))
    assert len(slug) <= SLUG_MAX_LENGTH
    assert slug.endswith('-exclusive')
    assert re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', slug)


def test_single_word_slug_longer_than_the_limit_is_cut() -> None:
    assert listing_slug('x' * 200) == 'x' * SLUG_MAX_LENGTH


# --- derive_ulez ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ('fuel', 'registered', 'compliant'),
    [
        (FuelType.PETROL, date(2005, 12, 31), False),
        (FuelType.PETROL, date(2006, 1, 1), True),
        (FuelType.DIESEL, date(2015, 8, 31), False),
        (FuelType.DIESEL, date(2015, 9, 1), True),
        (FuelType.DIESEL, date(2010, 1, 1), False),
        # A8: hybrids are petrol-electric, so they follow the petrol cut-off.
        (FuelType.HYBRID, date(2005, 12, 31), False),
        (FuelType.HYBRID, date(2006, 1, 1), True),
        (FuelType.PLUG_IN_HYBRID, date(2005, 12, 31), False),
        (FuelType.PLUG_IN_HYBRID, date(2006, 1, 1), True),
        (FuelType.ELECTRIC, date(1998, 1, 1), True),
        (FuelType.ELECTRIC, None, True),
        (FuelType.OTHER, date(2024, 1, 1), False),
        (FuelType.OTHER, None, False),
        # A draft without the inputs has no answer yet (the column is nullable for drafts).
        (FuelType.PETROL, None, None),
        (FuelType.DIESEL, None, None),
        (None, date(2020, 1, 1), None),
        (None, None, None),
    ],
)
def test_derive_ulez(fuel: str | None, registered: date | None, compliant: bool | None) -> None:
    assert derive_ulez(fuel, registered) is compliant


def test_derive_ulez_covers_every_fuel_type() -> None:
    # A new FuelType must get a ULEZ rule, not fall through silently.
    for fuel in FuelType:
        assert derive_ulez(fuel, date(2020, 1, 1)) in (True, False)


def test_derive_ulez_refuses_an_unknown_fuel_type() -> None:
    with pytest.raises(ValueError, match='steam'):
        derive_ulez('steam', date(2020, 1, 1))


# --- normalise_vrm -------------------------------------------------------------------


@pytest.mark.parametrize(
    ('raw', 'vrm'),
    [
        ('ZA19 KXR', 'ZA19KXR'),
        ('za19kxr', 'ZA19KXR'),
        ('  zA19-kXr ', 'ZA19KXR'),
        ('Z.A.1.9 K.X.R', 'ZA19KXR'),
        ('A1', 'A1'),
        ('ABC 123D', 'ABC123D'),
        ('1 ABC', '1ABC'),
    ],
)
def test_normalise_vrm(raw: str, vrm: str) -> None:
    assert normalise_vrm(raw) == vrm


@pytest.mark.parametrize('raw', [None, '', '   ', 'A', '-', 'ZA19KXRA', 'ZA19 KXR 1', 'Ω'])
def test_normalise_vrm_rejects(raw: str | None) -> None:
    assert normalise_vrm(raw) is None


@pytest.mark.parametrize('raw', ['ZA19 KXR', 'a1', 'abc 123d', 'zz99zzz'])
def test_normalised_vrm_satisfies_the_database_pattern(raw: str) -> None:
    vrm = normalise_vrm(raw)
    assert vrm is not None
    assert re.fullmatch(VRM_PATTERN, vrm)


def test_vrm_pattern_is_the_one_the_database_enforces() -> None:
    # Reader/writer agreement: the function's output form is the CHECK's form.
    with sync_engine.connect() as connection:
        definition = connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_listings_vrm_normalised'"
            )
        ).scalar_one()
    assert VRM_PATTERN in definition


# --- region_for_postcode -------------------------------------------------------------


def test_region_for_postcode_is_geos() -> None:
    assert derive.region_for_postcode is geo_region_for_postcode
    assert derive.region_for_postcode('M1 1AE') == 'E12000002'
