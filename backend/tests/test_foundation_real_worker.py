"""Integration tests against a real Celery worker and broker (Feature 01 §7).

Eager mode hides exactly the bugs these catch: JSON serialisation of task arguments,
and the after-commit timing between the request transaction and the worker reading
the row. The worker runs in-thread, consuming from the real test Redis broker and
reading the real test database through its own engine.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator

import pytest
from celery.contrib.testing.worker import start_worker
from sqlalchemy import delete, select

from app.core.cache import get_cache_client
from app.core.celery_app import celery_app
from app.core.jobs import dispatch
from app.db.session import SyncSessionLocal, WorkerSessionLocal
from app.models import FeatureFlag

_RESULT_PREFIX = 'autotrader:test:worker-probe:'


@celery_app.task(name='tests.worker_probe.record_row_visibility')
def record_row_visibility(flag_name: str, marker: str) -> None:
    with WorkerSessionLocal() as session:
        visible = session.scalar(select(FeatureFlag.id).where(FeatureFlag.name == flag_name))
    get_cache_client().set(_RESULT_PREFIX + marker, 'visible' if visible else 'missing', ex=60)


@pytest.fixture(scope='module')
def real_worker() -> Generator[None, None, None]:
    # Drop anything a previous run left on the queue, so only this test's tasks run.
    celery_app.control.purge()
    with start_worker(
        celery_app,
        pool='solo',
        perform_ping_check=False,
        queues=['default'],
        shutdown_timeout=10,
    ):
        yield


@pytest.fixture
def flag_cleanup() -> Generator[None, None, None]:
    yield
    with SyncSessionLocal.begin() as session:
        session.execute(delete(FeatureFlag).where(FeatureFlag.name.like('worker_probe_%')))


def _wait_for(marker: str, seconds: float) -> str | None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = get_cache_client().get(_RESULT_PREFIX + marker)
        if value is not None:
            return str(value)
        time.sleep(0.05)
    return None


def test_committed_dispatch_runs_on_a_real_worker_after_the_row_is_visible(
    real_worker: None, flag_cleanup: None
) -> None:
    name = f'worker_probe_{uuid.uuid4().hex[:12]}'
    marker = uuid.uuid4().hex
    with SyncSessionLocal.begin() as session:
        session.add(FeatureFlag(name=name, enabled=True))
        session.flush()
        dispatch(record_row_visibility, name, marker, session=session)

    assert _wait_for(marker, 15) == 'visible'


def test_rolled_back_dispatch_never_reaches_the_worker(
    real_worker: None, flag_cleanup: None
) -> None:
    name = f'worker_probe_{uuid.uuid4().hex[:12]}'
    rolled_back_marker = uuid.uuid4().hex
    with SyncSessionLocal() as session:
        session.begin()
        session.add(FeatureFlag(name=name, enabled=True))
        session.flush()
        dispatch(record_row_visibility, name, rolled_back_marker, session=session)
        session.rollback()

    # A committed sentinel sent afterwards proves the worker is alive and has drained
    # the queue past the point where the rolled-back task would have been.
    sentinel = uuid.uuid4().hex
    with SyncSessionLocal.begin() as session:
        session.add(FeatureFlag(name=f'{name}_sentinel', enabled=True))
        session.flush()
        dispatch(record_row_visibility, f'{name}_sentinel', sentinel, session=session)

    assert _wait_for(sentinel, 15) == 'visible'
    assert get_cache_client().get(_RESULT_PREFIX + rolled_back_marker) is None
