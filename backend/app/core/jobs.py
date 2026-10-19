from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

import structlog
from celery.app.task import Task
from opentelemetry import propagate
from sqlalchemy import event
from sqlalchemy.orm import Session, SessionTransaction

logger = structlog.get_logger(__name__)
_PENDING_DISPATCHES = 'autotrader.pending_task_dispatches'
_COMMITTED_TRANSACTION = 'autotrader.committed_transaction'
_DispatchCallback = tuple[SessionTransaction, str, Callable[[], Any]]


def dispatch(
    task: Task,
    *args: Any,
    session: Session,
    task_kwargs: Mapping[str, Any] | None = None,
    queue: str | None = None,
    **publish_options: Any,
) -> None:
    """Schedule a Celery task only after its owning SQLAlchemy transaction commits."""
    transaction = session.get_nested_transaction() or session.get_transaction()
    if transaction is None or not session.in_transaction():
        raise RuntimeError('dispatch requires an active SQLAlchemy transaction')

    options = dict(publish_options)
    if queue is not None:
        options['queue'] = queue

    request_id = _request_id_from_context()
    headers = dict(options.get('headers') or {})
    if request_id:
        headers.setdefault('request_id', request_id)
    from app.core.http_client import current_traceparent

    current_parent = current_traceparent()
    if current_parent:
        headers.setdefault('traceparent', current_parent)
    else:
        traceparent: dict[str, str] = {}
        propagate.inject(traceparent)
        if traceparent:
            headers.setdefault('traceparent', traceparent['traceparent'])
    if headers:
        options['headers'] = headers

    task_name = cast(str, getattr(task, 'name', None) or task.__class__.__name__)

    def publish() -> Any:
        return task.apply_async(
            args=args,
            kwargs=dict(task_kwargs or {}),
            **options,
        )

    pending: list[_DispatchCallback] = session.info.setdefault(_PENDING_DISPATCHES, [])
    pending.append((transaction, task_name, publish))


def _request_id_from_context() -> str | None:
    from app.core.http_client import current_request_id

    return current_request_id()


def _transaction_is_within(
    transaction: SessionTransaction,
    ancestor: SessionTransaction,
) -> bool:
    current: SessionTransaction | None = transaction
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


@event.listens_for(Session, 'after_commit')
def _publish_committed_dispatches(session: Session) -> None:
    transaction = session.get_transaction()
    if transaction is not None:
        session.info[_COMMITTED_TRANSACTION] = transaction


@event.listens_for(Session, 'after_transaction_end')
def _dispatch_after_outer_transaction_end(
    session: Session,
    transaction: SessionTransaction,
) -> None:
    if transaction.parent is not None:
        return
    committed_transaction = session.info.pop(_COMMITTED_TRANSACTION, None)
    if committed_transaction is not transaction:
        session.info.pop(_PENDING_DISPATCHES, None)
        return

    pending: list[_DispatchCallback] = session.info.pop(_PENDING_DISPATCHES, [])
    for _, task_name, publish in pending:
        try:
            publish()
        except Exception:
            logger.exception('celery_task_publish_failed', task=task_name)


@event.listens_for(Session, 'after_soft_rollback')
def _discard_rolled_back_dispatches(
    session: Session,
    previous_transaction: SessionTransaction,
) -> None:
    committed_transaction = session.info.get(_COMMITTED_TRANSACTION)
    if committed_transaction is previous_transaction:
        session.info.pop(_COMMITTED_TRANSACTION, None)
    pending: list[_DispatchCallback] = session.info.get(_PENDING_DISPATCHES, [])
    if not pending:
        return
    remaining = [
        item for item in pending if not _transaction_is_within(item[0], previous_transaction)
    ]
    if remaining:
        session.info[_PENDING_DISPATCHES] = remaining
    else:
        session.info.pop(_PENDING_DISPATCHES, None)
