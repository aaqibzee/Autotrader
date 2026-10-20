"""`Dealer` core (Feature 02 §2). Feature 04 adds the account columns in its own migration."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Double, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.checks import coordinate_checks, enum_check, slug_format_check
from app.db.uuid7 import uuid7
from app.modules.dealers.enums import DealerStatus
from app.modules.geo.services import Region

# A full postcode in its normal form (`SW1A 1AA`) or an outward code alone (`SW1A`; demo
# dealers store only that, Feature 02 A2). Writers normalise before saving.
POSTCODE_PATTERN = r'^[A-Z]{1,2}[0-9][A-Z0-9]?( [0-9][A-Z]{2})?$'


class Dealer(TimestampMixin, Base):
    __tablename__ = 'dealers'
    __table_args__ = (
        # Target of listings' composite FK, so a listing's is_demo always equals its dealer's
        # and a demo reset (cascade from demo dealers) can never reach a real listing.
        UniqueConstraint('id', 'is_demo'),
        slug_format_check(),
        CheckConstraint(f"postcode ~ '{POSTCODE_PATTERN}'", name='postcode_format'),
        *coordinate_checks(),
        enum_check('status', DealerStatus),
        enum_check('region_code', Region),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    postcode: Mapped[str] = mapped_column(String(8), nullable=False)
    # Null only when geocoding failed with no offline fallback (Northern Ireland, 02 A11).
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
    region_code: Mapped[str | None] = mapped_column(String(9))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DealerStatus.PENDING, server_default='pending'
    )
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='false'
    )
