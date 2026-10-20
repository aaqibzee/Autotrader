"""`dealers` and `listings` schema: the database refuses contradictory rows (Feature 02 slice 2.4)."""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from psycopg import errors as pg_errors
from sqlalchemy import ColumnElement, Connection, Index, MetaData, Select, and_, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex

from app.db.base import Base
from app.db.checks import enum_checks
from app.db.session import sync_engine
from app.db.uuid7 import uuid7
from app.models import Dealer, Listing
from app.modules.listings.visibility import publicly_visible
from tests.helpers.enum_checks import enum_check_drift

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def connection() -> Generator[Connection, None, None]:
    """A connection whose writes are all rolled back at the end of the test."""
    with sync_engine.connect() as conn:
        transaction = conn.begin()
        try:
            yield conn
        finally:
            transaction.rollback()


def _insert(connection: Connection, table: str, row: dict[str, Any]) -> None:
    columns = ', '.join(row)
    values = ', '.join(f'CAST(:{key} AS jsonb)' if key == 'specs' else f':{key}' for key in row)
    connection.execute(text(f'INSERT INTO {table} ({columns}) VALUES ({values})'), row)


def _make_and_model(connection: Connection) -> tuple[str, str]:
    suffix = uuid7().hex[-12:]
    make_id, model_id = str(uuid7()), str(uuid7())
    _insert(connection, 'makes', {'id': make_id, 'name': 'Ford', 'slug': f'ford-{suffix}'})
    _insert(
        connection,
        'vehicle_models',
        {'id': model_id, 'make_id': make_id, 'name': 'Fiesta', 'slug': 'fiesta'},
    )
    return make_id, model_id


def _dealer(connection: Connection, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        'id': str(uuid7()),
        'name': 'Northgate Example Motors',
        'slug': f'northgate-example-motors-{uuid7().hex[-12:]}',
        'postcode': 'M1',
        'latitude': 53.477,
        'longitude': -2.237,
        'region_code': 'E12000002',
        'status': 'approved',
        'is_demo': True,
    }
    row.update(overrides)
    _insert(connection, 'dealers', row)
    return row


def _active_listing(dealer: dict[str, Any], make_id: str, model_id: str) -> dict[str, Any]:
    """A complete, publicly visible listing; each rejection case changes one thing."""
    return {
        'id': str(uuid7()),
        'dealer_id': dealer['id'],
        'is_demo': dealer['is_demo'],
        'status': 'active',
        'moderation_status': 'clear',
        'make_id': make_id,
        'model_id': model_id,
        'variant': '1.0 EcoBoost ST-Line 5dr',
        'year': 2019,
        'registration_date': date(2019, 3, 1),
        'mileage': 42_000,
        'price_pence': 1_099_500,
        'body_type': 'hatchback',
        'fuel_type': 'petrol',
        'transmission': 'manual',
        'colour': 'blue',
        'engine_size_cc': 999,
        'doors': 5,
        'seats': 5,
        'owners': 2,
        'vrm': 'ZA19KXR',
        'title': '2019 Ford Fiesta 1.0 EcoBoost ST-Line 5dr',
        'ulez_compliant': True,
        'description': 'One careful owner.',
        'specs': '{}',
        'latitude': 53.477,
        'longitude': -2.237,
        'published_at': NOW,
        'listed_at': NOW,
    }


def _constraint_violated(action: Callable[[], object], connection: Connection) -> str:
    savepoint = connection.begin_nested()
    with pytest.raises(IntegrityError) as raised:
        action()
    savepoint.rollback()
    assert isinstance(raised.value.orig, pg_errors.IntegrityError)
    name = raised.value.orig.diag.constraint_name
    assert name is not None
    return name


# --- enum CHECK drift covers the new tables ------------------------------------------


def test_enum_drift_covers_dealers_and_listings(connection: Connection) -> None:
    checks = list(enum_checks(Base.metadata))
    covered = {(c.table, c.column) for c in checks}
    assert {
        ('dealers', 'status'),
        ('dealers', 'region_code'),
        ('listings', 'status'),
        ('listings', 'moderation_status'),
        ('listings', 'body_type'),
        ('listings', 'fuel_type'),
        ('listings', 'transmission'),
        ('listings', 'colour'),
    } <= covered
    assert enum_check_drift(connection, checks) == []


