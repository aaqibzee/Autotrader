"""load_taxonomy, the resolvers and the CLI, against real Postgres (Feature 02 slice 2.2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Generator
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SyncSessionLocal, sync_engine
from app.db.uuid7 import uuid7
from app.modules.taxonomy import services
from app.modules.taxonomy.dataset import (
    AliasRow,
    MakeRow,
    ModelRow,
    TaxonomyData,
    read_taxonomy,
)
from app.modules.taxonomy.models import Make, VehicleModel
from app.modules.taxonomy.services import (
    LoadReport,
    SlugChangeError,
    TaxonomyDataError,
    load_taxonomy,
    resolve_make,
    resolve_model,
)

_BACKEND = Path(__file__).resolve().parents[1]
_TABLES = 'model_aliases, make_aliases, vehicle_models, makes'


def _clear_taxonomy() -> None:
    with sync_engine.begin() as conn:
        conn.execute(text(f'TRUNCATE {_TABLES} CASCADE'))


@pytest.fixture(autouse=True)
def empty_taxonomy() -> Generator[None, None, None]:
    """Loads commit, so every test starts and ends with empty taxonomy tables."""
    _clear_taxonomy()
    yield
    _clear_taxonomy()


def _load(data: TaxonomyData) -> LoadReport:
    with SyncSessionLocal.begin() as session:
        return load_taxonomy(session, data)


def _snapshot() -> dict[str, list[tuple[Any, ...]]]:
    """Everything a load decides, keyed by slug rather than generated id."""
    with sync_engine.connect() as conn:
        return {
            'makes': conn.execute(
                text('SELECT slug, name, is_popular, is_active FROM makes ORDER BY slug')
            ).all(),
            'models': conn.execute(
                text(
                    'SELECT m.slug, vm.slug, vm.name, vm.body_types, vm.is_active '
                    'FROM vehicle_models vm JOIN makes m ON m.id = vm.make_id ORDER BY 1, 2'
                )
            ).all(),
            'make_aliases': conn.execute(
                text(
                    'SELECT a.alias, m.slug FROM make_aliases a '
                    'JOIN makes m ON m.id = a.make_id ORDER BY 1'
                )
            ).all(),
            'model_aliases': conn.execute(
                text(
                    'SELECT a.alias, m.slug, vm.slug FROM model_aliases a '
                    'JOIN vehicle_models vm ON vm.id = a.model_id '
                    'JOIN makes m ON m.id = vm.make_id ORDER BY 1, 2, 3'
                )
            ).all(),
        }


_FORD = MakeRow('ford', 'Ford', True)
_FIESTA = ModelRow('ford', 'fiesta', 'Fiesta', ('hatchback',))
_FOCUS = ModelRow('ford', 'focus', 'Focus', ('hatchback', 'estate'))


def _small(
    makes: tuple[MakeRow, ...] = (_FORD,),
    models: tuple[ModelRow, ...] = (_FIESTA, _FOCUS),
    aliases: tuple[AliasRow, ...] = (),
) -> TaxonomyData:
    return TaxonomyData(makes=makes, models=models, aliases=aliases)


def _make_id(session: Session, slug: str) -> UUID:
    return session.scalars(select(Make.id).where(Make.slug == slug)).one()


def _model(session: Session, make_slug: str, slug: str) -> VehicleModel:
    return session.scalars(
        select(VehicleModel).where(
            VehicleModel.make_id == _make_id(session, make_slug), VehicleModel.slug == slug
        )
    ).one()


# --- the committed dataset ----------------------------------------------------------


@pytest.fixture(scope='module')
def committed() -> TaxonomyData:
    return read_taxonomy()


def test_second_load_of_the_committed_taxonomy_changes_nothing(
    committed: TaxonomyData,
) -> None:
    rows = len(committed.makes) + len(committed.models)

    first = _load(committed)
    after_first = _snapshot()
    second = _load(committed)

    assert (first.inserted, first.updated, first.deactivated, first.unchanged) == (rows, 0, 0, 0)
    assert first.aliases_added > rows  # every name and slug, plus the explicit aliases
    assert second == LoadReport(unchanged=rows)
    assert _snapshot() == after_first


@pytest.mark.parametrize(
    ('make_slug', 'spellings'),
    [
        ('volkswagen', ['VW', 'VOLKSWAGEN', 'volkswagen', 'Volks wagen', 'vw']),
        ('mercedes-benz', ['MERCEDES-BENZ', 'Mercedes Benz', 'mercedes', 'Mercedes-AMG']),
        ('citroen', ['Citroën', 'CITROEN', 'citroen']),
        ('skoda', ['ŠKODA', 'Skoda']),
        ('land-rover', ['LAND ROVER', 'Land-Rover', 'landrover']),
        ('ssangyong', ['SSANGYONG', 'Ssang Yong', 'KGM']),
    ],
)
def test_make_spellings_resolve_to_one_make(
    committed: TaxonomyData, make_slug: str, spellings: list[str]
) -> None:
    _load(committed)
    with SyncSessionLocal() as session:
        expected = _make_id(session, make_slug)
        assert {resolve_make(session, spelling) for spelling in spellings} == {expected}


def test_model_spellings_resolve_within_their_make(committed: TaxonomyData) -> None:
    _load(committed)
    with SyncSessionLocal() as session:
        ford = _make_id(session, 'ford')
        ka, ka_plus = _model(session, 'ford', 'ka').id, _model(session, 'ford', 'ka-plus').id
        assert resolve_model(session, ford, 'KA') == ka
        assert resolve_model(session, ford, 'Ka+') == ka_plus
        assert resolve_model(session, ford, 'ka plus') == ka_plus
        assert (
            resolve_model(session, ford, 'MACH-E') == _model(session, 'ford', 'mustang-mach-e').id
        )

        mazda = _make_id(session, 'mazda')
        assert resolve_model(session, mazda, '2') == _model(session, 'mazda', 'mazda2').id
        assert resolve_model(session, mazda, 'Mazda 2') == _model(session, 'mazda', 'mazda2').id

        # Same spelling, different makes: resolution is scoped by make.
        seat_leon = resolve_model(session, _make_id(session, 'seat'), 'LEON')
        cupra_leon = resolve_model(session, _make_id(session, 'cupra'), 'LEON')
        assert seat_leon is not None and cupra_leon is not None and seat_leon != cupra_leon
        assert resolve_model(session, ford, 'Leon') is None


@pytest.mark.parametrize('text_input', [None, '', '   ', '---', 'Trabant', 'X' * 200])
def test_unknown_or_empty_input_resolves_to_none(
    committed: TaxonomyData, text_input: str | None
) -> None:
    _load(committed)
    with SyncSessionLocal() as session:
        assert resolve_make(session, text_input) is None
        assert resolve_model(session, _make_id(session, 'ford'), text_input) is None


# --- deactivate, never delete -------------------------------------------------------


def test_removed_model_is_deactivated_not_deleted_and_comes_back() -> None:
    _load(_small(aliases=(AliasRow('ford', 'focus', 'Focus RS'),)))
    with SyncSessionLocal() as session:
        focus_id = _model(session, 'ford', 'focus').id
        ford_id = _make_id(session, 'ford')

    report = _load(_small(models=(_FIESTA,)))

    assert (report.deactivated, report.unchanged, report.inserted) == (1, 2, 0)
    with SyncSessionLocal() as session:
        focus = _model(session, 'ford', 'focus')
        # The same row survives, so anything already referencing its id keeps working.
        assert (focus.id, focus.is_active) == (focus_id, False)
        # A retired model is no longer offered to new lookups.
        assert resolve_model(session, ford_id, 'Focus') is None
        assert resolve_model(session, ford_id, 'Focus RS') is None

    report = _load(_small(aliases=(AliasRow('ford', 'focus', 'Focus RS'),)))

    assert (report.updated, report.inserted) == (1, 0)
    with SyncSessionLocal() as session:
        assert _model(session, 'ford', 'focus').is_active
        assert resolve_model(session, ford_id, 'Focus RS') == focus_id


def test_a_listing_on_a_removed_model_survives_the_load() -> None:
    # Finishes 2.2's "a reference row survives" now that listings exist (slice 2.4).
    _load(_small())
    dealer_id, listing_id = uuid7(), uuid7()
    with SyncSessionLocal.begin() as session:
        focus = _model(session, 'ford', 'focus')
        focus_id, ford_id = focus.id, focus.make_id
        session.execute(
            text(
                "INSERT INTO dealers (id, name, slug, postcode) VALUES (:id, 'Example', :slug, 'M1')"
            ),
            {'id': dealer_id, 'slug': f'loader-probe-{dealer_id.hex}'},
        )
        session.execute(
            text(
                'INSERT INTO listings (id, dealer_id, make_id, model_id) '
                'VALUES (:id, :dealer_id, :make_id, :model_id)'
            ),
            {'id': listing_id, 'dealer_id': dealer_id, 'make_id': ford_id, 'model_id': focus_id},
        )
    try:
        report = _load(_small(models=(_FIESTA,)))

        assert report.deactivated == 1
        with SyncSessionLocal() as session:
            model_id = session.execute(
                text('SELECT model_id FROM listings WHERE id = :id'), {'id': listing_id}
            ).scalar_one()
            assert model_id == focus_id
            assert _model(session, 'ford', 'focus').is_active is False
    finally:
        with sync_engine.begin() as conn:
            conn.execute(text('DELETE FROM dealers WHERE id = :id'), {'id': dealer_id})


def test_removed_make_and_its_models_are_deactivated() -> None:
    vauxhall = MakeRow('vauxhall', 'Vauxhall', True)
    corsa = ModelRow('vauxhall', 'corsa', 'Corsa', ('hatchback',))
    _load(_small(makes=(_FORD, vauxhall), models=(_FIESTA, corsa)))

    report = _load(_small(models=(_FIESTA,)))

    assert report.deactivated == 2
    with SyncSessionLocal() as session:
        assert session.scalars(select(Make.is_active).where(Make.slug == 'vauxhall')).one() is False
        assert resolve_make(session, 'Vauxhall') is None


# --- names change, slugs never do ---------------------------------------------------


def test_renaming_changes_the_name_and_keeps_the_slug() -> None:
    _load(_small())

    report = _load(_small(makes=(MakeRow('ford', 'Ford Motor Company', False),)))

    assert (report.updated, report.inserted) == (1, 0)
    with SyncSessionLocal() as session:
        make = session.scalars(select(Make).where(Make.slug == 'ford')).one()
        assert (make.name, make.is_popular) == ('Ford Motor Company', False)
        assert resolve_make(session, 'Ford Motor Company') == make.id
        assert resolve_make(session, 'ford') == make.id  # the slug still resolves


def test_changing_a_make_slug_is_rejected_and_writes_nothing() -> None:
    _load(_small())
    before = _snapshot()
    moved = _small(
        makes=(MakeRow('ford-uk', 'Ford', True),),
        models=tuple(replace(model, make_slug='ford-uk') for model in (_FIESTA, _FOCUS)),
    )

    with pytest.raises(SlugChangeError, match="from slug 'ford' to 'ford-uk'"):
        _load(moved)
    assert _snapshot() == before


def test_changing_a_model_slug_is_rejected() -> None:
    _load(_small())

    with pytest.raises(SlugChangeError, match="from slug 'focus' to 'focus-mk4'"):
        _load(_small(models=(_FIESTA, replace(_FOCUS, slug='focus-mk4'))))


def test_a_retired_slug_cannot_return_under_a_new_slug() -> None:
    _load(_small())
    _load(_small(models=(_FIESTA,)))  # focus deactivated

    with pytest.raises(SlugChangeError):
        _load(_small(models=(_FIESTA, replace(_FOCUS, slug='focus-new'))))


def test_invalid_data_writes_nothing() -> None:
    with pytest.raises(TaxonomyDataError):
        _load(_small(models=(_FIESTA, replace(_FOCUS, body_types=('crossover',)))))
    assert _snapshot()['makes'] == []


# --- aliases follow the CSV ---------------------------------------------------------


def test_aliases_are_added_moved_and_removed_to_match_the_input() -> None:
    vauxhall = MakeRow('vauxhall', 'Vauxhall', True)
    corsa = ModelRow('vauxhall', 'corsa', 'Corsa', ('hatchback',))
    _load(
        _small(
            makes=(_FORD, vauxhall),
            models=(_FIESTA, corsa),
            aliases=(AliasRow('ford', '', 'Blue Oval'),),
        )
    )

    report = _load(
        _small(
            makes=(_FORD, vauxhall),
            models=(_FIESTA, corsa),
            aliases=(AliasRow('vauxhall', '', 'Blue Oval'),),
        )
    )

    assert (report.aliases_added, report.aliases_removed, report.updated) == (1, 1, 0)
    with SyncSessionLocal() as session:
        assert resolve_make(session, 'blue oval') == _make_id(session, 'vauxhall')

    report = _load(_small(makes=(_FORD, vauxhall), models=(_FIESTA, corsa)))

    assert (report.aliases_added, report.aliases_removed) == (0, 1)
    with SyncSessionLocal() as session:
        assert resolve_make(session, 'Blue Oval') is None


# --- concurrent loads serialise on the advisory lock --------------------------------


def _run_in_thread(target: Callable[[], object], errors: list[BaseException]) -> threading.Thread:
    def run() -> None:
        try:
            target()
        except BaseException as error:  # noqa: BLE001 - re-raised by the test
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def _advisory_lock_waiters() -> int:
    with sync_engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted")
        ).scalar_one()


def test_concurrent_loads_serialise_and_equal_a_single_load(
    committed: TaxonomyData, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_has_lock, release_first = threading.Event(), threading.Event()
    real_hold = services.hold_advisory_lock
    holder: list[str] = []

    def hold_and_pause(session: Session, lock: services.AdvisoryLock) -> None:
        real_hold(session, lock)
        if not holder:  # only the first loader pauses, while holding the lock
            holder.append(threading.current_thread().name)
            first_has_lock.set()
            assert release_first.wait(10)

    monkeypatch.setattr(services, 'hold_advisory_lock', hold_and_pause)
    reports: list[LoadReport] = []
    errors: list[BaseException] = []

    first = _run_in_thread(lambda: reports.append(_load(committed)), errors)
    assert first_has_lock.wait(10)
    second = _run_in_thread(lambda: reports.append(_load(committed)), errors)

    # The second loader is blocked on the lock, not racing the first.
    deadline = time.monotonic() + 3
    while _advisory_lock_waiters() == 0:
        assert time.monotonic() < deadline, 'second load never waited for the lock'
        time.sleep(0.05)
    release_first.set()
    first.join(15)
    second.join(15)

    assert errors == []
    rows = len(committed.makes) + len(committed.models)
    assert sorted(report.inserted for report in reports) == [0, rows]
    concurrent = _snapshot()

    _clear_taxonomy()
    _load(committed)
    assert _snapshot() == concurrent


def test_without_the_lock_concurrent_loads_collide(monkeypatch: pytest.MonkeyPatch) -> None:
    # Negative proof: the advisory lock, not luck, is what makes the test above pass.
    both_have_read = threading.Barrier(2, timeout=10)
    real_read = services._read_existing_makes

    def read_then_wait(session: Session) -> dict[str, Make]:
        existing = real_read(session)
        both_have_read.wait()
        return existing

    monkeypatch.setattr(services, 'hold_advisory_lock', lambda session, lock: None)
    monkeypatch.setattr(services, '_read_existing_makes', read_then_wait)
    errors: list[BaseException] = []

    threads = [_run_in_thread(lambda: _load(_small()), errors) for _ in range(2)]
    for thread in threads:
        thread.join(15)

    assert [type(error) for error in errors] == [IntegrityError]


# --- the real CLI -------------------------------------------------------------------


def _cli(*args: str) -> tuple[int, list[dict[str, Any]]]:
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.load_taxonomy', *args],
        cwd=_BACKEND,
        env=os.environ.copy(),  # carries this worker's test DATABASE_URL
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=120,
        check=False,
    )
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    assert lines, result.stdout + result.stderr
    return result.returncode, lines


def test_cli_loads_the_committed_taxonomy_idempotently(committed: TaxonomyData) -> None:
    rows = len(committed.makes) + len(committed.models)

    code, lines = _cli()
    assert code == 0
    assert lines[-1]['event'] == 'taxonomy_loaded'
    assert lines[-1]['inserted'] == rows

    code, lines = _cli()
    assert code == 0
    assert (lines[-1]['inserted'], lines[-1]['updated'], lines[-1]['unchanged']) == (0, 0, rows)


def test_cli_rejects_invalid_data_and_exits_non_zero(tmp_path: Path) -> None:
    (tmp_path / 'makes.csv').write_text('slug,name,is_popular\nford,Ford,true\n', encoding='utf-8')
    (tmp_path / 'models.csv').write_text(
        'make_slug,slug,name,body_types\nfourd,fiesta,Fiesta,hatchback\n', encoding='utf-8'
    )
    (tmp_path / 'aliases.csv').write_text('make_slug,model_slug,alias\n', encoding='utf-8')

    code, lines = _cli('--data-dir', str(tmp_path))

    assert code == 1
    assert lines[-1]['event'] == 'taxonomy_load_rejected'
    assert any('unknown make' in problem for problem in lines[-1]['problems'])
    assert _snapshot()['makes'] == []
