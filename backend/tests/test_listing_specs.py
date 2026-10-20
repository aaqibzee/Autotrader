"""The `specs` payload: vocabulary, validation, size cap and versioning (Feature 02 §4, slice 2.5)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.listings import specs as specs_module
from app.modules.listings.specs import (
    EQUIPMENT,
    EQUIPMENT_BY_CODE,
    GROUP_LABELS,
    SPECS_MAX_BYTES,
    SPECS_VERSION,
    EquipmentGroup,
    ListingSpecsV1,
    SpecsError,
    dump_specs,
    equipment_by_group,
    parse_specs,
)

VALID: dict[str, Any] = {
    'equipment': ['sat_nav', 'apple_carplay', 'heated_front_seats', 'isofix'],
    'extras': ['Dealer-fitted dash cam', 'Winter tyres'],
    'power_bhp': 123,
    'acceleration_0_62_s': 9.4,
    'top_speed_mph': 121,
    'co2_g_km': 109,
    'mpg_combined': 58.9,
    'boot_litres': 311,
    'insurance_group': 14,
    'mot_expiry': '2027-03-01',
    'mot_checked_at': '2026-10-01T09:30:00Z',
}


# --- the vocabulary ------------------------------------------------------------------


def test_vocabulary_is_about_120_unique_snake_case_codes() -> None:
    codes = [item.code for item in EQUIPMENT]
    assert 100 <= len(codes) <= 140
    assert len(codes) == len(set(codes)) == len(EQUIPMENT_BY_CODE)
    assert all(re.fullmatch(r'[a-z][a-z0-9]*(_[a-z0-9]+)*', code) for code in codes)
    labels = [item.label for item in EQUIPMENT]
    assert len(labels) == len(set(labels))


def test_every_group_has_a_label_and_items() -> None:
    assert set(GROUP_LABELS) == set(EquipmentGroup)
    assert {item.group for item in EQUIPMENT} == set(EquipmentGroup)


def test_equipment_by_group_follows_vocabulary_order() -> None:
    grouped = equipment_by_group(['isofix', 'sat_nav', 'abs', 'unknown_code'])
    assert list(grouped) == [EquipmentGroup.SAFETY, EquipmentGroup.INFOTAINMENT]
    assert [item.code for item in grouped[EquipmentGroup.SAFETY]] == ['abs', 'isofix']
    assert equipment_by_group([]) == {}


# --- validation ----------------------------------------------------------------------


def test_valid_payload_round_trips_with_version_1() -> None:
    parsed = parse_specs(VALID)
    stored, version = dump_specs(parsed)
    assert version == SPECS_VERSION == 1
    assert stored == VALID
    assert parse_specs(stored, version) == parsed
    assert parsed.mot_expiry == date(2027, 3, 1)
    assert parsed.mot_checked_at == datetime(2026, 10, 1, 9, 30, tzinfo=UTC)


def test_empty_payload_is_valid_and_stores_as_an_empty_object() -> None:
    for raw in (None, {}):
        assert dump_specs(parse_specs(raw)) == ({}, 1)


def _errors(raw: dict[str, Any]) -> list[str]:
    with pytest.raises(ValidationError) as raised:
        parse_specs(raw)
    return [str(error['loc'][0]) if error['loc'] else '' for error in raised.value.errors()]


@pytest.mark.parametrize(
    ('change', 'field'),
    [
        ({'colour_code': 'red'}, 'colour_code'),  # unknown key: extra="forbid"
        ({'equipment': ['sat_nav', 'hover_mode']}, 'equipment'),
        ({'equipment': ['sat_nav', 'sat_nav']}, 'equipment'),
        ({'equipment': 'sat_nav'}, 'equipment'),
        ({'extras': ['x'] * 11}, 'extras'),
        ({'extras': ['x' * 61]}, 'extras'),
        ({'extras': ['   ']}, 'extras'),
        ({'extras': ['line one\nline two']}, 'extras'),
        ({'power_bhp': 0}, 'power_bhp'),
        ({'power_bhp': 2_001}, 'power_bhp'),
        ({'acceleration_0_62_s': 0.5}, 'acceleration_0_62_s'),
        ({'top_speed_mph': 301}, 'top_speed_mph'),
        ({'co2_g_km': -1}, 'co2_g_km'),
        ({'mpg_combined': 0}, 'mpg_combined'),
        ({'battery_kwh': 0}, 'battery_kwh'),
        ({'range_miles': 0}, 'range_miles'),
        ({'boot_litres': -1}, 'boot_litres'),
        ({'insurance_group': 51}, 'insurance_group'),
        ({'mot_expiry': 'next year'}, 'mot_expiry'),
        ({'mot_checked_at': '2026-10-01T09:30:00'}, 'mot_checked_at'),  # naive datetime
    ],
)
def test_invalid_fields_are_refused_with_their_location(change: dict[str, Any], field: str) -> None:
    assert _errors({**VALID, **change}) == [field]


def test_extras_are_trimmed() -> None:
    assert parse_specs({'extras': ['  Winter tyres  ']}).extras == ['Winter tyres']


def test_the_model_is_immutable() -> None:
    with pytest.raises(ValidationError):
        parse_specs(VALID).power_bhp = 1  # type: ignore[misc]


# --- the 16 KB cap -------------------------------------------------------------------


def test_payload_over_16_kb_is_refused_before_validation() -> None:
    oversized = {'extras': ['x' * 60] * 300}  # also invalid, but the size check comes first
    with pytest.raises(SpecsError, match='larger than 16384 bytes'):
        parse_specs(oversized)


def test_cap_counts_utf8_bytes_not_characters() -> None:
    # 9,000 two-byte characters: under 16,384 characters, over 16,384 bytes.
    with pytest.raises(SpecsError):
        parse_specs({'notes': 'é' * 9_000})


def test_largest_valid_payload_fits_well_inside_the_cap() -> None:
    largest = {
        **VALID,
        'equipment': [item.code for item in EQUIPMENT],
        'extras': ['x' * 60] * 10,
        'battery_kwh': 100.0,
        'range_miles': 300,
    }
    stored, _ = dump_specs(parse_specs(largest))
    assert specs_module._serialised_size(stored) < SPECS_MAX_BYTES / 2


# --- versioning ----------------------------------------------------------------------


@pytest.mark.parametrize('version', [0, 2, -1])
def test_unknown_versions_are_refused(version: int) -> None:
    with pytest.raises(SpecsError, match='unknown specs version'):
        parse_specs(VALID, version)


def test_older_versions_are_upgraded_on_read(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate the future: current is V2, and a V1 -> V2 upgrade renames a key. The
    # upgraded dict is validated by the current model (here V1's shape stands in).
    monkeypatch.setattr(specs_module, 'SPECS_VERSION', 2)
    monkeypatch.setitem(specs_module.UPGRADES, 1, lambda raw: {'power_bhp': raw.pop('bhp'), **raw})
    parsed = parse_specs({'bhp': 150, 'top_speed_mph': 130}, 1)
    assert isinstance(parsed, ListingSpecsV1)
    assert (parsed.power_bhp, parsed.top_speed_mph) == (150, 130)
    # A payload already at the current version is not upgraded.
    assert parse_specs({'power_bhp': 99}, 2).power_bhp == 99
