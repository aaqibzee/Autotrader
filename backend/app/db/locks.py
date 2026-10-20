"""Transaction-scoped advisory locks (Feature 02 A5).

Every key lives in this one enum so two commands can never pick the same number by
accident. `pg_advisory_xact_lock` waits for the lock and releases it at commit or
rollback, so a crashed run cannot leave it held.
"""

from __future__ import annotations

from enum import IntEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session


class AdvisoryLock(IntEnum):
    TAXONOMY_LOAD = 2_0001


def hold_advisory_lock(session: Session, lock: AdvisoryLock) -> None:
    """Block until `lock` is free, then hold it until `session`'s transaction ends."""
    session.execute(select(func.pg_advisory_xact_lock(int(lock))))
