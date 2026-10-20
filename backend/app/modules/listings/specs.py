"""The `specs` JSONB: display-only long tail, validated and versioned (Feature 02 §4).

Every write goes through `ListingSpecsV1` (`extra="forbid"`) and is stored with
`specs_version = 1`. Every read goes through `parse_specs(raw, version)`, which upgrades
older shapes step by step, so a later `ListingSpecsV2` needs one upgrade function and no
backfill. A field moves out of here into a typed column the moment anything filters or
sorts on it (§4 rule).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

SPECS_VERSION = 1
SPECS_MAX_BYTES = 16 * 1024
MAX_EXTRAS = 10
EXTRA_MAX_LENGTH = 60


class EquipmentGroup(StrEnum):
    """Display groups, in the order Feature 08 shows them."""

    SAFETY = 'safety'
    DRIVER_ASSISTANCE = 'driver_assistance'
    COMFORT = 'comfort'
    INFOTAINMENT = 'infotainment'
    EXTERIOR = 'exterior'
    INTERIOR = 'interior'
    PRACTICALITY = 'practicality'
    PERFORMANCE = 'performance'
    ELECTRIC = 'electric'


GROUP_LABELS: dict[EquipmentGroup, str] = {
    EquipmentGroup.SAFETY: 'Safety',
    EquipmentGroup.DRIVER_ASSISTANCE: 'Driver assistance',
    EquipmentGroup.COMFORT: 'Comfort',
    EquipmentGroup.INFOTAINMENT: 'Infotainment',
    EquipmentGroup.EXTERIOR: 'Exterior',
    EquipmentGroup.INTERIOR: 'Interior',
    EquipmentGroup.PRACTICALITY: 'Practicality',
    EquipmentGroup.PERFORMANCE: 'Performance and handling',
    EquipmentGroup.ELECTRIC: 'Electric and hybrid',
}


@dataclass(frozen=True)
class EquipmentItem:
    code: str
    label: str
    group: EquipmentGroup


def _items(group: EquipmentGroup, *pairs: tuple[str, str]) -> tuple[EquipmentItem, ...]:
    return tuple(EquipmentItem(code, label, group) for code, label in pairs)


# Codes are stored in listings, so they never change once released: add new codes, and
# retire one only with a specs version bump and an upgrade function.
EQUIPMENT: tuple[EquipmentItem, ...] = (
    *_items(
        EquipmentGroup.SAFETY,
        ('abs', 'Anti-lock brakes'),
        ('stability_control', 'Electronic stability control'),
        ('traction_control', 'Traction control'),
        ('isofix', 'ISOFIX child seat mounts'),
        ('front_airbags', 'Front airbags'),
        ('side_airbags', 'Side airbags'),
        ('curtain_airbags', 'Curtain airbags'),
        ('knee_airbag', 'Driver knee airbag'),
        ('tyre_pressure_monitoring', 'Tyre pressure monitoring'),
        ('emergency_call', 'Emergency call (eCall)'),
        ('alarm', 'Alarm'),
        ('immobiliser', 'Immobiliser'),
        ('tracker', 'Tracker'),
    ),
    *_items(
        EquipmentGroup.DRIVER_ASSISTANCE,
        ('cruise_control', 'Cruise control'),
        ('adaptive_cruise_control', 'Adaptive cruise control'),
        ('speed_limiter', 'Speed limiter'),
        ('lane_keep_assist', 'Lane keep assist'),
        ('lane_departure_warning', 'Lane departure warning'),
        ('blind_spot_monitoring', 'Blind spot monitoring'),
        ('emergency_braking', 'Autonomous emergency braking'),
        ('traffic_sign_recognition', 'Traffic sign recognition'),
        ('driver_attention_alert', 'Driver attention alert'),
        ('rear_cross_traffic_alert', 'Rear cross-traffic alert'),
        ('front_parking_sensors', 'Front parking sensors'),
        ('rear_parking_sensors', 'Rear parking sensors'),
        ('reversing_camera', 'Reversing camera'),
        ('surround_view_camera', '360-degree camera'),
        ('park_assist', 'Self-parking'),
        ('hill_start_assist', 'Hill start assist'),
        ('hill_descent_control', 'Hill descent control'),
        ('head_up_display', 'Head-up display'),
        ('auto_high_beam', 'Automatic high beam'),
        ('night_vision', 'Night vision'),
    ),
    *_items(
        EquipmentGroup.COMFORT,
        ('air_conditioning', 'Air conditioning'),
        ('climate_control', 'Climate control'),
        ('dual_zone_climate', 'Dual-zone climate control'),
        ('tri_zone_climate', 'Three-zone climate control'),
        ('heated_front_seats', 'Heated front seats'),
        ('heated_rear_seats', 'Heated rear seats'),
        ('ventilated_seats', 'Ventilated seats'),
        ('massage_seats', 'Massage seats'),
        ('heated_steering_wheel', 'Heated steering wheel'),
        ('electric_seats', 'Electric seats'),
        ('memory_seats', 'Memory seats'),
        ('lumbar_support', 'Lumbar support'),
        ('keyless_entry', 'Keyless entry'),
        ('keyless_start', 'Keyless start'),
        ('electric_front_windows', 'Electric front windows'),
        ('electric_rear_windows', 'Electric rear windows'),
        ('auto_dimming_mirror', 'Auto-dimming rear-view mirror'),
        ('heated_windscreen', 'Heated windscreen'),
        ('rain_sensing_wipers', 'Rain-sensing wipers'),
        ('automatic_headlights', 'Automatic headlights'),
        ('remote_climate', 'Remote climate preconditioning'),
    ),
    *_items(
        EquipmentGroup.INFOTAINMENT,
        ('sat_nav', 'Satellite navigation'),
        ('apple_carplay', 'Apple CarPlay'),
        ('android_auto', 'Android Auto'),
        ('bluetooth', 'Bluetooth'),
        ('dab_radio', 'DAB radio'),
        ('usb', 'USB connection'),
        ('wireless_charging', 'Wireless phone charging'),
        ('touchscreen', 'Touchscreen'),
        ('digital_dashboard', 'Digital instrument cluster'),
        ('premium_audio', 'Premium sound system'),
        ('voice_control', 'Voice control'),
        ('wifi_hotspot', 'Wi-Fi hotspot'),
        ('rear_entertainment', 'Rear-seat entertainment'),
        ('connected_services', 'Connected app services'),
        ('aux_input', 'Auxiliary input'),
    ),
    *_items(
        EquipmentGroup.EXTERIOR,
        ('alloy_wheels', 'Alloy wheels'),
        ('led_headlights', 'LED headlights'),
        ('matrix_headlights', 'Matrix LED headlights'),
        ('xenon_headlights', 'Xenon headlights'),
        ('fog_lights', 'Fog lights'),
        ('daytime_running_lights', 'Daytime running lights'),
        ('panoramic_roof', 'Panoramic roof'),
        ('sunroof', 'Sunroof'),
        ('privacy_glass', 'Privacy glass'),
        ('roof_rails', 'Roof rails'),
        ('tow_bar', 'Tow bar'),
        ('electric_tailgate', 'Electric tailgate'),
        ('hands_free_tailgate', 'Hands-free tailgate'),
        ('folding_mirrors', 'Electric folding mirrors'),
        ('heated_mirrors', 'Heated mirrors'),
        ('metallic_paint', 'Metallic paint'),
    ),
    *_items(
        EquipmentGroup.INTERIOR,
        ('leather_seats', 'Leather seats'),
        ('part_leather_seats', 'Part-leather seats'),
        ('alcantara', 'Alcantara trim'),
        ('sports_seats', 'Sports seats'),
        ('ambient_lighting', 'Ambient lighting'),
        ('leather_steering_wheel', 'Leather steering wheel'),
        ('paddle_shifters', 'Paddle shifters'),
        ('split_folding_rear_seats', 'Split-folding rear seats'),
        ('third_row_seats', 'Third-row seats'),
        ('front_armrest', 'Front centre armrest'),
        ('rear_armrest', 'Rear centre armrest'),
    ),
    *_items(
        EquipmentGroup.PRACTICALITY,
        ('spare_wheel', 'Full-size spare wheel'),
        ('space_saver_spare', 'Space-saver spare wheel'),
        ('tyre_repair_kit', 'Tyre repair kit'),
        ('cargo_cover', 'Load cover'),
        ('adjustable_boot_floor', 'Adjustable boot floor'),
        ('ski_hatch', 'Ski hatch'),
        ('power_socket', '12V power socket'),
        ('wheelchair_accessible', 'Wheelchair accessible'),
        ('service_history', 'Full service history'),
        ('two_keys', 'Two keys'),
    ),
    *_items(
        EquipmentGroup.PERFORMANCE,
        ('sports_suspension', 'Sports suspension'),
        ('adaptive_suspension', 'Adaptive suspension'),
        ('air_suspension', 'Air suspension'),
        ('four_wheel_drive', 'Four-wheel drive'),
        ('limited_slip_differential', 'Limited-slip differential'),
        ('drive_modes', 'Selectable drive modes'),
        ('launch_control', 'Launch control'),
        ('sports_exhaust', 'Sports exhaust'),
        ('start_stop', 'Engine start-stop'),
    ),
    *_items(
        EquipmentGroup.ELECTRIC,
        ('rapid_charging', 'Rapid (DC) charging'),
        ('type_2_cable', 'Type 2 charging cable'),
        ('three_pin_cable', 'Three-pin charging cable'),
        ('heat_pump', 'Heat pump'),
        ('battery_preconditioning', 'Battery preconditioning'),
        ('vehicle_to_load', 'Vehicle-to-load'),
        ('one_pedal_driving', 'One-pedal driving'),
        ('regenerative_braking', 'Adjustable regenerative braking'),
    ),
)

EQUIPMENT_BY_CODE: dict[str, EquipmentItem] = {item.code: item for item in EQUIPMENT}


class SpecsError(ValueError):
    """Raw specs refused before field validation: too large, or an unknown version."""


def _known_codes(codes: list[str]) -> list[str]:
    unknown = sorted(set(codes) - EQUIPMENT_BY_CODE.keys())
    if unknown:
        raise ValueError(f'unknown equipment codes: {", ".join(unknown)}')
    if len(set(codes)) != len(codes):
        raise ValueError('equipment codes must not repeat')
    return codes


Extra = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=EXTRA_MAX_LENGTH),
]


class ListingSpecsV1(BaseModel):
    """Version 1 of the `specs` payload. Every field is optional; ranges are generous."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    equipment: Annotated[
        list[str], Field(max_length=len(EQUIPMENT)), AfterValidator(_known_codes)
    ] = []
    extras: Annotated[list[Extra], Field(max_length=MAX_EXTRAS)] = []
    power_bhp: Annotated[int, Field(ge=1, le=2_000)] | None = None
    acceleration_0_62_s: Annotated[float, Field(ge=1, le=60)] | None = None
    top_speed_mph: Annotated[int, Field(ge=1, le=300)] | None = None
    co2_g_km: Annotated[int, Field(ge=0, le=1_000)] | None = None
    mpg_combined: Annotated[float, Field(gt=0, le=1_000)] | None = None
    battery_kwh: Annotated[float, Field(gt=0, le=300)] | None = None
    range_miles: Annotated[int, Field(ge=1, le=1_500)] | None = None
    boot_litres: Annotated[int, Field(ge=0, le=10_000)] | None = None
    insurance_group: Annotated[int, Field(ge=1, le=50)] | None = None
    mot_expiry: date | None = None
    # When the MOT data was fetched (Feature 05 lookup); Feature 08 shows "as of" it.
    mot_checked_at: AwareDatetime | None = None

    @field_validator('extras')
    @classmethod
    def _printable_extras(cls, extras: list[str]) -> list[str]:
        if any(not extra.isprintable() for extra in extras):
            raise ValueError('extras must be single-line plain text')
        return extras


