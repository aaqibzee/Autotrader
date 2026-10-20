"""Listing enumerations (Feature 02 §3)."""

from __future__ import annotations

from enum import StrEnum


class ListingStatus(StrEnum):
    """The dealer-driven lifecycle, owned by Feature 05 §1."""

    DRAFT = 'draft'
    ACTIVE = 'active'
    RESERVED = 'reserved'
    SOLD = 'sold'
    ARCHIVED = 'archived'


class ModerationStatus(StrEnum):
    """System-owned (Feature 02 §5); written only by Feature 14's moderation service."""

    CLEAR = 'clear'
    HELD = 'held'
    HIDDEN = 'hidden'
    REMOVED = 'removed'