# --- well-formed rows are accepted ---------------------------------------------------


def test_well_formed_rows_are_accepted(connection: Connection) -> None:
    make_id, model_id = _make_and_model(connection)
    dealer = _dealer(connection)
    _insert(connection, 'listings', _active_listing(dealer, make_id, model_id))
    # A bare draft (Feature 05 autosave) needs nothing but its dealer.
    _insert(
        connection,
        'listings',
        {'id': str(uuid7()), 'dealer_id': dealer['id'], 'is_demo': True, 'status': 'draft'},
    )
    # Full postcode, no coordinates (no offline fallback, 02 A11), no region.
    _dealer(connection, postcode='BT1 1AA', latitude=None, longitude=None, region_code=None)
    count = connection.execute(
        text('SELECT count(*) FROM listings WHERE dealer_id = :id'), {'id': dealer['id']}
    ).scalar_one()
    assert count == 2


# --- the database refuses contradictory listings -------------------------------------

LISTING_VIOLATIONS: list[tuple[str, dict[str, Any], str]] = [
    ('zero price', {'price_pence': 0}, 'ck_listings_price_pence_range'),
    ('price over £5m', {'price_pence': 500_000_001}, 'ck_listings_price_pence_range'),
    ('negative mileage', {'mileage': -1}, 'ck_listings_mileage_range'),
    ('year 1899', {'year': 1899}, 'ck_listings_year_range'),
    ('8 doors', {'doors': 8}, 'ck_listings_doors_range'),
    ('10 seats', {'seats': 10}, 'ck_listings_seats_range'),
    ('engine over 10 litres', {'engine_size_cc': 10_001}, 'ck_listings_engine_size_cc_range'),
    ('negative owners', {'owners': -1}, 'ck_listings_owners_range'),
    ('negative photo count', {'photo_count': -1}, 'ck_listings_photo_count_range'),
    ('steam fuel', {'fuel_type': 'steam'}, 'ck_listings_fuel_type'),
    ('unknown body type', {'body_type': 'crossover'}, 'ck_listings_body_type'),
    ('unknown transmission', {'transmission': 'cvt'}, 'ck_listings_transmission'),
    ('unknown colour', {'colour': 'teal'}, 'ck_listings_colour'),
    ('unknown status', {'status': 'deleted'}, 'ck_listings_status'),
    ('unknown moderation', {'moderation_status': 'flagged'}, 'ck_listings_moderation_status'),
    ('description over 5,000', {'description': 'x' * 5_001}, 'ck_listings_description_length'),
    ('lower-case VRM', {'vrm': 'za19kxr'}, 'ck_listings_vrm_normalised'),
    ('VRM with a space', {'vrm': 'ZA1 KXR'}, 'ck_listings_vrm_normalised'),
    ('one-character VRM', {'vrm': 'Z'}, 'ck_listings_vrm_normalised'),
    ('specs not an object', {'specs': '[]'}, 'ck_listings_specs_object'),
    ('specs version 0', {'specs_version': 0}, 'ck_listings_specs_version_range'),
    ('latitude only', {'longitude': None}, 'ck_listings_coordinates_paired'),
    ('latitude 91', {'latitude': 91.0}, 'ck_listings_latitude_range'),
    ('longitude 181', {'longitude': 181.0}, 'ck_listings_longitude_range'),
    (
        'archived without archived_at',
        {'status': 'archived'},
        'ck_listings_archived_iff_archived_at',
    ),
    ('archived_at while active', {'archived_at': NOW}, 'ck_listings_archived_iff_archived_at'),
    ('sold without sold_at', {'status': 'sold'}, 'ck_listings_sold_has_sold_at'),
    (
        'active without published_at',
        {'published_at': None, 'listed_at': None},
        'ck_listings_published_has_published_at',
    ),
    (
        'listed_at without published_at',
        {'status': 'draft', 'published_at': None},
        'ck_listings_listed_has_published_at',
    ),
    # A12: only a draft may lack what the publish validator requires.
    ('active without price', {'price_pence': None}, 'ck_listings_publish_complete'),
    ('active without mileage', {'mileage': None}, 'ck_listings_publish_complete'),
    (
        'reserved without registration date',
        {'status': 'reserved', 'registration_date': None},
        'ck_listings_publish_complete',
    ),
    (
        'sold without a model',
        {'status': 'sold', 'sold_at': NOW, 'model_id': None},
        'ck_listings_publish_complete',
    ),
    ('active without ULEZ derived', {'ulez_compliant': None}, 'ck_listings_publish_complete'),
    ('active with an empty title', {'title': ''}, 'ck_listings_publish_complete'),
]


