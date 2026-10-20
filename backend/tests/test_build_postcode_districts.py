"""The ONSPD -> districts builder, on a small synthetic ONSPD-shaped zip (Feature 02 slice 2.3)."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest

from app.modules.geo.districts import COLUMNS, read_districts
from scripts.build_postcode_districts import OnspdError, build, main

# A subset of the real ONSPD header, in its order and with its year suffixes.
HEADER = [
    'pcd7', 'pcds', 'dointr', 'doterm', 'lad26cd', 'usrtypind', 'gridind',
    'ctry26cd', 'rgn26cd', 'lat', 'long',
]  # fmt: skip
NAMES_MEMBER = 'Documents/LAD Local Authority District names and codes UK as at 04_25.csv'
POSTCODES_MEMBER = 'Data/ONSPD_AUG_2026_UK.csv'

ENGLAND, SCOTLAND, NI, JERSEY = 'E92000001', 'S92000003', 'N92000002', 'L93000001'
NW, NE, NO_REGION = 'E12000002', 'E12000001', 'S99999999'


def postcode(
    pcds: str,
    lat: float,
    lng: float,
    *,
    lad: str = 'E08000003',
    country: str = ENGLAND,
    region: str = NW,
    terminated: str = '',
    user_type: str = '0',
    grid: str = '1',
) -> list[str]:
    return [
        pcds.replace(' ', ''), pcds, '198001', terminated, lad, user_type, grid,
        country, region, f'{lat:.6f}', f'{lng:.6f}',
    ]  # fmt: skip


def write_onspd(path: Path, rows: list[list[str]], names: dict[str, str] | None = None) -> Path:
    names = names if names is not None else {
        'E08000003': 'Manchester', 'E08000001': 'Bolton', 'S12000036': 'City of Edinburgh',
        'E06000057': 'Northumberland', 'N09000003': 'Belfast',
    }  # fmt: skip

    def csv_bytes(header: list[str], body: list[list[str]]) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer, quoting=csv.QUOTE_NONNUMERIC, lineterminator='\r\n')
        writer.writerow(header)
        writer.writerows(body)
        return ('﻿' + buffer.getvalue()).encode('utf-8')  # ONSPD files carry a BOM

    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(
            NAMES_MEMBER,
            csv_bytes(['LAD25CD', 'LAD25NM', 'LAD25NMW'], [[c, n, ''] for c, n in names.items()]),
        )
        archive.writestr(POSTCODES_MEMBER, csv_bytes(HEADER, rows))
        archive.writestr('User Guide/readme.txt', b'not data')
    return path


def by_code(rows: list[list[str]]) -> dict[str, dict[str, str]]:
    return {row[0]: dict(zip(COLUMNS, row, strict=True)) for row in rows}


def test_centroid_is_the_median_not_the_mean(tmp_path: Path) -> None:
    rows = [
        postcode('M1 1AA', 53.0, -2.0),
        postcode('M1 1AB', 53.1, -2.1),
        postcode('M1 1AD', 59.9, -7.0),  # an outlier: the mean would be 55.33, -3.70
    ]
    district = by_code(build(write_onspd(tmp_path / 'onspd.zip', rows)))['M1']
    assert (district['latitude'], district['longitude']) == ('53.100000', '-2.100000')


def test_terminated_ungridded_large_user_and_non_uk_postcodes_are_excluded(tmp_path: Path) -> None:
    rows = [
        postcode('M1 1AA', 53.0, -2.0),
        postcode('M1 1ZZ', 40.0, -9.0, terminated='201203'),
        postcode('M1 9ZZ', 99.999999, 0.0, grid='9'),
        postcode('M1 8ZZ', 41.0, -9.0, user_type='1'),
        postcode('M99 1AA', 53.5, -2.2, user_type='1'),  # a whole large-user pseudo-district
        postcode('BT1 1AA', 54.6, -5.9, lad='N09000003', country=NI, region='N99999999'),
        postcode('JE2 3AB', 49.2, -2.1, country=JERSEY, region='L99999999'),
    ]
    output = by_code(build(write_onspd(tmp_path / 'onspd.zip', rows)))
    assert list(output) == ['M1']
    assert output['M1']['latitude'] == '53.000000'


def test_region_and_area_name_follow_the_majority(tmp_path: Path) -> None:
    rows = [
        # TD15: two English postcodes, one Scottish -> North East, Northumberland.
        postcode('TD15 1AA', 55.77, -2.00, lad='E06000057', region=NE),
        postcode('TD15 1AB', 55.76, -2.01, lad='E06000057', region=NE),
        postcode('TD15 2AA', 55.70, -2.10, lad='S12000036', country=SCOTLAND, region=NO_REGION),
        # BL1: a one-one tie on local authority breaks on the lower code.
        postcode('BL1 1AA', 53.58, -2.43, lad='E08000003'),
        postcode('BL1 1AB', 53.58, -2.43, lad='E08000001'),
    ]
    output = by_code(build(write_onspd(tmp_path / 'onspd.zip', rows)))
    assert output['TD15']['region_code'] == NE
    assert output['TD15']['area_name'] == 'Northumberland'
    assert output['BL1']['area_name'] == 'Bolton'


def test_scottish_and_welsh_postcodes_take_their_nation_as_region(tmp_path: Path) -> None:
    rows = [postcode('EH1 1YZ', 55.95, -3.19, lad='S12000036', country=SCOTLAND, region=NO_REGION)]
    output = by_code(build(write_onspd(tmp_path / 'onspd.zip', rows)))
    assert output['EH1']['region_code'] == SCOTLAND


def test_unnamed_local_authority_fails_the_build(tmp_path: Path) -> None:
    rows = [postcode('M1 1AA', 53.0, -2.0, lad='E99999999')]
    with pytest.raises(OnspdError, match='E99999999'):
        build(write_onspd(tmp_path / 'onspd.zip', rows))


def test_header_without_a_needed_column_fails_the_build(tmp_path: Path) -> None:
    path = write_onspd(tmp_path / 'onspd.zip', [postcode('M1 1AA', 53.0, -2.0)])
    with zipfile.ZipFile(path, 'a') as archive:
        archive.writestr('Data/ONSPD_MAY_2026_UK.csv', b'pcds\r\n')  # now two candidates
    with pytest.raises(OnspdError, match='expected one file'):
        build(path)

    other = tmp_path / 'other.zip'
    with zipfile.ZipFile(other, 'w') as archive:
        archive.writestr(NAMES_MEMBER, b'LAD25CD,LAD25NM,LAD25NMW\r\n')
        archive.writestr(POSTCODES_MEMBER, b'pcds,doterm,lat,long\r\n')
    with pytest.raises(OnspdError, match="expected one 'usrtypind' column"):
        build(other)


def test_cli_output_is_deterministic_and_readable_by_the_lookup(tmp_path: Path) -> None:
    rows = [
        postcode('M2 1AA', 53.48, -2.24),
        postcode('M1 1AA', 53.47, -2.23),
        postcode('EH1 1YZ', 55.95, -3.19, lad='S12000036', country=SCOTLAND, region=NO_REGION),
    ]
    onspd = write_onspd(tmp_path / 'onspd.zip', rows)
    first, second = tmp_path / 'first.csv', tmp_path / 'second.csv'
    assert main(['--onspd', str(onspd), '--out', str(first)]) == 0
    assert main(['--onspd', str(onspd), '--out', str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()
    assert b'\r' not in first.read_bytes()

    districts = read_districts(first)
    assert list(districts) == ['EH1', 'M1', 'M2']
    assert districts['EH1'].area_name == 'City of Edinburgh'


def test_cli_exits_non_zero_on_bad_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    onspd = write_onspd(tmp_path / 'onspd.zip', [postcode('M1 1AA', 53.0, -2.0)], names={})
    out = tmp_path / 'out.csv'
    assert main(['--onspd', str(onspd), '--out', str(out)]) == 1
    assert 'E08000003' in capsys.readouterr().err
    assert not out.exists()
