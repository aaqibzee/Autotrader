"""Dealer enumerations (Feature 02 §2)."""

from __future__ import annotations

from enum import StrEnum


class DealerStatus(StrEnum):
    """Approval state. Transitions are owned by Feature 14 §3."""

    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    SUSPENDED = 'suspended'
