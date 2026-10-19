from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.uuid7 import uuid7


class FeatureFlag(TimestampMixin, Base):
    __tablename__ = 'feature_flags'
    # is_enabled() normalises names before querying ('value-my-car' -> 'value_my_car'), so a
    # row stored in any other form could never be found and the flag would silently stay
    # off. The database refuses that form outright.
    __table_args__ = (
        CheckConstraint(r"name ~ '^[a-z0-9]+(_[a-z0-9]+)*$'", name='name_normalised'),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='false'
    )
