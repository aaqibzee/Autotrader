"""Optimistic locking on `updated_at` (Feature 01 §5).

Editable entities carry `updated_at` as the lock token. A client sends back the value it
read; if the row changed since, the save is rejected with 409 `stale_update` plus the
current representation, so the UI can show what changed instead of silently overwriting.

Rule (Yaqlo was bitten twice): `onupdate=now()` fires on *any* UPDATE, so background
writes (counters, stats, computed indicators) must go to separate tables, never to a
locked row, or they invalidate every open editor's token.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.errors import AppError, ProblemCode


class StaleUpdateError(AppError):
    def __init__(self, current: dict[str, Any]) -> None:
        super().__init__(
            'This record was changed by someone else. Review the latest version and try again.',
            code=ProblemCode.STALE_UPDATE,
            status_code=409,
            extra={'current': current},
        )


def ensure_not_stale(
    current_updated_at: datetime,
    expected_updated_at: datetime,
    current_representation: dict[str, Any],
) -> None:
    """Raise StaleUpdateError unless the client's token matches the stored row.

    Call after loading the row with `SELECT ... FOR UPDATE` so two concurrent saves with
    the same token cannot both pass the check.
    """
    if current_updated_at != expected_updated_at:
        raise StaleUpdateError(current_representation)
