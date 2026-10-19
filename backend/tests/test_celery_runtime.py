from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core import celery_app as celery_module


def test_celery_uses_separate_workload_queues_and_safe_task_defaults() -> None:
    app = celery_module.celery_app
    assert {queue.name for queue in app.conf.task_queues} == {
        'default',
        'images',
        'notifications',
    }
    assert app.conf.task_routes['app.tasks.notifications.*']['queue'] == 'notifications'
    assert app.conf.task_routes['app.tasks.images.*']['queue'] == 'images'
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.task_ignore_result is True
    assert app.conf.task_soft_time_limit == 60
    assert app.conf.task_time_limit == 120


def test_cloudflare_ranges_refresh_is_scheduled_weekly() -> None:
    entry = celery_module.celery_app.conf.beat_schedule['refresh-cloudflare-ranges-weekly']
    assert entry['task'] == 'app.tasks.cloudflare_ranges.refresh_cloudflare_ranges'
    assert entry['schedule'].day_of_week == {0}
    assert entry['schedule'].hour == {3}


def test_second_beat_exits_when_redis_lock_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
    lock = MagicMock()
    lock.acquire.return_value = False
    client = MagicMock()
    client.lock.return_value = lock
    monkeypatch.setattr(celery_module.Redis, 'from_url', lambda *_args, **_kwargs: client)

    process_lock = celery_module._BeatProcessLock()
    with pytest.raises(SystemExit, match='lock held'):
        process_lock.acquire()

    lock.acquire.assert_called_once_with(blocking=False)
    client.close.assert_called_once()


def test_worker_process_redacts_logs_and_initialises_tracing() -> None:
    import os
    import subprocess
    import sys

    # A fresh interpreter, like a real worker: it never imports app.main.
    script = (
        'from celery.signals import worker_init\n'
        'from app.core.celery_app import celery_app\n'
        'worker_init.send(sender=None)\n'
        'import structlog\n'
        'from opentelemetry import trace\n'
        "structlog.get_logger('task').info('lead_sent', email='jane.doe@example.com',"
        " phone='07700 900123', vrm='AB12 CDE')\n"
        "print('SERVICE=' + trace.get_tracer_provider().resource.attributes['service.name'])\n"
    )
    result = subprocess.run(
        [sys.executable, '-c', script],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, 'PYTHONPATH': '.'},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert 'SERVICE=autotrader-worker' in result.stdout
    assert 'lead_sent' in result.stdout
    for raw in ('jane.doe@example.com', '07700 900123', 'AB12 CDE'):
        assert raw not in result.stdout