@pytest.mark.parametrize(
    ('change', 'constraint'),
    [(change, constraint) for _, change, constraint in LISTING_VIOLATIONS],
    ids=[case for case, _, _ in LISTING_VIOLATIONS],
)
def test_database_refuses_contradictory_listings(
    connection: Connection, change: dict[str, Any], constraint: str
) -> None:
    make_id, model_id = _make_and_model(connection)
    dealer = _dealer(connection)
    row = {**_active_listing(dealer, make_id, model_id), **change}
    assert _constraint_violated(lambda: _insert(connection, 'listings', row), connection) == (
        constraint
    )


def test_title_over_160_characters_is_refused(connection: Connection) -> None:
    make_id, model_id = _make_and_model(connection)
    row = {**_active_listing(_dealer(connection), make_id, model_id), 'title': 'x' * 161}
    savepoint = connection.begin_nested()
    with pytest.raises(Exception, match='value too long'):
        _insert(connection, 'listings', row)
    savepoint.rollback()


def test_incomplete_drafts_and_archived_drafts_are_allowed(connection: Connection) -> None:
    make_id, model_id = _make_and_model(connection)
    dealer = _dealer(connection)
    for status, extra in (('draft', {}), ('archived', {'archived_at': NOW})):
        row = {
            **_active_listing(dealer, make_id, model_id),
            'status': status,
            'price_pence': None,
            'mileage': None,
            'registration_date': None,
            'ulez_compliant': None,
            'title': '',
            'published_at': None,
            'listed_at': None,
            **extra,
        }
        _insert(connection, 'listings', row)


def test_model_must_belong_to_the_listings_make(connection: Connection) -> None:
    make_id, _ = _make_and_model(connection)
    _, other_model_id = _make_and_model(connection)
    row = _active_listing(_dealer(connection), make_id, other_model_id)
    assert (
        _constraint_violated(lambda: _insert(connection, 'listings', row), connection)
        == 'fk_listings_make_id_vehicle_models'
    )


@pytest.mark.parametrize('dealer_is_demo', [True, False])
def test_listing_is_demo_must_equal_its_dealers(
    connection: Connection, dealer_is_demo: bool
) -> None:
    make_id, model_id = _make_and_model(connection)
    dealer = _dealer(connection, is_demo=dealer_is_demo)
    row = {**_active_listing(dealer, make_id, model_id), 'is_demo': not dealer_is_demo}
    assert (
        _constraint_violated(lambda: _insert(connection, 'listings', row), connection)
        == 'fk_listings_dealer_id_dealers'
    )


# --- the database refuses contradictory dealers --------------------------------------

DEALER_VIOLATIONS: list[tuple[str, dict[str, Any], str]] = [
    ('lower-case postcode', {'postcode': 'm1'}, 'ck_dealers_postcode_format'),
    ('postcode without its space', {'postcode': 'SW1A1AA'}, 'ck_dealers_postcode_format'),
    ('not a postcode', {'postcode': 'HELLO'}, 'ck_dealers_postcode_format'),
    ('unknown region', {'region_code': 'E12000010'}, 'ck_dealers_region_code'),
    ('unknown status', {'status': 'active'}, 'ck_dealers_status'),
    ('bad slug', {'slug': 'Northgate Motors'}, 'ck_dealers_slug_format'),
    ('longitude only', {'latitude': None}, 'ck_dealers_coordinates_paired'),
]


@pytest.mark.parametrize(
    ('change', 'constraint'),
    [(change, constraint) for _, change, constraint in DEALER_VIOLATIONS],
    ids=[case for case, _, _ in DEALER_VIOLATIONS],
)
def test_database_refuses_contradictory_dealers(
    connection: Connection, change: dict[str, Any], constraint: str
) -> None:
    assert _constraint_violated(lambda: _dealer(connection, **change), connection) == constraint


