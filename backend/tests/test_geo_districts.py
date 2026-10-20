"""Postcode parsing, the district lookup and the committed districts CSV (Feature 02 slice 2.3).

No database: the lookup is a bundled file.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import pytest

from app.modules.geo.districts import (
    COLUMNS,
    DEFAULT_DISTRICTS_FILE,
    NORTHERN_IRELAND,
    OUTWARD_PATTERN,
    REGIONS,
    District,
    all_districts,
    district_for,
    outward_code,
    read_districts,
    region_for_postcode,
)

# Great Britain, generously: Scilly to Shetland, Ardnamurchan to Lowestoft, plus the
# Western Isles and St Kilda.
LATITUDE_RANGE = (49.8, 61.0)
LONGITUDE_RANGE = (-8.7, 1.8)
# ~2,740 GB geographic districts (README). A rebuild that loses a few hundred is broken.
MINIMUM_DISTRICTS = 2_700


def dataset_problems(districts: dict[str, District]) -> list[str]:
    problems: list[str] = []
    if len(districts) < MINIMUM_DISTRICTS:
        problems.append(f'only {len(districts)} districts')
    for code, district in districts.items():
        if code != district.outward_code or not OUTWARD_PATTERN.fullmatch(code):
            problems.append(f'{code}: malformed outward code')
        if not LATITUDE_RANGE[0] <= district.latitude <= LATITUDE_RANGE[1]:
            problems.append(f'{code}: latitude {district.latitude} outside Great Britain')
        if not LONGITUDE_RANGE[0] <= district.longitude <= LONGITUDE_RANGE[1]:
            problems.append(f'{code}: longitude {district.longitude} outside Great Britain')
        if district.region_code not in REGIONS:
            problems.append(f'{code}: unknown region {district.region_code}')
        if district.region_code == NORTHERN_IRELAND or code.startswith('BT'):
            problems.append(f'{code}: Northern Ireland data is not OGL (README)')
        if not district.area_name:
            problems.append(f'{code}: no area name')
    return problems


# --- the committed dataset ----------------------------------------------------------


def test_committed_dataset_is_sane() -> None:
    assert dataset_problems(read_districts()) == []


def test_committed_dataset_covers_every_gb_region() -> None:
    regions = {district.region_code for district in all_districts()}
    assert regions == set(REGIONS) - {NORTHERN_IRELAND}


def test_committed_dataset_is_sorted_utf8_lf_with_unique_codes() -> None:
    raw = DEFAULT_DISTRICTS_FILE.read_bytes()
    assert b'\r' not in raw
    raw.decode('utf-8')
    with DEFAULT_DISTRICTS_FILE.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.reader(handle))
    assert tuple(rows[0]) == COLUMNS
    codes = [row[0] for row in rows[1:]]
    assert codes == sorted(codes)
    assert len(codes) == len(set(codes))


@pytest.mark.parametrize(
    ('corruption', 'expected'),
    [
        ({'latitude': 0.0}, 'outside Great Britain'),
        ({'longitude': 12.0}, 'outside Great Britain'),
        ({'region_code': 'E99999999'}, 'unknown region'),
        ({'region_code': NORTHERN_IRELAND}, 'not OGL'),
        ({'area_name': ''}, 'no area name'),
    ],
)
def test_sanity_check_catches_a_corrupted_row(corruption: dict[str, object], expected: str) -> None:
    districts = dict(read_districts())
    original = districts['M1']
    districts['M1'] = replace(original, **corruption)
    problems = dataset_problems(districts)
    assert len(problems) == 1
    assert expected in problems[0]


def test_sanity_check_catches_a_truncated_dataset() -> None:
    districts = dict(list(read_districts().items())[:100])
    assert dataset_problems(districts) == ['only 100 districts']


def test_reader_rejects_an_unexpected_header(tmp_path: Path) -> None:
    path = tmp_path / 'districts.csv'
    path.write_text('outward_code,lat,lng\nM1,53.4,-2.2\n', encoding='utf-8')
    with pytest.raises(ValueError, match='header'):
        read_districts(path)


# --- parsing -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('SW1A 1AA', 'SW1A'),
        ('sw1a1aa', 'SW1A'),
        ('  Sw1A   1aA ', 'SW1A'),
        ('SW1A', 'SW1A'),
        ('m1 1ae', 'M1'),
        ('M1', 'M1'),
        ('B33 8TH', 'B33'),
        ('CR2 6XH', 'CR2'),
        ('DN55 1PT', 'DN55'),
        ('W1A 0AX', 'W1A'),
        ('EC1A 1BB', 'EC1A'),
        ('BT1 1AA', 'BT1'),
    ],
)
def test_outward_code_accepts_full_postcodes_and_outward_codes(text: str, expected: str) -> None:
    assert outward_code(text) == expected


@pytest.mark.parametrize(
    'text',
    [None, '', '   ', 'SW1A 1A', 'SW1A 1AAA', '1AA', 'M', 'ABC1', 'SW1A-1AA', 'SW1A 11A', '12345'],
)
def test_outward_code_rejects_anything_else(text: str | None) -> None:
    assert outward_code(text) is None


# --- lookups -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('postcode', 'region'),
    [
        ('SW1A 1AA', 'E12000007'),  # London
        ('M1', 'E12000002'),  # North West
        ('EH1 1YZ', 'S92000003'),  # Scotland
        ('CF10 1EP', 'W92000004'),  # Wales
        ('LS1', 'E12000003'),  # Yorkshire and The Humber
        ('TR21 0HE', 'E12000009'),  # Isles of Scilly: South West
        ('TD15', 'E12000001'),  # Berwick: an English district in a Scottish area
        ('BT1 1AA', NORTHERN_IRELAND),  # by rule, no row in the file
        ('bt93', NORTHERN_IRELAND),
    ],
)
def test_region_for_postcode(postcode: str, region: str) -> None:
    assert region_for_postcode(postcode) == region


@pytest.mark.parametrize('text', [None, '', 'not a postcode', 'ZZ1 1ZZ', 'BS98', 'JE2 3AB'])
def test_region_for_postcode_is_none_when_unknown(text: str | None) -> None:
    # BS98 is a large-user pseudo-district; JE (Jersey) is not in the UK.
    assert region_for_postcode(text) is None


def test_district_for_returns_the_centroid() -> None:
    district = district_for('sw1a 2aa')
    assert district is not None
    assert district.outward_code == 'SW1A'
    assert district.area_name == 'Westminster'
    assert district.latitude == pytest.approx(51.50, abs=0.02)
    assert district.longitude == pytest.approx(-0.13, abs=0.02)


def test_district_for_has_no_northern_ireland_centroid() -> None:
    assert district_for('BT1 1AA') is None
    assert district_for('nonsense') is None
