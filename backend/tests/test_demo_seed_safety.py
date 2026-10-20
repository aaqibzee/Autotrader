"""Demo seed safety: region scope, reset, production controls (Feature 02 §8-§9, slice 2.8)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
import structlog
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import SyncSessionLocal, sync_engine
from app.models import Dealer, Listing
from app.modules.geo.services import REGION_NAMES, REGION_SHORT_CODES, Region, parse_region
from app.modules.listings.demo_seed import (
    DemoSeedError,
    production_refusal,
    reset_demo,
    seed_demo,
)
from app.modules.taxonomy.dataset import read_taxonomy
from app.modules.taxonomy.services import load_taxonomy
from scripts import seed_demo as seed_cli
from tests.factories.dealers import create_dealer
from tests.factories.listings import create_listing, create_vehicle
from tests.test_demo_seed import NOW, TODAY, _generate

# --- region names ---------------------------------------------------------------------


@pytest.mark.parametrize('region', list(Region))
def test_every_spelling_of_a_region_parses_to_it(region: Region) -> None:
    # Also catches two regions sharing a spelling (the later one would win the lookup).
    for spelling in (
        region.value,
        region.name,
        REGION_NAMES[region],
        REGION_SHORT_CODES[region].lower(),
        REGION_NAMES[region].lower().replace(' ', '-'),
    ):
        assert parse_region(spelling) is region, spelling


@pytest.mark.parametrize('spelling', ['XX', '', 'North', 'E12000010'])
def test_an_unknown_region_is_refused(spelling: str) -> None:
    with pytest.raises(ValueError, match='unknown region'):
        parse_region(spelling)


# --- region-scoped generation (pure) ---------------------------------------------------


def test_a_region_scoped_dataset_has_every_dealer_in_that_region() -> None:
    dataset = _generate(400, region=Region.NORTH_WEST)
    assert len(dataset.dealers) == 5
    assert {dealer.region_code for dealer in dataset.dealers} == {Region.NORTH_WEST}


def test_northern_ireland_cannot_be_seeded() -> None:
    # No NI districts in the bundled file (A11), so there is nowhere to put a dealer.
    with pytest.raises(DemoSeedError, match='Northern Ireland'):
        _generate(10, region=Region.NORTHERN_IRELAND)


def test_a_second_region_avoids_the_firsts_slugs_and_plates() -> None:
    first = _generate(200, region=Region.NORTH_WEST)
    slugs = frozenset(dealer.slug for dealer in first.dealers)
    plates = frozenset(listing.vrm for listing in first.listings)
    # Negative proof: the same seed reuses the first dealer name in another region, so
    # without the taken sets the second run would hit the unique slug.
    naive = _generate(200, region=Region.LONDON)
    assert slugs & {dealer.slug for dealer in naive.dealers}

    second = _generate(200, region=Region.LONDON, taken_slugs=slugs, taken_plates=plates)
    assert not slugs & {dealer.slug for dealer in second.dealers}
    assert not plates & {listing.vrm for listing in second.listings}
    # Still deterministic given the same inputs.
    assert second == _generate(200, region=Region.LONDON, taken_slugs=slugs, taken_plates=plates)


# --- production rules (pure, then through the CLI) ---------------------------------------


@pytest.mark.parametrize(
    ('region', 'confirmed', 'perf', 'refused'),
    [
        (None, False, False, '--region'),
        (None, True, False, '--region'),
        (Region.NORTH_WEST, False, False, '--confirm-production'),
        (Region.NORTH_WEST, True, True, 'perf'),
        (Region.NORTH_WEST, True, False, None),
    ],
)
def test_production_refusal(
    region: Region | None, confirmed: bool, perf: bool, refused: str | None
) -> None:
    reason = production_refusal(
        environment='production', region=region, confirmed=confirmed, perf=perf
    )
    assert (reason is None) if refused is None else (refused in (reason or ''))


@pytest.mark.parametrize('environment', ['local', 'staging'])
def test_only_production_is_restricted(environment: str) -> None:
    assert (
        production_refusal(environment=environment, region=None, confirmed=False, perf=True) is None
    )


class _DatabaseTouched(Exception):
    pass


class _NoDatabase:
    """Stands in for `SyncSessionLocal`: any attempt to open a session fails the test."""

    def begin(self) -> Any:
        raise _DatabaseTouched

    def __call__(self) -> Any:
        raise _DatabaseTouched


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> structlog.testing.CapturingLogger:
    monkeypatch.setattr(seed_cli.settings, 'ENVIRONMENT', 'production')
    monkeypatch.setattr(seed_cli, 'SyncSessionLocal', _NoDatabase())
    captured = structlog.testing.CapturingLogger()
    monkeypatch.setattr(seed_cli, 'logger', captured)
    return captured


@pytest.mark.parametrize(
    'argv',
    [
        [],
        ['--listings', '100'],
        ['--region', 'NW'],
        ['--confirm-production'],
        ['--profile', 'perf', '--region', 'NW', '--confirm-production'],
        ['--reset'],
        ['--reset', '--confirm-production'],
        ['--reset', '--region', 'NW'],
    ],
)
def test_production_refuses_before_touching_the_database(
    production: structlog.testing.CapturingLogger, argv: list[str]
) -> None:
    assert seed_cli.main(argv) == 2
    [call] = production.calls
    assert call.args == ('demo_seed_refused',)
    assert call.kwargs['environment'] == 'production'
    assert call.kwargs['operator'] and call.kwargs['host']


@pytest.mark.parametrize(
    'argv',
    [
        ['--region', 'NW', '--confirm-production'],
        ['--reset', '--region', 'NW', '--confirm-production'],
    ],
)
def test_a_confirmed_regional_production_run_goes_ahead(
    production: structlog.testing.CapturingLogger, argv: list[str]
) -> None:
    # Negative proof for the test above: the stand-in does catch a database session.
    with pytest.raises(_DatabaseTouched):
        seed_cli.main(argv)


def test_reset_takes_no_size() -> None:
    for argv in (['--reset', '--listings', '10'], ['--reset', '--profile', 'perf']):
        with pytest.raises(SystemExit):
            seed_cli.main(argv)


def test_an_unknown_region_flag_is_a_usage_error() -> None:
    with pytest.raises(SystemExit):
        seed_cli.main(['--region', 'Atlantis'])


# --- reset against the database ----------------------------------------------------------


def _count(model: type[Dealer | Listing], *where: Any) -> int:
    with SyncSessionLocal() as session:
        return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


@pytest.fixture
def seeded() -> Generator[structlog.testing.CapturingLogger, None, None]:
    """Committed taxonomy; everything demo, and the real dealer and vehicle, removed after."""
    with SyncSessionLocal.begin() as session:
        load_taxonomy(session, read_taxonomy())
    captured = structlog.testing.CapturingLogger()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(seed_cli, 'logger', captured)
        yield captured
    with sync_engine.begin() as connection:
        connection.execute(text('DELETE FROM dealers WHERE is_demo'))
        connection.execute(text("DELETE FROM dealers WHERE slug LIKE 'example-motors-%'"))
        connection.execute(
            text(
                "DELETE FROM vehicle_models WHERE make_id IN (SELECT id FROM makes WHERE slug LIKE 'vauxhall-%')"
            )
        )
        connection.execute(text("DELETE FROM makes WHERE slug LIKE 'vauxhall-%'"))


def test_reset_by_region_removes_only_demo_rows_there(
    seeded: structlog.testing.CapturingLogger,
) -> None:
    # Two regions seeded with the same random seed: the second avoids the first's slugs.
    assert seed_cli.main(['--listings', '60', '--region', 'NW']) == 0
    assert seed_cli.main(['--listings', '60', '--region', 'LON']) == 0
    assert seed_cli.main(['--listings', '10', '--region', 'NW']) == 1  # NW already seeded
    in_nw = Dealer.region_code == Region.NORTH_WEST
    in_london = Dealer.region_code == Region.LONDON
    assert _count(Dealer, Dealer.is_demo, in_nw) == 1
    assert _count(Listing, Listing.is_demo) == 120

    # A real dealer and listing in the same region (Manchester, M1).
    with SyncSessionLocal.begin() as session:
        dealer = create_dealer(session, outward_code='M1', is_demo=False)
        real = create_listing(session, dealer, create_vehicle(session, make='Vauxhall'))
        real_id, real_dealer_id = real.id, dealer.id
    assert dealer.region_code == Region.NORTH_WEST

    assert seed_cli.main(['--reset', '--region', 'NW']) == 0

    assert _count(Dealer, Dealer.is_demo, in_nw) == 0
    assert _count(Dealer, Dealer.is_demo, in_london) == 1
    assert _count(Listing, Listing.is_demo) == 60  # London's survive
    assert _count(Listing, Listing.id == real_id) == 1
    assert _count(Dealer, Dealer.id == real_dealer_id) == 1

    seeded_call, london_call, refused_call, reset_call = seeded.calls
    assert (seeded_call.args, refused_call.args) == (('demo_seeded',), ('demo_seed_failed',))
    assert 'North West' in refused_call.kwargs['reason']
    assert reset_call.args == ('demo_reset',)
    assert (reset_call.kwargs['dealers'], reset_call.kwargs['listings']) == (1, 60)
    assert reset_call.kwargs['flags']['region'] == Region.NORTH_WEST
    assert reset_call.kwargs['flags']['reset'] is True
    assert reset_call.kwargs['operator'] and reset_call.kwargs['host']
    assert london_call.kwargs['flags']['random_seed'] == seeded_call.kwargs['flags']['random_seed']

    # Idempotent: a second reset deletes nothing and fails nothing.
    assert seed_cli.main(['--reset', '--region', 'NW']) == 0
    assert (seeded.calls[-1].kwargs['dealers'], seeded.calls[-1].kwargs['listings']) == (0, 0)

    # An unscoped reset removes every demo row, and still no real one.
    assert seed_cli.main(['--reset']) == 0
    assert _count(Listing, Listing.is_demo) == 0
    assert _count(Listing, Listing.id == real_id) == 1


@pytest.fixture
def session() -> Generator[Session, None, None]:
    with Session(sync_engine) as session:
        try:
            load_taxonomy(session, read_taxonomy())
            yield session
        finally:
            session.rollback()


def test_an_unscoped_seed_refuses_while_any_region_has_demo_data(session: Session) -> None:
    seed_demo(session, listings=20, region=Region.SCOTLAND, today=TODAY, now=NOW)
    with pytest.raises(DemoSeedError, match='already exists: remove'):
        seed_demo(session, listings=20, today=TODAY, now=NOW)
    # Another region is fine.
    seed_demo(session, listings=20, region=Region.WALES, today=TODAY, now=NOW)


def test_reset_on_an_empty_scope_deletes_nothing(session: Session) -> None:
    seed_demo(session, listings=20, region=Region.WALES, today=TODAY, now=NOW)
    report = reset_demo(session, Region.SCOTLAND)
    assert (report.dealers, report.listings) == (0, 0)
    assert reset_demo(session, Region.WALES).listings == 20
