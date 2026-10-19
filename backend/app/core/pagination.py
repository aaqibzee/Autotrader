"""Shared list-endpoint envelopes (Feature 01 §5).

Offset pages (`Page`) for browsable lists; cursor pages (`CursorPage`) for high-volume,
append-only feeds (alerts, admin logs) where OFFSET scans get slower as they grow.
"""

from __future__ import annotations

import base64
import json
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from app.core.errors import AppError, ProblemCode

T = TypeVar('T')

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class PageParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> PageParams:
    """FastAPI dependency: `params: Annotated[PageParams, Depends(page_params)]`."""
    return PageParams(page=page, page_size=page_size)


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


def encode_cursor(position: dict[str, Any]) -> str:
    """Opaque cursor from the last row's sort key (e.g. {'created_at': ..., 'id': ...})."""
    raw = json.dumps(position, separators=(',', ':'), sort_keys=True, default=str)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip('=')


def decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        padded = cursor + '=' * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError('The cursor is invalid.', code=ProblemCode.INVALID_CURSOR) from exc
    if not isinstance(value, dict):
        raise AppError('The cursor is invalid.', code=ProblemCode.INVALID_CURSOR)
    return value
