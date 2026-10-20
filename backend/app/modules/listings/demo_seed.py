"""Deterministic demo inventory (Feature 02 §8, slice 2.7).

`generate()` is pure: given a seed, a size, a fixed `today`/`now`, the district file and
the taxonomy catalogue, it returns the same dealers and listings every time. Nothing in it
reads the clock, the database or the network. `seed_demo()` writes that dataset through
the real derivation path (`derive.py`, `stamp_listed_at`), then fails the run if
`verify_listing_invariants()` finds any row a real writer would not have produced.

Demo data must not look real (playbook §4): plates start with `Z` (A1), dealer names
contain "Demo" and come from neutral word lists, locations are district centroids with
the outward code only (A2), and every description says the car is not for sale.
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import string
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.db.locks import AdvisoryLock, hold_advisory_lock
from app.db.uuid7 import uuid7
from app.modules.dealers.services import demo_dealers, insert_dealers
from app.modules.geo.services import District, Region, all_districts
from app.modules.listings.derive import build_title, derive_ulez, normalise_vrm
from app.modules.listings.enums import ListingStatus
from app.modules.listings.models import Listing
from app.modules.listings.services import InvariantMismatch, verify_listing_invariants
from app.modules.listings.specs import EQUIPMENT, EquipmentGroup, dump_specs, parse_specs
from app.modules.listings.visibility import stamp_listed_at
from app.modules.taxonomy.enums import BodyType, Colour, FuelType, Transmission
from app.modules.taxonomy.naming import slugify
from app.modules.taxonomy.services import CatalogueModel, catalogue

T = TypeVar('T')

DEFAULT_LISTINGS = 5_000
PERF_LISTINGS = 50_000
DEFAULT_RANDOM_SEED = 42
LISTINGS_PER_DEALER = 80
INSERT_BATCH_SIZE = 1_000
MAX_AGE_YEARS = 18

# ONS mid-2023 population estimates, millions. Northern Ireland has no districts in the
# bundled file (A11), so it gets no demo dealers.
REGION_POPULATION: dict[Region, float] = {
    Region.NORTH_EAST: 2.7,
    Region.NORTH_WEST: 7.5,
    Region.YORKSHIRE_AND_THE_HUMBER: 5.6,
    Region.EAST_MIDLANDS: 4.9,
    Region.WEST_MIDLANDS: 6.0,
    Region.EAST_OF_ENGLAND: 6.4,
    Region.LONDON: 8.9,
    Region.SOUTH_EAST: 9.4,
    Region.SOUTH_WEST: 5.8,
    Region.WALES: 3.2,
    Region.SCOTLAND: 5.5,
}

# Rough shares of UK used-car stock; makes not listed get DEFAULT_MAKE_WEIGHT.
MAKE_WEIGHTS: dict[str, float] = {
    'ford': 13, 'vauxhall': 10, 'volkswagen': 10, 'bmw': 7, 'mercedes-benz': 7, 'audi': 7,
    'toyota': 5, 'nissan': 5, 'kia': 4, 'hyundai': 4, 'peugeot': 4, 'renault': 3,
    'skoda': 3, 'mini': 3, 'land-rover': 3, 'citroen': 2, 'honda': 2, 'seat': 2,
    'volvo': 2, 'fiat': 2, 'mazda': 2, 'tesla': 1.5, 'mg': 1.5, 'dacia': 1.5,
}  # fmt: skip
DEFAULT_MAKE_WEIGHT = 0.5
EXOTIC_MAKE_WEIGHT = 0.05

# New-car price tiers (pounds) by make; anything unlisted is mainstream.
TIER_PRICE = {'budget': 17_000, 'mainstream': 25_000, 'premium': 40_000, 'luxury': 95_000, 'exotic': 220_000}  # fmt: skip
MAKE_TIER: dict[str, str] = {
    **dict.fromkeys(('dacia', 'mg', 'suzuki', 'ssangyong', 'smart', 'fiat', 'abarth'), 'budget'),
    **dict.fromkeys(
        ('audi', 'bmw', 'mercedes-benz', 'volvo', 'lexus', 'land-rover', 'jaguar', 'tesla',
         'polestar', 'genesis', 'alfa-romeo', 'ds-automobiles', 'ineos'),
        'premium',
    ),
    **dict.fromkeys(('porsche', 'maserati', 'lotus'), 'luxury'),
    **dict.fromkeys(
        ('ferrari', 'lamborghini', 'mclaren', 'rolls-royce', 'aston-martin', 'bentley'), 'exotic'
    ),
}  # fmt: skip
ELECTRIC_ONLY_MAKES = frozenset({'tesla', 'polestar', 'byd'})
# Models sold only as EVs (the taxonomy has no powertrain data). Without this a seeded
# "Audi Q6 e-tron" could be petrol, which reads as obviously fake.
ELECTRIC_ONLY_MODELS = frozenset({
    ('audi', 'q4-e-tron'), ('audi', 'q6-e-tron'), ('audi', 'q8-e-tron'), ('audi', 'e-tron-gt'),
    ('bmw', 'i3'), ('bmw', 'i4'), ('bmw', 'i5'), ('bmw', 'i7'), ('bmw', 'ix'),
    ('cupra', 'born'), ('dacia', 'spring'), ('ford', 'mustang-mach-e'), ('honda', 'e-ny1'),
    ('hyundai', 'ioniq-5'), ('hyundai', 'ioniq-6'), ('kia', 'ev3'), ('kia', 'ev6'),
    ('kia', 'ev9'), ('mercedes-benz', 'eqa'), ('mercedes-benz', 'eqb'),
    ('mercedes-benz', 'eqc'), ('mercedes-benz', 'eqe'), ('mercedes-benz', 'eqs'),
    ('mg', 'mg4'), ('nissan', 'leaf'), ('nissan', 'e-nv200'), ('nissan', 'ariya'),
    ('porsche', 'taycan'), ('renault', 'zoe'), ('skoda', 'enyaq'), ('volkswagen', 'id-3'),
    ('volkswagen', 'id-4'), ('volkswagen', 'id-5'), ('volkswagen', 'id-7'),
    ('volkswagen', 'id-buzz'), ('volvo', 'ex30'), ('volvo', 'ex40'), ('volvo', 'ex90'),
    ('jaguar', 'i-pace'), ('toyota', 'bz4x'), ('abarth', '500e'), ('fiat', '500e'),
})  # fmt: skip
BODY_FACTOR = {
    BodyType.HATCHBACK: 0.9, BodyType.SALOON: 1.05, BodyType.ESTATE: 1.05, BodyType.SUV: 1.15,
    BodyType.COUPE: 1.1, BodyType.CONVERTIBLE: 1.1, BodyType.MPV: 1.0, BodyType.PICKUP: 1.2,
    BodyType.VAN: 1.0,
}  # fmt: skip
ENGINE_CC = {
    'budget': (999, 1199, 1332, 1498),
    'mainstream': (999, 1199, 1395, 1498, 1598, 1968, 1995),
    'premium': (1499, 1950, 1984, 1995, 2993),
    'luxury': (2894, 2981, 3996),
    'exotic': (3902, 3996, 6498),
}  # fmt: skip
COLOUR_WEIGHTS = {
    Colour.GREY: 18, Colour.BLACK: 17, Colour.WHITE: 16, Colour.BLUE: 14, Colour.SILVER: 11,
    Colour.RED: 10, Colour.GREEN: 3, Colour.ORANGE: 2, Colour.BROWN: 2, Colour.BEIGE: 1,
    Colour.YELLOW: 1, Colour.GOLD: 1, Colour.PURPLE: 1, Colour.BRONZE: 1, Colour.OTHER: 2,
}  # fmt: skip
STATUS_WEIGHTS = {
    ListingStatus.ACTIVE: 85, ListingStatus.RESERVED: 5, ListingStatus.SOLD: 5, ListingStatus.DRAFT: 5,
}  # fmt: skip
TRIMS = (
    'Base',
    'S',
    'SE',
    'SE L',
    'Sport',
    'GT Line',
    'Titanium',
    'Design',
    'Excellence',
    'Edition',
)

# Neutral words only: no surnames, no place names, nothing that reads like a real firm.
NAME_FIRST = (
    'Amber', 'Birch', 'Cedar', 'Copper', 'Elm', 'Fern', 'Granite', 'Harbour', 'Hazel', 'Ivy',
    'Juniper', 'Larch', 'Maple', 'Meadow', 'Oak', 'Pebble', 'Quartz', 'Rowan', 'Slate', 'Willow',
)  # fmt: skip
NAME_SECOND = ('Lane', 'Gate', 'Field', 'Brook', 'Ridge', 'Vale', 'Court', 'Hill', 'Green', 'Row')
NAME_SUFFIX = ('Demo Motors', 'Demo Cars', 'Demo Autos', 'Demo Car Sales')
# Current-format plates never use I or Q, and never Z in the memory tag; demo plates
# always start with Z (A1), so none can be a real registration.
PLATE_LETTERS = ''.join(c for c in string.ascii_uppercase if c not in 'IQ')
MEMORY_SECOND_LETTERS = PLATE_LETTERS.replace('Z', '')


@dataclass(frozen=True)
class DemoDealer:
    name: str
    slug: str
    postcode: str
    latitude: float
    longitude: float
    region_code: str


@dataclass(frozen=True)
class DemoListing:
    dealer_index: int
    model: CatalogueModel
    status: ListingStatus
    variant: str
    year: int
    registration_date: date
    mileage: int
    price_pence: int
    body_type: str
    fuel_type: str
    transmission: str
    colour: str
    engine_size_cc: int | None
    doors: int
    seats: int
    owners: int
    vrm: str
    description: str
    specs: dict[str, Any]
    published_at: datetime | None
    sold_at: datetime | None


@dataclass(frozen=True)
class DemoDataset:
    dealers: tuple[DemoDealer, ...]
    listings: tuple[DemoListing, ...]


@dataclass(frozen=True)
class SeedReport:
    dealers: int
    listings: int
    statuses: dict[str, int]
    listed: int
    random_seed: int
    invariant_mismatches: int = 0
    mismatches: list[InvariantMismatch] = field(default_factory=list, repr=False)


class DemoSeedError(RuntimeError):
    """The seed cannot run (no taxonomy) or produced rows a real writer would not."""


# --- generation (pure) -----------------------------------------------------------------


def _weighted(rng: random.Random, weights: Mapping[T, float]) -> T:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _dealers(rng: random.Random, count: int, districts: Sequence[District]) -> list[DemoDealer]:
    by_region: dict[str, list[District]] = {}
    for district in districts:
        by_region.setdefault(district.region_code, []).append(district)
    regions = {
        region: weight for region, weight in REGION_POPULATION.items() if region in by_region
    }

    dealers: list[DemoDealer] = []
    names: set[str] = set()
    while len(dealers) < count:
        name = f'{rng.choice(NAME_FIRST)} {rng.choice(NAME_SECOND)} {rng.choice(NAME_SUFFIX)}'
        if name in names:
            name = f'{name} {len(dealers) + 1}'
        names.add(name)
        district = rng.choice(by_region[_weighted(rng, regions)])
        dealers.append(
            DemoDealer(
                name=name,
                slug=slugify(name),
                postcode=district.outward_code,
                latitude=district.latitude,
                longitude=district.longitude,
                region_code=district.region_code,
            )
        )
    return dealers


def _make_weight(model: CatalogueModel) -> float:
    if MAKE_TIER.get(model.make_slug) == 'exotic':
        return EXOTIC_MAKE_WEIGHT
    return MAKE_WEIGHTS.get(model.make_slug, DEFAULT_MAKE_WEIGHT)


def _age_identifier(registered: date) -> str:
    # March-August: the year (19); September-February: the year + 50 (69), where January
    # and February belong to the previous September's series.
    if 3 <= registered.month <= 8:
        return f'{registered.year % 100:02d}'
    year = registered.year if registered.month >= 9 else registered.year - 1
    return f'{year % 100 + 50:02d}'


def demo_plate(rng: random.Random, registered: date) -> str:
    random_letters = ''.join(rng.choice(PLATE_LETTERS) for _ in range(3))
    return f'Z{rng.choice(MEMORY_SECOND_LETTERS)}{_age_identifier(registered)}{random_letters}'


def _fuel(rng: random.Random, model: CatalogueModel, year: int, tier: str) -> FuelType:
    if (
        model.make_slug in ELECTRIC_ONLY_MAKES
        or (model.make_slug, model.model_slug) in ELECTRIC_ONLY_MODELS
    ):
        return FuelType.ELECTRIC
    if tier == 'exotic':
        return FuelType.PETROL
    if year >= 2019:
        weights = {FuelType.PETROL: 48, FuelType.DIESEL: 15, FuelType.HYBRID: 17, FuelType.PLUG_IN_HYBRID: 7, FuelType.ELECTRIC: 13}  # fmt: skip
    elif year >= 2013:
        weights = {FuelType.PETROL: 50, FuelType.DIESEL: 38, FuelType.HYBRID: 8, FuelType.PLUG_IN_HYBRID: 2, FuelType.ELECTRIC: 2}  # fmt: skip
    else:
        weights = {FuelType.PETROL: 55, FuelType.DIESEL: 43, FuelType.HYBRID: 2}
    return _weighted(rng, weights)


def _doors_and_seats(rng: random.Random, body: str) -> tuple[int, int]:
    match body:
        case BodyType.COUPE:
            return 2, 4
        case BodyType.CONVERTIBLE:
            return 2, rng.choice((2, 4))
        case BodyType.HATCHBACK:
            return rng.choice((3, 5, 5, 5)), 5
        case BodyType.MPV:
            return 5, rng.choice((5, 7))
        case BodyType.SUV:
            return 5, rng.choice((5, 5, 5, 7))
        case BodyType.VAN:
            return 4, rng.choice((2, 3))
        case _:
            return 4 if body in (BodyType.SALOON, BodyType.PICKUP) else 5, 5


def _price_pence(rng: random.Random, tier: str, body: str, age: float, mileage: int) -> int:
    new = TIER_PRICE[tier] * BODY_FACTOR[BodyType(body)]
    # Steep first-year drop, then ~12% a year.
    age_factor = 1 - 0.18 * age if age < 1 else 0.82 * 0.88 ** (age - 1)
    expected_mileage = 8_000 * max(age, 0.25)
    mileage_factor = min(1.15, max(0.7, 1 - (mileage - expected_mileage) / 200_000))
    pounds = new * age_factor * mileage_factor * rng.lognormvariate(0, 0.08)
    pounds = min(5_000_000, max(500, pounds))
    return (round(pounds / 50) * 50 - 5) * 100  # x45 / x95, the forecourt habit


def _specs(
    rng: random.Random,
    fuel: FuelType,
    tier: str,
    body: str,
    engine_cc: int | None,
    year: int,
    today: date,
) -> dict[str, Any]:
    electrified = fuel in (FuelType.ELECTRIC, FuelType.PLUG_IN_HYBRID, FuelType.HYBRID)
    pool = [item.code for item in EQUIPMENT if electrified or item.group != EquipmentGroup.ELECTRIC]
    wanted = 6 + 2 * max(0, year - 2008) + rng.randint(-3, 3)
    equipment = sorted(rng.sample(pool, min(len(pool), max(2, wanted))), key=pool.index)
    raw: dict[str, Any] = {
        'equipment': equipment,
        'boot_litres': {'hatchback': 300, 'estate': 600, 'suv': 500, 'mpv': 650}.get(body, 420)
        + rng.randint(-60, 60),
        'insurance_group': min(
            50, {'budget': 8, 'mainstream': 16, 'premium': 30}.get(tier, 45) + rng.randint(-5, 5)
        ),
    }
    if fuel == FuelType.ELECTRIC:
        battery = rng.choice((40, 58, 64, 77, 82, 100))
        raw |= {'battery_kwh': battery, 'range_miles': int(battery * rng.uniform(3.4, 4.0)),
                'power_bhp': rng.randint(150, 450)}  # fmt: skip
    else:
        assert engine_cc is not None
        raw |= {
            'power_bhp': max(60, int(engine_cc * rng.uniform(0.07, 0.12))),
            'mpg_combined': round(rng.uniform(30, 70 if fuel != FuelType.PETROL else 55), 1),
            'co2_g_km': rng.randint(90, 220),
        }
    if today.year - year >= 3:
        raw['mot_expiry'] = (today + timedelta(days=rng.randint(10, 360))).isoformat()
    stored, _ = dump_specs(parse_specs(raw))
    return stored


def _listing(
    rng: random.Random,
    dealer_index: int,
    model: CatalogueModel,
    today: date,
    now: datetime,
    plates: set[str],
) -> DemoListing:
    tier = MAKE_TIER.get(model.make_slug, 'mainstream')
    age = rng.triangular(0.1, MAX_AGE_YEARS, 4)
    registered = today - timedelta(days=int(age * 365.25))
    fuel = _fuel(rng, model, registered.year, tier)
    body = rng.choice(model.body_types)
    automatic = fuel in (FuelType.ELECTRIC, FuelType.HYBRID, FuelType.PLUG_IN_HYBRID) or (
        rng.random() < (0.7 if tier in ('premium', 'luxury', 'exotic') else 0.35)
    )
    engine_cc = None if fuel == FuelType.ELECTRIC else rng.choice(ENGINE_CC[tier])
    doors, seats = _doors_and_seats(rng, body)
    mileage = max(10, round(rng.uniform(7_000, 9_000) * age * rng.gauss(1, 0.2) / 10) * 10)
    trim = rng.choice(TRIMS)
    if engine_cc is None:
        variant = f'{trim} {doors}dr'
    else:
        variant = f'{engine_cc / 1000:.1f} {trim} {doors}dr'

    plate = demo_plate(rng, registered)
    while plate in plates:
        plate = demo_plate(rng, registered)
    plates.add(plate)

    status: ListingStatus = _weighted(rng, STATUS_WEIGHTS)
    published_at = sold_at = None
    if status != ListingStatus.DRAFT:
        published_at = now - timedelta(minutes=rng.randint(60, 90 * 24 * 60))
    if status == ListingStatus.SOLD:
        assert published_at is not None
        sold_at = published_at + (now - published_at) * rng.random()
    owners = min(9, 1 + int(age // 3) + rng.randint(0, 1))
    colour: Colour = _weighted(rng, COLOUR_WEIGHTS)
    description = (
        f'{colour.value.title()} {body.replace("_", " ")} with {mileage:,} miles and '
        f'{owners} previous owner{"s" if owners > 1 else ""}. Demo listing: this car is not '
        'for sale and the dealer is fictional.'
    )
    return DemoListing(
        dealer_index=dealer_index,
        model=model,
        status=status,
        variant=variant,
        year=registered.year,
        registration_date=registered,
        mileage=mileage,
        price_pence=_price_pence(rng, tier, body, age, mileage),
        body_type=body,
        fuel_type=fuel,
        transmission=Transmission.AUTOMATIC if automatic else Transmission.MANUAL,
        colour=colour,
        engine_size_cc=engine_cc,
        doors=doors,
        seats=seats,
        owners=owners,
        vrm=plate,
        description=description,
        specs=_specs(rng, fuel, tier, body, engine_cc, registered.year, today),
        published_at=published_at,
        sold_at=sold_at,
    )


def generate(
    *,
    listings: int,
    random_seed: int,
    districts: Sequence[District],
    models: Sequence[CatalogueModel],
    today: date,
    now: datetime,
) -> DemoDataset:
    """The demo dataset for `random_seed`: same inputs, same output, always."""
    if not models:
        raise DemoSeedError('the taxonomy is empty: run scripts.load_taxonomy first')
    rng = random.Random(random_seed)
    dealers = _dealers(rng, max(1, math.ceil(listings / LISTINGS_PER_DEALER)), districts)
    # Dealer sizes vary: a few big forecourts, many small ones.
    dealer_weights = [rng.lognormvariate(0, 0.6) for _ in dealers]
    model_weights = [_make_weight(model) for model in models]
    plates: set[str] = set()
    rows = []
    for _ in range(listings):
        dealer_index = rng.choices(range(len(dealers)), weights=dealer_weights)[0]
        model = rng.choices(models, weights=model_weights)[0]
        rows.append(_listing(rng, dealer_index, model, today, now, plates))
    return DemoDataset(tuple(dealers), tuple(rows))


# --- writing ---------------------------------------------------------------------------


def _listing_row(listing: DemoListing, dealer_id: Any, dealer: DemoDealer) -> dict[str, Any]:
    """The insert row, with every derived column computed by derive.py (never hand-set)."""
    model = listing.model
    return {
        'id': uuid7(),
        'dealer_id': dealer_id,
        'is_demo': True,
        'status': listing.status,
        'make_id': model.make_id,
        'model_id': model.model_id,
        'variant': listing.variant,
        'year': listing.year,
        'registration_date': listing.registration_date,
        'mileage': listing.mileage,
        'price_pence': listing.price_pence,
        'body_type': listing.body_type,
        'fuel_type': listing.fuel_type,
        'transmission': listing.transmission,
        'colour': listing.colour,
        'engine_size_cc': listing.engine_size_cc,
        'doors': listing.doors,
        'seats': listing.seats,
        'owners': listing.owners,
        'vrm': normalise_vrm(listing.vrm),
        'title': build_title(listing.year, model.make_name, model.model_name, listing.variant),
        'ulez_compliant': derive_ulez(listing.fuel_type, listing.registration_date),
        'description': listing.description,
        'specs': listing.specs,
        'specs_version': 1,
        'latitude': dealer.latitude,
        'longitude': dealer.longitude,
        'published_at': listing.published_at,
        'sold_at': listing.sold_at,
    }


def write_dataset(session: Session, dataset: DemoDataset) -> list[Any]:
    """Insert `dataset` (Core, batches of 1,000) and stamp `listed_at`; returns listing ids."""
    dealer_ids = insert_dealers(
        session,
        [{**asdict(dealer), 'is_demo': True, 'status': 'approved'} for dealer in dataset.dealers],
    )
    rows = [
        _listing_row(
            listing, dealer_ids[listing.dealer_index], dataset.dealers[listing.dealer_index]
        )
        for listing in dataset.listings
    ]
    for start in range(0, len(rows), INSERT_BATCH_SIZE):
        session.execute(insert(Listing), rows[start : start + INSERT_BATCH_SIZE])
    return [row['id'] for row in rows]


def seed_demo(
    session: Session,
    *,
    listings: int = DEFAULT_LISTINGS,
    random_seed: int = DEFAULT_RANDOM_SEED,
    today: date | None = None,
    now: datetime | None = None,
) -> SeedReport:
    """Generate and write demo inventory in the caller's transaction, under the seed lock.

    Raises `DemoSeedError` (and writes nothing once the caller rolls back) if demo data
    already exists, the taxonomy is empty, or any listing fails `verify_listing_invariants`.
    """
    hold_advisory_lock(session, AdvisoryLock.SEED_DEMO)
    if demo_dealers(session):
        # Checked under the lock, so two concurrent runs cannot both pass it.
        raise DemoSeedError('demo data already exists: remove it with --reset first')
    clock = session.scalar(select(func.now())) if now is None else now
    assert clock is not None
    dataset = generate(
        listings=listings,
        random_seed=random_seed,
        districts=all_districts(),
        models=catalogue(session),
        today=today or clock.date(),
        now=clock,
    )
    ids = write_dataset(session, dataset)
    # A seeded listing that was never held has been visible since it was published.
    listed = stamp_listed_at(session, ids, at=Listing.published_at)
    mismatches = verify_listing_invariants(session)
    report = SeedReport(
        dealers=len(dataset.dealers),
        listings=len(ids),
        statuses=dict(sorted(Counter(str(row.status) for row in dataset.listings).items())),
        listed=listed,
        random_seed=random_seed,
        invariant_mismatches=len(mismatches),
        mismatches=mismatches,
    )
    if mismatches:
        raise DemoSeedError(f'{len(mismatches)} seeded rows fail verify_listing_invariants')
    return report


# --- export (determinism checks) --------------------------------------------------------

EXPORT_COLUMNS = (
    'status', 'variant', 'year', 'registration_date', 'mileage', 'price_pence', 'body_type',
    'fuel_type', 'transmission', 'colour', 'engine_size_cc', 'doors', 'seats', 'owners', 'vrm',
    'title', 'ulez_compliant', 'description', 'specs', 'latitude', 'longitude',
)  # fmt: skip


def export_demo(session: Session) -> str:
    """Every demo dealer and listing as CSV, without ids or timestamps, in a stable order.

    Two seeds with the same inputs export byte-identical text (design AC *Seed*).
    """
    dealers = demo_dealers(session)
    slug_by_id = {dealer.id: dealer.slug for dealer in dealers}
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(('dealer', 'name', 'postcode', 'latitude', 'longitude', 'region_code'))
    writer.writerows(
        (d.slug, d.name, d.postcode, d.latitude, d.longitude, d.region_code) for d in dealers
    )
    columns = [getattr(Listing, name) for name in EXPORT_COLUMNS]
    rows = session.execute(
        select(Listing.dealer_id, *columns).where(Listing.is_demo).order_by(Listing.vrm)
    )
    writer.writerow(('dealer', *EXPORT_COLUMNS))
    for dealer_id, *values in rows:
        cells = [json.dumps(v, sort_keys=True) if isinstance(v, dict) else v for v in values]
        writer.writerow((slug_by_id.get(dealer_id, '?'), *cells))
    return output.getvalue()
