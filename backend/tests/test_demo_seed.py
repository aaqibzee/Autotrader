"""Deterministic demo seed (Feature 02 §8, slice 2.7).

Network access is blocked for every test (conftest `block_unstubbed_network`), so these
also prove the seed runs offline. Generation tests need no database: the catalogue comes
from the committed taxonomy CSVs with fixed ids.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from collections.abc import Generator
from datetime import UTC, date, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import SyncSessionLocal, sync_engine
from app.models import Listing
from app.modules.geo.services import Region, all_districts, district_for
from app.modules.listings import demo_seed
from app.modules.listings.demo_seed import (
    ELECTRIC_ONLY_MODELS,
    DemoDataset,
    DemoSeedError,
    export_demo,
    generate,
    seed_demo,
)
from app.modules.listings.services import verify_listing_invariants
from app.modules.listings.visibility import publicly_visible
from app.modules.taxonomy.dataset import read_taxonomy
from app.modules.taxonomy.services import CatalogueModel, load_taxonomy
from scripts import seed_demo as seed_cli

TODAY = date(2026, 10, 1)
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
PLATE = re.compile(r'Z[A-HJ-PR-Y][0-9]{2}[A-HJ-PR-Z]{3}')

# Real UK dealer groups and car retailers: no demo dealer name may contain one.
REAL_DEALER_NAMES = (
    'Arnold Clark', 'Evans Halshaw', 'Lookers', 'Sytner', 'Pendragon', 'Vertu', 'Marshall',
    'Inchcape', 'Stoneacre', 'Jardine', 'Cazoo', 'Cinch', 'CarShop', 'Motorpoint',
    'Big Motoring World', 'Listers', 'Hendy', 'Robins & Day', 'Snows', 'Benfield', 'Bristol Street',
    'Jennings', 'Vindis', 'Group 1', 'JCT600', 'Peter Vardy', 'Swansway', 'Rybrook',
)  # fmt: skip


def _catalogue() -> list[CatalogueModel]:
    data = read_taxonomy()
    makes = {make.slug: make for make in data.makes}
    return sorted(
        (
            CatalogueModel(
                make_id=uuid5(NAMESPACE_URL, f'make:{model.make_slug}'),
                make_slug=model.make_slug,
                make_name=makes[model.make_slug].name,
                make_is_popular=makes[model.make_slug].is_popular,
                model_id=uuid5(NAMESPACE_URL, f'model:{model.make_slug}/{model.slug}'),
                model_slug=model.slug,
                model_name=model.name,
                body_types=model.body_types,
            )
            for model in data.models
        ),
        key=lambda model: (model.make_slug, model.model_slug),
    )


CATALOGUE = _catalogue()


def _generate(listings: int, random_seed: int = 42, **kwargs: Any) -> DemoDataset:
    return generate(
        listings=listings,
        random_seed=random_seed,
        districts=all_districts(),
        models=CATALOGUE,
        today=TODAY,
        now=NOW,
        **kwargs,
    )


@pytest.fixture(scope='module')
def large() -> DemoDataset:
    return _generate(10_000)


# --- generation: deterministic and believable ------------------------------------------


def test_same_seed_same_dataset_different_seed_different_dataset() -> None:
    assert _generate(300) == _generate(300)
    assert _generate(300, random_seed=7) != _generate(300)


def test_dealer_count_is_about_one_per_80_listings() -> None:
    assert len(_generate(5_000).dealers) == 63
    assert len(_generate(1).dealers) == 1


def test_prices_fall_with_age_within_each_popular_make(large: DemoDataset) -> None:
    prices: dict[tuple[str, int], list[int]] = defaultdict(list)
    for listing in large.listings:
        if listing.model.make_is_popular:
            prices[(listing.model.make_slug, TODAY.year - listing.year)].append(listing.price_pence)
    checked = 0
    for make in sorted({make for make, _ in prices}):
        buckets = [prices.get((make, age), []) for age in (1, 5, 10)]
        if min(map(len, buckets)) < 5:
            continue
        one, five, ten = (statistics.median(bucket) for bucket in buckets)
        assert one > five > ten, make
        checked += 1
    assert checked >= 8  # not vacuous


def test_mileage_tracks_age(large: DemoDataset) -> None:
    by_age: dict[int, list[int]] = defaultdict(list)
    for listing in large.listings:
        by_age[TODAY.year - listing.year].append(listing.mileage)
    per_year = statistics.median(statistics.median(by_age[age]) / age for age in range(3, 12))
    assert 6_000 <= per_year <= 10_000


def test_make_mix_follows_the_used_market(large: DemoDataset) -> None:
    counts: dict[str, int] = defaultdict(int)
    for listing in large.listings:
        counts[listing.model.make_slug] += 1
    top = sorted(counts, key=counts.__getitem__, reverse=True)[:5]
    assert 'ford' in top and 'volkswagen' in top
    assert counts.get('ferrari', 0) < counts['ford'] / 50


def test_every_plate_is_a_z_plate_matching_its_registration(large: DemoDataset) -> None:
    plates = [listing.vrm for listing in large.listings]
    assert len(plates) == len(set(plates))
    for listing in large.listings:
        assert PLATE.fullmatch(listing.vrm), listing.vrm
        registered = listing.registration_date
        assert listing.vrm[2:4] == demo_seed._age_identifier(registered)


@pytest.mark.parametrize(
    ('registered', 'identifier'),
    [
        (date(2019, 3, 1), '19'),
        (date(2019, 8, 31), '19'),
        (date(2019, 9, 1), '69'),
        (date(2020, 2, 29), '69'),
        (date(2010, 1, 15), '59'),
        (date(2009, 12, 1), '59'),
    ],
)
def test_age_identifier(registered: date, identifier: str) -> None:
    assert demo_seed._age_identifier(registered) == identifier


def test_dealers_are_fictional_and_sit_on_district_centroids(large: DemoDataset) -> None:
    names = [dealer.name for dealer in large.dealers]
    assert len(names) == len(set(names))
    assert len({dealer.slug for dealer in large.dealers}) == len(names)
    for dealer in large.dealers:
        assert ' Demo ' in f' {dealer.name} '
        lowered = dealer.name.lower()
        assert not any(real.lower() in lowered for real in REAL_DEALER_NAMES), dealer.name
        district = district_for(dealer.postcode)
        assert district is not None and district.outward_code == dealer.postcode  # outward only
        assert (dealer.latitude, dealer.longitude) == (district.latitude, district.longitude)
        assert dealer.region_code != Region.NORTHERN_IRELAND


def test_listings_are_internally_consistent(large: DemoDataset) -> None:
    for listing in large.listings:
        assert 'not for sale' in listing.description
        assert len(listing.description) >= 50  # Feature 05's publish minimum
        assert listing.registration_date <= TODAY
        assert listing.body_type in listing.model.body_types
        assert 10_000 <= listing.price_pence <= 500_000_000
        if listing.fuel_type == 'electric':
            assert listing.engine_size_cc is None and listing.transmission == 'automatic'
        if (listing.model.make_slug, listing.model.model_slug) in ELECTRIC_ONLY_MODELS:
            assert listing.fuel_type == 'electric', listing.model
        if listing.status == 'draft':
            assert listing.published_at is None
        else:
            assert listing.published_at is not None and listing.published_at <= NOW
        if listing.status == 'sold':
            assert listing.sold_at is not None and listing.published_at is not None
            assert listing.published_at <= listing.sold_at <= NOW


def test_electric_only_models_exist_in_the_taxonomy() -> None:
    known = {(model.make_slug, model.model_slug) for model in CATALOGUE}
    assert ELECTRIC_ONLY_MODELS <= known


def test_generation_refuses_an_empty_catalogue() -> None:
    with pytest.raises(DemoSeedError, match='load_taxonomy'):
        generate(
            listings=1, random_seed=1, districts=all_districts(), models=[], today=TODAY, now=NOW
        )


# --- writing: through the real derivation path ------------------------------------------


@pytest.fixture
def session() -> Generator[Session, None, None]:
    """A rolled-back session with the committed taxonomy loaded inside it."""
    with Session(sync_engine) as session:
        try:
            load_taxonomy(session, read_taxonomy())
            yield session
        finally:
            session.rollback()


def _seeded_export(random_seed: int) -> str:
    with Session(sync_engine) as session:
        try:
            load_taxonomy(session, read_taxonomy())
            seed_demo(session, listings=200, random_seed=random_seed, today=TODAY, now=NOW)
            return export_demo(session)
        finally:
            session.rollback()


def test_seeding_500_listings_passes_every_invariant(session: Session) -> None:
    report = seed_demo(session, listings=500, today=TODAY, now=NOW)

    assert (report.dealers, report.listings, report.invariant_mismatches) == (7, 500, 0)
    assert sum(report.statuses.values()) == 500
    assert report.statuses['active'] > 400
    assert verify_listing_invariants(session) == []
    visible = session.execute(
        select(Listing.listed_at, Listing.published_at).where(Listing.is_demo, publicly_visible())
    ).all()
    assert len(visible) == report.listed > 0
    # A seeded listing that was never held has been listed since it was published.
    assert all(listed_at == published_at for listed_at, published_at in visible)
    hidden = session.scalar(
        select(Listing.id).where(
            Listing.is_demo, Listing.listed_at.is_not(None), ~publicly_visible()
        )
    )
    assert hidden is None


def test_two_runs_with_the_same_seed_export_identically() -> None:
    first = _seeded_export(42)
    assert first == _seeded_export(42)
    assert first != _seeded_export(43)
    assert first.count('\n') > 200  # dealers + header + listings: not an empty export


def test_seed_refuses_to_run_twice(session: Session) -> None:
    seed_demo(session, listings=20, today=TODAY, now=NOW)
    with pytest.raises(DemoSeedError, match='--reset'):
        seed_demo(session, listings=20, today=TODAY, now=NOW)


def test_seed_fails_when_a_row_breaks_an_invariant(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Negative proof: a seed whose title derivation drifted must not commit.
    monkeypatch.setattr(demo_seed, 'build_title', lambda *parts: 'Not what derive.py says')
    with pytest.raises(DemoSeedError, match='verify_listing_invariants'):
        seed_demo(session, listings=20, today=TODAY, now=NOW)


# --- the real CLI ---------------------------------------------------------------------


@pytest.fixture
def committed_taxonomy() -> Generator[None, None, None]:
    with SyncSessionLocal.begin() as session:
        load_taxonomy(session, read_taxonomy())
    yield
    with sync_engine.begin() as connection:
        connection.execute(text('DELETE FROM dealers WHERE is_demo'))


def test_cli_seeds_then_refuses_a_second_run(committed_taxonomy: None) -> None:
    assert seed_cli.main(['--listings', '30', '--random-seed', '5']) == 0
    with SyncSessionLocal() as session:
        assert session.scalar(text('SELECT count(*) FROM listings WHERE is_demo')) == 30
    assert seed_cli.main(['--listings', '30']) == 1
    with SyncSessionLocal() as session:
        assert session.scalar(text('SELECT count(*) FROM listings WHERE is_demo')) == 30


def test_cli_rejects_a_non_positive_size() -> None:
    with pytest.raises(SystemExit):
        seed_cli.main(['--listings', '0'])
    with pytest.raises(SystemExit):
        seed_cli.main(['--listings', '10', '--profile', 'perf'])
