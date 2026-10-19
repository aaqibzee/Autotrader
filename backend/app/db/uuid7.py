from __future__ import annotations

import secrets
import time
from uuid import UUID


def uuid7() -> UUID:
    """Return an RFC 9562 UUIDv7 without requiring Python 3.14+."""
    timestamp_ms = time.time_ns() // 1_000_000
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)

    value = (timestamp_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= random_a << 64
    value |= 0b10 << 62
    value |= random_b
    return UUID(int=value)
