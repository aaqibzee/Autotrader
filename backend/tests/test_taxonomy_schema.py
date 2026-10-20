from __future__ import annotations

from collections.abc import Generator
from enum import StrEnum

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from psycopg import errors as pg_errors
from sqlalchemy import Column, Connection, MetaData, Table, Text, text
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.db.checks import EnumCheck, enum_check, enum_checks, replace_enum_check
from app.db.session import sync_engine
from app.db.uuid7 import uuid7
from tests.helpers.enum_checks import enum_check_drift


@pytest.fixture
def connection() -> Generator[Connection, None, None]:
    """A connection whose writes are all rolled back at the end of the test."""
    with sync_engine.connect() as conn:
        transaction = conn.begin()
        try:
            yield conn
        finally:
            transaction.rollback()


# --- enum CHECK drift ---------------------------------------------------------------


def test_every_enum_check_matches_its_enum(connection: Connection) -> None:
    checks = list(enum_checks(Base.metadata))
    # Guard against walking zero constraints and passing vacuously.
    assert ('vehicle_models', 'body_types') in {(c.table, c.column) for c in checks}
    assert enum_check_drift(connection, checks) == []


class _Shade(StrEnum):
    LIGHT = 'light'
    DARK = 'dark'


def test_drift_check_fails_on_a_mismatched_check(connection: Connection) -> None:
    connection.execute(
        text(
            'CREATE TABLE drift_probe (shade text, shades text[], '
            "CONSTRAINT ck_drift_probe_shade CHECK (shade IN ('light', 'dim')), "
            "CONSTRAINT ck_drift_probe_shades CHECK (shades <@ ARRAY['light']::text[]))"
        )
    )
    metadata = MetaData()
    Table(
        'drift_probe',
        metadata,
        Column('shade', Text),
        Column('shades', Text),
        Column('hue', Text),
        enum_check('shade', _Shade),
        enum_check('shades', _Shade, array=True),
        enum_check('hue', _Shade),
    )

    problems = enum_check_drift(connection, enum_checks(metadata))

    assert problems == [
        'ck_drift_probe_hue: missing from the database',
        "ck_drift_probe_shade: database allows ['dim', 'light'], _Shade has ['dark', 'light']",
        "ck_drift_probe_shades: database allows ['light'], _Shade has ['dark', 'light']",
    ]


# --- the database refuses malformed taxonomy rows -----------------------------------


def _insert_make(connection: Connection, slug: str) -> str:
    make_id = str(uuid7())
    connection.execute(
        text('INSERT INTO makes (id, name, slug) VALUES (:id, :name, :slug)'),
        {'id': make_id, 'name': slug.title(), 'slug': slug},
    )
    return make_id


def _insert_model(
    connection: Connection, make_id: str, slug: str, body_types: list[str] | None = None
) -> str:
    model_id = str(uuid7())
    connection.execute(
        text(
            'INSERT INTO vehicle_models (id, make_id, name, slug, body_types) '
            'VALUES (:id, :make_id, :name, :slug, :body_types)'
        ),
        {
            'id': model_id,
            'make_id': make_id,
            'name': slug.title(),
            'slug': slug,
            'body_types': body_types or ['hatchback'],
        },
    )
    return model_id


def _insert_make_alias(connection: Connection, make_id: str, alias: str) -> None:
    connection.execute(
        text('INSERT INTO make_aliases (id, alias, make_id) VALUES (:id, :alias, :make_id)'),
        {'id': str(uuid7()), 'alias': alias, 'make_id': make_id},
    )


def _insert_model_alias(connection: Connection, model_id: str, alias: str) -> None:
    connection.execute(
        text('INSERT INTO model_aliases (id, alias, model_id) VALUES (:id, :alias, :model_id)'),
        {'id': str(uuid7()), 'alias': alias, 'model_id': model_id},
    )


def test_well_formed_taxonomy_rows_are_accepted(connection: Connection) -> None:
    # The baseline every rejection case below differs from by exactly one value.
    make_id = _insert_make(connection, 'alfa-romeo')
    model_id = _insert_model(connection, make_id, 'giulia', ['saloon', 'estate'])
    _insert_make_alias(connection, make_id, 'ALFA')
    _insert_model_alias(connection, model_id, 'GIULIAQV')
    count = connection.execute(text('SELECT count(*) FROM vehicle_models')).scalar_one()
    assert count >= 1


