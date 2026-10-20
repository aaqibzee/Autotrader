"""Derive the postcode-district centroid file from the ONS Postcode Directory (Feature 02 A3).

    uv run python -m scripts.build_postcode_districts --onspd PATH/ONSPD_AUG_2026.zip

Reads the ONSPD zip exactly as downloaded (never extracted: the CSV inside is ~1.5 GB) and
streams it row by row. Keeps live, geographic postcodes: no termination date, a real grid
reference, and a small user (large-user and PO Box postcodes are placed at the sorting
office, and whole pseudo-districts consist of nothing else). Dropped as well:

- the Channel Islands and the Isle of Man, which are not in the UK;
- Northern Ireland (`BT`). ONS redistributes it under a Land and Property Services
  licence that allows internal business use only, not the Open Government Licence, so it
  cannot ship in this repository. `region_for_postcode` still maps `BT` to Northern
  Ireland by rule.

Postcodes are grouped by outward code, and each district gets:

- the *median* latitude and longitude, so a few outlying postcodes cannot drag the
  centroid into the sea the way a mean can;
- the region holding most of the district's postcodes;
- the name of the local authority holding most of them (`area_name`; ONSPD carries no
  post town, which is Royal Mail PAF data and licensed separately).

Ties break on the lower code, and rows are sorted by outward code, so the same edition
always produces a byte-identical file. Rebuild steps and attribution:
`backend/data/geo/README.md`.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import statistics
import sys
import zipfile
from array import array
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from app.modules.geo.districts import COLUMNS, DEFAULT_DISTRICTS_FILE, REGIONS, outward_code

_POSTCODES_MEMBER = re.compile(r'Data/ONSPD_[A-Z]{3}_\d{4}_UK\.csv')
_LAD_NAMES_MEMBER = re.compile(r'Documents/LAD Local Authority District names and codes UK.*\.csv')
NO_GRID_REFERENCE = '9'
SMALL_USER = '0'
# Not under the Open Government Licence (see the module docstring).
EXCLUDED_COUNTRIES = frozenset({'N92000002'})


class OnspdError(ValueError):
    """The input is not an ONSPD zip this builder understands."""


@dataclass
class _Accumulator:
    latitudes: array[float] = field(default_factory=lambda: array('d'))
    longitudes: array[float] = field(default_factory=lambda: array('d'))
    regions: Counter[str] = field(default_factory=Counter)
    authorities: Counter[str] = field(default_factory=Counter)


def _column(header: list[str], prefix: str) -> int:
    """Index of the column named `prefix` or `prefix` + a two-digit year (`rgn26cd`).

    ONSPD renames its geography columns every year (`rgn25cd` -> `rgn26cd`), so the year
    is matched loosely and everything else exactly.
    """
    pattern = re.compile(rf'{prefix}(\d\d)?(cd)?', re.IGNORECASE)
    matches = [index for index, name in enumerate(header) if pattern.fullmatch(name)]
    if len(matches) != 1:
        raise OnspdError(f'expected one {prefix!r} column, found {len(matches)}')
    return matches[0]


def _region(country_code: str, region_code: str) -> str | None:
    # England has a region tier; Wales, Scotland and Northern Ireland are their own region.
    code = region_code if country_code.startswith('E') else country_code
    return code if code in REGIONS else None


def _most_common(counter: Counter[str]) -> str:
    return min(counter.items(), key=lambda item: (-item[1], item[0]))[0]


def aggregate(
    rows: Iterable[list[str]], header: list[str], authority_names: Mapping[str, str]
) -> list[list[str]]:
    """Output rows (as `COLUMNS`, sorted) from ONSPD rows. Pure apart from its input."""
    postcode = _column(header, 'pcds')
    terminated = _column(header, 'doterm')
    user_type = _column(header, 'usrtypind')
    grid = _column(header, 'gridind')
    country = _column(header, 'ctry')
    region = _column(header, 'rgn')
    authority = _column(header, 'lad')
    latitude = _column(header, 'lat')
    longitude = _column(header, 'long')

    districts: dict[str, _Accumulator] = {}
    for row in rows:
        if (
            row[terminated]
            or row[grid] == NO_GRID_REFERENCE
            or row[user_type] != SMALL_USER
            or row[country] in EXCLUDED_COUNTRIES
        ):
            continue
        region_code = _region(row[country], row[region])
        code = outward_code(row[postcode])
        if region_code is None or code is None:
            continue
        district = districts.setdefault(code, _Accumulator())
        district.latitudes.append(float(row[latitude]))
        district.longitudes.append(float(row[longitude]))
        district.regions[region_code] += 1
        district.authorities[row[authority]] += 1

    output: list[list[str]] = []
    unnamed: set[str] = set()
    for code in sorted(districts):
        district = districts[code]
        authority_code = _most_common(district.authorities)
        name = authority_names.get(authority_code)
        if not name:
            unnamed.add(authority_code)
            continue
        output.append(
            [
                code,
                f'{statistics.median(district.latitudes):.6f}',
                f'{statistics.median(district.longitudes):.6f}',
                _most_common(district.regions),
                name,
            ]
        )
    if unnamed:
        raise OnspdError(f'local authority codes with no name: {", ".join(sorted(unnamed))}')
    return output


def _member(archive: zipfile.ZipFile, pattern: re.Pattern[str]) -> str:
    names = [name for name in archive.namelist() if pattern.fullmatch(name)]
    if len(names) != 1:
        raise OnspdError(f'expected one file matching {pattern.pattern}, found {names}')
    return names[0]


def _csv_rows(archive: zipfile.ZipFile, member: str) -> Iterator[list[str]]:
    with archive.open(member) as raw:
        # ONSPD files start with a byte-order mark.
        yield from csv.reader(io.TextIOWrapper(raw, encoding='utf-8-sig', newline=''))


def build(onspd_zip: Path) -> list[list[str]]:
    with zipfile.ZipFile(onspd_zip) as archive:
        names = _csv_rows(archive, _member(archive, _LAD_NAMES_MEMBER))
        next(names)  # header: LADnnCD, LADnnNM, LADnnNMW
        authority_names = {row[0]: row[1] for row in names if row and row[0]}
        rows = _csv_rows(archive, _member(archive, _POSTCODES_MEMBER))
        header = next(rows)
        return aggregate(rows, header, authority_names)


def write_districts(rows: list[list[str]], path: Path) -> None:
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build postcode_districts.csv from ONSPD.')
    parser.add_argument('--onspd', type=Path, required=True, help='the ONSPD zip, as downloaded')
    parser.add_argument('--out', type=Path, default=DEFAULT_DISTRICTS_FILE)
    arguments = parser.parse_args(argv)

    try:
        rows = build(arguments.onspd)
    except OnspdError as error:
        print(f'build_postcode_districts: {error}', file=sys.stderr)
        return 1
    write_districts(rows, arguments.out)
    print(f'wrote {len(rows)} districts to {arguments.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