def test_dealer_slugs_are_unique(connection: Connection) -> None:
    dealer = _dealer(connection)
    assert (
        _constraint_violated(lambda: _dealer(connection, slug=dealer['slug']), connection)
        == 'uq_dealers_slug'
    )


# --- cascades: every FK onto listings or dealers (design §9, enforced mechanically) ---

_FOREIGN_KEYS_ONTO = text(
    """
    SELECT con.conname, con.conrelid::regclass::text AS from_table, con.confdeltype
    FROM pg_constraint con
    WHERE con.contype = 'f' AND con.confrelid = ANY(CAST(:targets AS regclass[]))
    ORDER BY con.conname
    """
)


def _non_cascading_foreign_keys(connection: Connection) -> list[str]:
    rows = connection.execute(_FOREIGN_KEYS_ONTO, {'targets': ['listings', 'dealers']}).all()
    # Guard against an empty walk passing vacuously.
    assert 'fk_listings_dealer_id_dealers' in {row.conname for row in rows}
    return [f'{row.from_table}.{row.conname}' for row in rows if row.confdeltype != 'c']


def test_every_foreign_key_onto_listings_or_dealers_cascades(connection: Connection) -> None:
    # Demo data is removed per region by deleting demo dealers (slice 2.8); any table that
    # references a listing or dealer without ON DELETE CASCADE would make that reset fail.
    assert _non_cascading_foreign_keys(connection) == []


def test_cascade_check_catches_a_non_cascading_foreign_key(connection: Connection) -> None:
    connection.execute(
        text(
            'CREATE TABLE cascade_probe (id uuid PRIMARY KEY, '
            'listing_id uuid CONSTRAINT fk_cascade_probe_listing REFERENCES listings (id))'
        )
    )
    assert _non_cascading_foreign_keys(connection) == ['cascade_probe.fk_cascade_probe_listing']


def test_deleting_a_dealer_deletes_its_listings(connection: Connection) -> None:
    make_id, model_id = _make_and_model(connection)
    dealer = _dealer(connection)
    _insert(connection, 'listings', _active_listing(dealer, make_id, model_id))
    connection.execute(text('DELETE FROM dealers WHERE id = :id'), {'id': dealer['id']})
    remaining = connection.execute(
        text('SELECT count(*) FROM listings WHERE dealer_id = :id'), {'id': dealer['id']}
    ).scalar_one()
    assert remaining == 0


# --- partial indexes: the predicate in the database is the one in the code ------------

_INDEX_PREDICATE = text(
    """
    SELECT pg_get_expr(i.indpred, i.indrelid)
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    WHERE c.relname = :name
    """
)


def _partial_indexes(metadata: MetaData) -> list[Index]:
    return [
        index
        for table in metadata.sorted_tables
        for index in sorted(table.indexes, key=lambda index: str(index.name))
        if index.dialect_options['postgresql']['where'] is not None
    ]


def partial_index_drift(connection: Connection, indexes: list[Index]) -> list[str]:
    """Indexes whose live predicate differs from the model's, compared as Postgres renders them.

    `alembic check` does not compare partial-index predicates, so a predicate edited in
    the model without a migration would otherwise go unnoticed while queries stop matching
    the index. Each model index is built under a probe name and rolled back.
    """
    problems: list[str] = []
    for index in indexes:
        live = connection.execute(_INDEX_PREDICATE, {'name': index.name}).scalar_one_or_none()
        if live is None:
            problems.append(f'{index.name}: missing from the database')
            continue
        probe_name = f'probe_{uuid7().hex[:16]}'
        ddl = str(CreateIndex(index).compile(dialect=connection.dialect))
        savepoint = connection.begin_nested()
        connection.execute(text(ddl.replace(str(index.name), probe_name, 1)))
        expected = connection.execute(_INDEX_PREDICATE, {'name': probe_name}).scalar_one()
        savepoint.rollback()
        if live != expected:
            problems.append(f'{index.name}: database has {live!r}, model has {expected!r}')
    return problems


def test_partial_index_predicates_match_the_models(connection: Connection) -> None:
    indexes = _partial_indexes(Base.metadata)
    assert {str(index.name) for index in indexes} >= {
        'ix_listings_visible_make_id_model_id_price_pence',
        'ix_listings_visible_listed_at',
        'ix_listings_visible_latitude_longitude',
        'ix_listings_vrm_live',
    }
    assert partial_index_drift(connection, indexes) == []


