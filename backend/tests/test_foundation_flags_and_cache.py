from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from redis import Redis
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.core import cache, feature_flags
from app.db.session import SyncSessionLocal
from app.models import FeatureFlag


@pytest.fixture
def flag_table() -> Generator[None, None, None]:
    feature_flags._cache.clear()
    yield
    with SyncSessionLocal.begin() as session:
        session.execute(delete(FeatureFlag))
    feature_flags._cache.clear()


def _store_flag(name: str, enabled: bool) -> None:
    with SyncSessionLocal.begin() as session:
        existing = session.query(FeatureFlag).filter_by(name=name).one_or_none()
        if existing:
            existing.enabled = enabled
        else:
            session.add(FeatureFlag(name=name, enabled=enabled))


def test_flag_reads_database_value_and_unknown_flags_are_off(flag_table: None) -> None:
    _store_flag('new_search', True)
    assert feature_flags.is_enabled('new_search') is True
    assert feature_flags.is_enabled('never_created') is False


def test_flag_names_are_normalised_on_read(flag_table: None) -> None:
    _store_flag('value_my_car', True)
    assert feature_flags.is_enabled('Value-My-Car') is True


def test_database_refuses_unnormalised_flag_names(flag_table: None) -> None:
    with pytest.raises(IntegrityError), SyncSessionLocal.begin() as session:
        session.add(FeatureFlag(name='value-my-car', enabled=True))


def test_flag_value_is_cached_for_thirty_seconds(
    flag_table: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(feature_flags.time, 'monotonic', lambda: clock[0])
    _store_flag('cached_flag', False)
    assert feature_flags.is_enabled('cached_flag') is False

    _store_flag('cached_flag', True)
    clock[0] += 29
    assert feature_flags.is_enabled('cached_flag') is False  # still the cached value
    clock[0] += 2
    assert feature_flags.is_enabled('cached_flag') is True  # refreshed after expiry


def test_environment_override_beats_the_database(
    flag_table: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store_flag('override_me', False)
    monkeypatch.setenv('FLAG_OVERRIDE_ME', 'on')
    assert feature_flags.is_enabled('override_me') is True
    monkeypatch.setenv('FLAG_OVERRIDE_ME', ' OFF ')
    assert feature_flags.is_enabled('override_me') is False


def test_invalid_override_value_or_name_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FLAG_TYPO_FLAG', 'yes')
    with pytest.raises(ValueError, match='"on" or "off"'):
        feature_flags.is_enabled('typo_flag')
    with pytest.raises(ValueError, match='letters, numbers'):
        feature_flags.is_enabled('bad name!')


@pytest.fixture
def namespace() -> str:
    return f'tests.{uuid.uuid4().hex}'


def test_get_or_set_computes_once_then_serves_from_cache(namespace: str) -> None:
    calls: list[int] = []

    def compute() -> dict[str, int]:
        calls.append(1)
        return {'count': 42}

    assert cache.get_or_set('facets', 60, compute, namespace=namespace) == {'count': 42}
    assert cache.get_or_set('facets', 60, compute, namespace=namespace) == {'count': 42}
    assert len(calls) == 1
    ttl = cache.get_cache_client().ttl(cache.cache_key('facets', namespace=namespace))
    assert 0 < int(ttl) <= 60  # type: ignore[arg-type]


def test_schema_version_bump_ignores_old_shape(namespace: str) -> None:
    cache.get_or_set('shape', 60, lambda: {'old': True}, namespace=namespace, version=1)
    fresh = cache.get_or_set('shape', 60, lambda: {'new': True}, namespace=namespace, version=2)
    assert fresh == {'new': True}


def test_corrupt_cached_value_is_recomputed(namespace: str) -> None:
    key = cache.cache_key('corrupt', namespace=namespace)
    cache.get_cache_client().set(key, '{not json', ex=60)
    assert cache.get_or_set('corrupt', 60, lambda: [1, 2], namespace=namespace) == [1, 2]


def test_unserialisable_value_is_returned_but_not_cached(namespace: str) -> None:
    marker = object()
    assert cache.get_or_set('obj', 60, lambda: marker, namespace=namespace) is marker
    assert cache.get_cache_client().get(cache.cache_key('obj', namespace=namespace)) is None


def test_cache_fails_open_when_redis_is_unreachable(
    namespace: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The suite's network guard refuses this host, so every Redis call raises a
    # ConnectionError; the cache must degrade to computing the value, not fail the request.
    unreachable = Redis.from_url('redis://127.0.0.2:6382/0', socket_connect_timeout=0.2)
    monkeypatch.setattr(cache, '_client', unreachable)
    assert cache.get_or_set('k', 60, lambda: 'computed', namespace=namespace) == 'computed'


def test_cache_key_validation() -> None:
    with pytest.raises(ValueError, match='namespace'):
        cache.cache_key('k', namespace=' ')
    with pytest.raises(ValueError, match='version'):
        cache.cache_key('k', namespace='n', version=0)
    with pytest.raises(ValueError, match='ttl'):
        cache.get_or_set('k', 0, lambda: 1, namespace='n')
