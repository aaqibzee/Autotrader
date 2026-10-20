from __future__ import annotations

import os
import re
import threading
import time

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SyncSessionLocal
from app.models.feature_flag import FeatureFlag

_CACHE_TTL_SECONDS = 30.0
_NAME_PATTERN = re.compile(r'^[a-z0-9]+(?:_[a-z0-9]+)*$')
_cache: dict[str, tuple[float, bool]] = {}
_cache_lock = threading.Lock()


def _normalize_name(name: str) -> str:
    normalized = name.strip().lower().replace('-', '_')
    if not _NAME_PATTERN.fullmatch(normalized):
        raise ValueError('Feature flag names must contain only letters, numbers, and underscores')
    return normalized


def _environment_override(name: str) -> bool | None:
    key = f'FLAG_{name.upper()}'
    value = os.environ.get(key)
    if value is None and key in settings.model_fields_set:
        value = getattr(settings, key)
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized not in {'on', 'off'}:
        raise ValueError(f'{key} must be set to "on" or "off"')
    return normalized == 'on'


def is_enabled(name: str) -> bool:
    normalized_name = _normalize_name(name)
    override = _environment_override(normalized_name)
    if override is not None:
        return override

    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(normalized_name)
        if cached is not None and cached[0] > now:
            return cached[1]
        _cache.pop(normalized_name, None)

    with SyncSessionLocal() as session:
        enabled = session.scalar(
            select(FeatureFlag.enabled).where(FeatureFlag.name == normalized_name)
        )
    result = bool(enabled)

    with _cache_lock:
        _cache[normalized_name] = (time.monotonic() + _CACHE_TTL_SECONDS, result)
    return result