def test_partial_index_drift_check_catches_a_changed_predicate(connection: Connection) -> None:
    connection.execute(text('DROP INDEX ix_listings_visible_listed_at'))
    connection.execute(
        text(
            'CREATE INDEX ix_listings_visible_listed_at ON listings (listed_at) '
            "WHERE status = 'active'"
        )
    )
    problems = partial_index_drift(connection, _partial_indexes(Base.metadata))
    assert len(problems) == 1
    assert problems[0].startswith(
        "ix_listings_visible_listed_at: database has \"((status)::text = 'active'"
    )


def _generic_plan(connection: Connection, query: Select[Any]) -> str:
    """EXPLAIN of `query` as a prepared statement under a generic plan.

    A generic plan cannot see parameter values, which is exactly when a partial index
    stops matching if the visibility constants were bound rather than inline.
    """
    compiled = query.compile(
        dialect=postgresql.dialect(paramstyle='numeric_dollar'),  # type: ignore[no-untyped-call]
        compile_kwargs={'render_postcompile': True},
    )
    arguments = ', '.join(f"'{compiled.params[name]}'" for name in compiled.positiontup or ())
    connection.execute(text('SET LOCAL enable_seqscan = off'))
    connection.execute(text('SET LOCAL plan_cache_mode = force_generic_plan'))
    connection.exec_driver_sql(f'PREPARE visible_probe AS {compiled}')
    try:
        plan = connection.exec_driver_sql(f'EXPLAIN EXECUTE visible_probe({arguments})')
        return '\n'.join(plan.scalars().all())
    finally:
        connection.exec_driver_sql('DEALLOCATE visible_probe')


def _search(predicate: ColumnElement[bool], make_id: str, model_id: str) -> Select[Any]:
    return (
        select(Listing.id)
        .where(predicate, Listing.make_id == UUID(make_id), Listing.model_id == UUID(model_id))
        .where(Listing.price_pence.between(500_000, 1_000_000))
        .order_by(Listing.price_pence)
    )


def test_publicly_visible_renders_constants_inline() -> None:
    sql = str(
        select(Listing.id)
        .where(publicly_visible())
        .compile(sync_engine, compile_kwargs={'render_postcompile': True})
    )
    assert "IN ('active', 'reserved')" in sql
    assert "moderation_status = 'clear'" in sql


def test_a_query_using_publicly_visible_uses_the_partial_index_under_a_generic_plan(
    connection: Connection,
) -> None:
    make_id, model_id = _make_and_model(connection)
    plan = _generic_plan(connection, _search(publicly_visible(), make_id, model_id))
    assert 'ix_listings_visible_make_id_model_id_price_pence' in plan


def test_the_same_rule_with_bound_parameters_cannot_use_it(connection: Connection) -> None:
    # Negative proof for the inline-constants rule above.
    make_id, model_id = _make_and_model(connection)
    bound = and_(
        Listing.status.in_(['active', 'reserved']),
        Listing.moderation_status == 'clear',
        Listing.archived_at.is_(None),
    )
    plan = _generic_plan(connection, _search(bound, make_id, model_id))
    assert 'ix_listings_visible_' not in plan


# --- UUIDv7 ids ----------------------------------------------------------------------


def test_new_dealer_and_listing_ids_are_uuid7_and_sort_by_creation() -> None:
    created: list[UUID] = []
    with Session(sync_engine) as session:
        dealer = Dealer(name='Example', slug=f'uuid-probe-{uuid7().hex}', postcode='M1')
        session.add(dealer)
        session.flush()
        created.append(dealer.id)
        for _ in range(5):
            # UUIDv7 orders by millisecond; two ids in the same millisecond are unordered.
            time.sleep(0.002)
            listing = Listing(dealer_id=dealer.id, is_demo=False)
            session.add(listing)
            session.flush()
            created.append(listing.id)
        time.sleep(0.002)
        later = Dealer(name='Example', slug=f'uuid-probe-{uuid7().hex}', postcode='M1')
        session.add(later)
        session.flush()
        created.append(later.id)
        session.rollback()

    assert all(identifier.version == 7 for identifier in created)
    assert sorted(created) == created