ListingSpecs = ListingSpecsV1

# Version N -> N+1 upgrades of the raw dict, applied on read. Empty until a V2 exists.
UPGRADES: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def _serialised_size(raw: Mapping[str, Any]) -> int:
    return len(json.dumps(raw, separators=(',', ':'), ensure_ascii=False, default=str).encode())


def parse_specs(raw: Mapping[str, Any] | None, version: int = SPECS_VERSION) -> ListingSpecs:
    """Validate a stored or submitted payload, upgrading it from `version` first.

    Raises `SpecsError` for an oversized payload or unknown version, and pydantic's
    `ValidationError` (field-level detail for a 422) for anything else.
    """
    data = dict(raw or {})
    if _serialised_size(data) > SPECS_MAX_BYTES:
        raise SpecsError(f'specs are larger than {SPECS_MAX_BYTES} bytes')
    if not 1 <= version <= SPECS_VERSION:
        raise SpecsError(f'unknown specs version {version}')
    while version < SPECS_VERSION:
        data = UPGRADES[version](data)
        version += 1
    return ListingSpecs.model_validate(data)


def dump_specs(specs: ListingSpecs) -> tuple[dict[str, Any], int]:
    """The `(specs, specs_version)` pair to store. Unset fields are omitted."""
    return specs.model_dump(mode='json', exclude_defaults=True), SPECS_VERSION


def equipment_by_group(codes: list[str]) -> dict[EquipmentGroup, list[EquipmentItem]]:
    """Codes grouped for display (Feature 08), groups and items in vocabulary order."""
    chosen = set(codes)
    grouped: dict[EquipmentGroup, list[EquipmentItem]] = {}
    for item in EQUIPMENT:
        if item.code in chosen:
            grouped.setdefault(item.group, []).append(item)
    return grouped