@pytest.mark.parametrize(
    ('case', 'constraint'),
    [
        ('make slug with upper case', 'ck_makes_slug_format'),
        ('make slug with a space', 'ck_makes_slug_format'),
        ('make slug with a trailing hyphen', 'ck_makes_slug_format'),
        ('make slug with a double hyphen', 'ck_makes_slug_format'),
        ('make slug with an accent', 'ck_makes_slug_format'),
        ('duplicate make slug', 'uq_makes_slug'),
        ('model slug with underscore', 'ck_vehicle_models_slug_format'),
        ('duplicate model slug within a make', 'uq_vehicle_models_make_id_slug'),
        ('unknown body type', 'ck_vehicle_models_body_types'),
        ('one bad body type among good ones', 'ck_vehicle_models_body_types'),
        ('lower-case make alias', 'ck_make_aliases_alias_normalised'),
        ('make alias with a space', 'ck_make_aliases_alias_normalised'),
        ('make alias with a hyphen', 'ck_make_aliases_alias_normalised'),
        ('mixed-case model alias', 'ck_model_aliases_alias_normalised'),
        ('model alias with an accent', 'ck_model_aliases_alias_normalised'),
        ('make alias mapped twice', 'uq_make_aliases_alias'),
    ],
)
def test_database_refuses_malformed_taxonomy_rows(
    connection: Connection, case: str, constraint: str
) -> None:
    make_id = _insert_make(connection, 'ford')
    model_id = _insert_model(connection, make_id, 'fiesta')
    _insert_make_alias(connection, make_id, 'FORDMOTOR')
    other_make_id = _insert_make(connection, 'vauxhall')

    violations = {
        'make slug with upper case': lambda: _insert_make(connection, 'Skoda'),
        'make slug with a space': lambda: _insert_make(connection, 'land rover'),
        'make slug with a trailing hyphen': lambda: _insert_make(connection, 'mini-'),
        'make slug with a double hyphen': lambda: _insert_make(connection, 'rolls--royce'),
        'make slug with an accent': lambda: _insert_make(connection, 'citroën'),
        'duplicate make slug': lambda: _insert_make(connection, 'ford'),
        'model slug with underscore': lambda: _insert_model(connection, make_id, 'focus_st'),
        'duplicate model slug within a make': lambda: _insert_model(connection, make_id, 'fiesta'),
        'unknown body type': lambda: _insert_model(connection, make_id, 'kuga', ['crossover']),
        'one bad body type among good ones': lambda: _insert_model(
            connection, make_id, 'puma', ['suv', 'hatchback', 'Hatchback']
        ),
        'lower-case make alias': lambda: _insert_make_alias(connection, make_id, 'forduk'),
        'make alias with a space': lambda: _insert_make_alias(connection, make_id, 'FORD UK'),
        'make alias with a hyphen': lambda: _insert_make_alias(connection, make_id, 'FORD-UK'),
        'mixed-case model alias': lambda: _insert_model_alias(connection, model_id, 'FiestaST'),
        'model alias with an accent': lambda: _insert_model_alias(connection, model_id, 'FIËSTA'),
        'make alias mapped twice': lambda: _insert_make_alias(
            connection, other_make_id, 'FORDMOTOR'
        ),
    }

    savepoint = connection.begin_nested()
    with pytest.raises(IntegrityError) as raised:
        violations[case]()
    savepoint.rollback()

    assert isinstance(raised.value.orig, pg_errors.IntegrityError)
    assert raised.value.orig.diag.constraint_name == constraint


def test_same_model_slug_is_allowed_under_different_makes(connection: Connection) -> None:
    _insert_model(connection, _insert_make(connection, 'make-one'), 'one')
    _insert_model(connection, _insert_make(connection, 'make-two'), 'one')


# --- replace_enum_check (zero-downtime CHECK swap) ----------------------------------


class _ShadeV2(StrEnum):
    LIGHT = 'light'
    DARK = 'dark'
    PASTEL = 'pastel'


class _ShadeNarrow(StrEnum):
    LIGHT = 'light'


@pytest.fixture
def probe_table() -> Generator[str, None, None]:
    """A committed scratch table: the helper commits mid-way, so no outer rollback."""
    name = 'enum_swap_probe'
    with sync_engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {name}'))
        conn.execute(
            text(
                f'CREATE TABLE {name} (shade text, '
                f"CONSTRAINT ck_{name}_shade CHECK (shade IN ('light', 'dark')))"
            )
        )
        conn.execute(text(f"INSERT INTO {name} VALUES ('dark')"))
    try:
        yield name
    finally:
        with sync_engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS {name}'))


def _run_migration_step(step: object) -> None:
    """Run `step` the way a migration body runs, under a real Alembic context."""
    with sync_engine.connect() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context), context.begin_transaction():
            step()  # type: ignore[operator]


def _probe_checks(table: str, enum: type[StrEnum]) -> list[EnumCheck]:
    return [EnumCheck(table=table, column='shade', enum=enum, array=False)]


def test_replace_enum_check_widens_the_allowed_values(probe_table: str) -> None:
    _run_migration_step(lambda: replace_enum_check(probe_table, 'shade', _ShadeV2))

    with sync_engine.begin() as conn:
        conn.execute(text(f"INSERT INTO {probe_table} VALUES ('pastel')"))
        assert enum_check_drift(conn, _probe_checks(probe_table, _ShadeV2)) == []


def test_replace_enum_check_leaves_an_unvalidated_check_when_existing_rows_violate(
    probe_table: str,
) -> None:
    # The existing 'dark' row is outside the narrower enum, so VALIDATE must fail...
    with pytest.raises(IntegrityError):
        _run_migration_step(lambda: replace_enum_check(probe_table, 'shade', _ShadeNarrow))

    # ...while the NOT VALID constraint, committed before it, still guards new writes,
    # and the drift test reports it rather than passing.
    with sync_engine.begin() as conn:
        assert enum_check_drift(conn, _probe_checks(probe_table, _ShadeNarrow)) == [
            f'ck_{probe_table}_shade: NOT VALID (existing rows were never checked)'
        ]
    with pytest.raises(IntegrityError), sync_engine.begin() as conn:
        conn.execute(text(f"INSERT INTO {probe_table} VALUES ('dark')"))
