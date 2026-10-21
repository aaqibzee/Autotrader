from __future__ import annotations

import os
import socket
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from alembic import command

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLES_SQL = _REPO_ROOT / 'ops' / 'postgres' / 'roles.sql'
# Advisory lock key for applying roles.sql, taken on the `postgres` database (never an app
# database, so it cannot collide with app/db/locks.py's keys). Arbitrary, but fixed.
_ROLES_LOCK_KEY = 7_301_003
_TEST_ENV = dotenv_values(_REPO_ROOT / '.env.test')
for _key, _value in _TEST_ENV.items():
    if _value is not None:
        os.environ.setdefault(_key, _value)

_DEFAULT_DATABASE_URL = (
    'postgresql+psycopg://autotrader:local-only-postgres-password@127.0.0.1:5432/autotrader'
)
_BASE_DATABASE_URL = os.environ.get('DATABASE_URL', _DEFAULT_DATABASE_URL)
_WORKER_ID = os.environ.get('PYTEST_XDIST_WORKER', 'gw0')
_DATABASE_URL = make_url(_BASE_DATABASE_URL)
_TEST_DATABASE_NAME = f'{_DATABASE_URL.database}_test_{_WORKER_ID}'
_TEST_DATABASE_URL = _DATABASE_URL.set(database=_TEST_DATABASE_NAME)
os.environ['DATABASE_URL'] = _TEST_DATABASE_URL.render_as_string(hide_password=False)


def _prepare_test_database() -> None:
    admin_url = _DATABASE_URL.set(database='postgres')
    admin_engine = create_engine(admin_url, isolation_level='AUTOCOMMIT', poolclass=NullPool)
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text('SELECT 1 FROM pg_database WHERE datname = :name'),
                {'name': _TEST_DATABASE_NAME},
            ).scalar_one_or_none()
            if not exists:
                quoted_name = connection.dialect.identifier_preparer.quote(_TEST_DATABASE_NAME)
                connection.execute(text(f'CREATE DATABASE {quoted_name}'))
    finally:
        admin_engine.dispose()

    alembic_config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    alembic_config.set_main_option(
        'sqlalchemy.url',
        _TEST_DATABASE_URL.render_as_string(hide_password=False).replace('%', '%%'),
    )
    alembic_config.attributes['configure_logger'] = False
    command.upgrade(alembic_config, 'head')

    # Grants are per-database, so every worker DB needs the least-privilege roles applied.
    # But roles.sql also writes cluster-wide catalog rows (`CREATE ROLE`, `ALTER ROLE ... SET`
    # in pg_authid / pg_db_role_setting), and xdist workers applying it at the same moment
    # fail with "tuple concurrently updated". So the step is serialised across workers by
    # an advisory lock. Advisory locks are scoped to a database, and each worker has its
    # own, so the lock is held on the shared `postgres` database.
    lock_engine = create_engine(admin_url, isolation_level='AUTOCOMMIT', poolclass=NullPool)
    roles_engine = create_engine(_TEST_DATABASE_URL, poolclass=NullPool)
    try:
        with lock_engine.connect() as lock_connection:
            lock_connection.execute(text('SELECT pg_advisory_lock(:key)'), {'key': _ROLES_LOCK_KEY})
            try:
                with roles_engine.begin() as connection:
                    # Raw driver call with no params: psycopg would otherwise parse
                    # format()'s %I.
                    driver_connection = connection.connection.driver_connection
                    assert driver_connection is not None
                    driver_connection.execute(_ROLES_SQL.read_text(encoding='utf-8'))
            finally:
                lock_connection.execute(
                    text('SELECT pg_advisory_unlock(:key)'), {'key': _ROLES_LOCK_KEY}
                )
    finally:
        roles_engine.dispose()
        lock_engine.dispose()

    test_engine = create_engine(_TEST_DATABASE_URL, poolclass=NullPool)
    try:
        with test_engine.begin() as connection:
            table_names = [
                name
                for name in inspect(connection).get_table_names(schema='public')
                if name != 'alembic_version'
            ]
            if table_names:
                quoted_tables = ', '.join(
                    connection.dialect.identifier_preparer.quote(name) for name in table_names
                )
                connection.execute(text(f'TRUNCATE TABLE {quoted_tables} RESTART IDENTITY CASCADE'))
    finally:
        test_engine.dispose()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--no-test-database',
        action='store_true',
        default=False,
        help='skip isolated PostgreSQL setup for tests that do not require a database',
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    if session.config.getoption('--no-test-database'):
        return
    if os.environ.get('PYTEST_XDIST_TESTRUNUID') and 'PYTEST_XDIST_WORKER' not in os.environ:
        return
    _prepare_test_database()


@pytest.fixture(scope='session')
def client() -> Generator[TestClient, None, None]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def block_unstubbed_network(monkeypatch: pytest.MonkeyPatch) -> None:
    original_connect = socket.socket.connect
    allowed_ports = {5432, 5433, 6379, 6380, 6381, 6382, 9000, 9002}

    def guarded_connect(sock: socket.socket, address: object) -> None:
        if isinstance(address, tuple) and len(address) >= 2:
            host, port = address[0], address[1]
            if host in {'127.0.0.1', '::1', 'localhost'} and port in allowed_ports:
                original_connect(sock, address)
                return
            if (
                host in {'127.0.0.1', '::1', 'localhost'}
                and isinstance(port, int)
                and 49152 <= port <= 65535
                and not sock.getblocking()
            ):
                original_connect(sock, address)
                return
        raise OSError(f'Unstubbed outbound network access blocked: {address!r}')

    monkeypatch.setattr(socket.socket, 'connect', guarded_connect)
