from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.checks import enum_check
from app.db.uuid7 import uuid7
from app.modules.taxonomy.enums import BodyType

# Slugs appear in SEO URLs (Feature 13) and are immutable once created, so the database
# refuses anything that is not already in URL form.
SLUG_PATTERN = r'^[a-z0-9]+(-[a-z0-9]+)*$'


def _slug_format() -> CheckConstraint:
    return CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name='slug_format')


def _alias_upper_case() -> CheckConstraint:
    # Resolvers upper-case their input before looking an alias up, so an alias stored in
    # any other case could never match.
    return CheckConstraint('alias = upper(alias)', name='alias_upper_case')


class Make(TimestampMixin, Base):
    __tablename__ = 'makes'
    __table_args__ = (_slug_format(),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    is_popular: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='false'
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default='true'
    )


class VehicleModel(TimestampMixin, Base):
    __tablename__ = 'vehicle_models'
    __table_args__ = (
        UniqueConstraint('make_id', 'slug'),
        _slug_format(),
        enum_check('body_types', BodyType, array=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    # Covered by the (make_id, slug) unique index, so no separate FK index.
    make_id: Mapped[UUID] = mapped_column(ForeignKey('makes.id'), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    body_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default='true'
    )


class MakeAlias(TimestampMixin, Base):
    __tablename__ = 'make_aliases'
    __table_args__ = (_alias_upper_case(),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    # One alias, one make: an ambiguous alias would make resolution order-dependent.
    alias: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    make_id: Mapped[UUID] = mapped_column(
        ForeignKey('makes.id', ondelete='CASCADE'), nullable=False, index=True
    )


class ModelAlias(TimestampMixin, Base):
    __tablename__ = 'model_aliases'
    __table_args__ = (UniqueConstraint('model_id', 'alias'), _alias_upper_case())

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    alias: Mapped[str] = mapped_column(String(80), nullable=False)
    model_id: Mapped[UUID] = mapped_column(
        ForeignKey('vehicle_models.id', ondelete='CASCADE'), nullable=False
    )
