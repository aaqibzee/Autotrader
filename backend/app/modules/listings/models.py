"""`Listing`, the central table (Feature 02 §3). Feature 05 is its main writer.

The database refuses every contradictory row: ranges, enum values, the lifecycle
timestamps, and (A12) a non-draft listing missing anything the publish validator
requires. Composite FKs (A13) keep a listing's model inside its make and its `is_demo`
equal to its dealer's.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ColumnElement,
    Date,
    DateTime,
    Double,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    SQLColumnExpression,
    String,
    Text,
    and_,
    literal,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin
from app.db.checks import coordinate_checks, enum_check
from app.db.uuid7 import uuid7
from app.modules.listings.enums import ListingStatus, ModerationStatus
from app.modules.taxonomy.enums import BodyType, Colour, FuelType, Transmission

VISIBLE_STATUSES = (ListingStatus.ACTIVE, ListingStatus.RESERVED)
LIVE_STATUSES = VISIBLE_STATUSES
TITLE_MAX_LENGTH = 160
DESCRIPTION_MAX_LENGTH = 5_000
# `derive.normalise_vrm`'s output (slice 2.5): upper-case letters and digits, 2-7 long.
VRM_PATTERN = r'^[A-Z0-9]{2,7}$'

# Everything Feature 05's publish validator requires (05 §2) apart from images and the
# description length. Only a draft, or a draft that was archived, may lack them (A12).
PUBLISH_REQUIRED_COLUMNS = (
    'make_id',
    'model_id',
    'year',
    'registration_date',
    'mileage',
    'price_pence',
    'body_type',
    'fuel_type',
    'transmission',
    'ulez_compliant',
)


def _status_in(status: SQLColumnExpression[Any], statuses: tuple[str, ...]) -> ColumnElement[bool]:
    # Constants render inline (`status IN ('active', 'reserved')`) rather than as bound
    # parameters, in queries as well as in index DDL. A partial index is only usable when
    # the planner can prove the query's predicate implies the index's, which it cannot do
    # for a parameter under a generic (prepared) plan.
    return status.in_([literal(str(value), String, literal_execute=True) for value in statuses])


def visible_predicate(
    status: SQLColumnExpression[Any],
    moderation_status: SQLColumnExpression[Any],
    archived_at: SQLColumnExpression[Any],
) -> ColumnElement[bool]:
    """The public-visibility rule (Feature 02 §5), over any three columns.

    The partial indexes below and `visibility.publicly_visible()` both build from this one
    function, so the predicate in the index and in every query is the same text.
    """
    return and_(
        _status_in(status, VISIBLE_STATUSES),
        moderation_status == literal(ModerationStatus.CLEAR.value, String, literal_execute=True),
        archived_at.is_(None),
    )


def is_visible(status: str, moderation_status: str, archived_at: datetime | None) -> bool:
    """`visible_predicate` for values already loaded (tested against it on every state)."""
    return (
        status in VISIBLE_STATUSES
        and moderation_status == ModerationStatus.CLEAR
        and archived_at is None
    )


def _range(column: str, low: int, high: int) -> CheckConstraint:
    return CheckConstraint(f'{column} BETWEEN {low} AND {high}', name=f'{column}_range')


def _publish_complete() -> CheckConstraint:
    required = ' AND '.join(f'{column} IS NOT NULL' for column in PUBLISH_REQUIRED_COLUMNS)
    return CheckConstraint(
        f"status IN ('draft', 'archived') OR ({required} AND char_length(title) > 0)",
        name='publish_complete',
    )


class Listing(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = 'listings'
    __table_args__ = (
        ForeignKeyConstraint(
            ['dealer_id', 'is_demo'], ['dealers.id', 'dealers.is_demo'], ondelete='CASCADE'
        ),
        ForeignKeyConstraint(
            ['make_id', 'model_id'], ['vehicle_models.make_id', 'vehicle_models.id']
        ),
        enum_check('status', ListingStatus),
        enum_check('moderation_status', ModerationStatus),
        enum_check('body_type', BodyType),
        enum_check('fuel_type', FuelType),
        enum_check('transmission', Transmission),
        enum_check('colour', Colour),
        _range('year', 1900, 2100),
        _range('mileage', 0, 1_000_000),
        _range('price_pence', 10_000, 500_000_000),
        _range('engine_size_cc', 0, 10_000),
        _range('doors', 1, 7),
        _range('seats', 1, 9),
        _range('owners', 0, 99),
        CheckConstraint('photo_count >= 0', name='photo_count_range'),
        CheckConstraint('specs_version >= 1', name='specs_version_range'),
        CheckConstraint("jsonb_typeof(specs) = 'object'", name='specs_object'),
        CheckConstraint(
            f'char_length(description) <= {DESCRIPTION_MAX_LENGTH}', name='description_length'
        ),
        CheckConstraint(f"vrm ~ '{VRM_PATTERN}'", name='vrm_normalised'),
        *coordinate_checks(),
        # Lifecycle consistency (design §3): one soft-delete signal, and every state carries
        # the timestamp that proves how it got there.
        CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)", name='archived_iff_archived_at'
        ),
        CheckConstraint("status <> 'sold' OR sold_at IS NOT NULL", name='sold_has_sold_at'),
        CheckConstraint(
            "status IN ('draft', 'archived') OR published_at IS NOT NULL",
            name='published_has_published_at',
        ),
        CheckConstraint(
            'listed_at IS NULL OR published_at IS NOT NULL', name='listed_has_published_at'
        ),
        _publish_complete(),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    dealer_id: Mapped[UUID] = mapped_column(nullable=False)
    # Copied from the dealer at create; the composite FK keeps it equal to the dealer's.
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='false'
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ListingStatus.DRAFT, server_default='draft'
    )
    moderation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ModerationStatus.CLEAR, server_default='clear'
    )

    # Vehicle. Nullable because drafts autosave half-filled forms (Feature 05 §3); the
    # publish_complete CHECK makes them required everywhere else.
    make_id: Mapped[UUID | None] = mapped_column(ForeignKey('makes.id'))
    model_id: Mapped[UUID | None] = mapped_column()
    variant: Mapped[str | None] = mapped_column(String(80))
    year: Mapped[int | None] = mapped_column(SmallInteger)
    registration_date: Mapped[date | None] = mapped_column(Date)
    mileage: Mapped[int | None] = mapped_column(Integer)
    price_pence: Mapped[int | None] = mapped_column(Integer)
    body_type: Mapped[str | None] = mapped_column(String(16))
    fuel_type: Mapped[str | None] = mapped_column(String(16))
    transmission: Mapped[str | None] = mapped_column(String(16))
    colour: Mapped[str | None] = mapped_column(String(16))
    engine_size_cc: Mapped[int | None] = mapped_column(SmallInteger)
    doors: Mapped[int | None] = mapped_column(SmallInteger)
    seats: Mapped[int | None] = mapped_column(SmallInteger)
    owners: Mapped[int | None] = mapped_column(SmallInteger)
    vrm: Mapped[str | None] = mapped_column(String(7))

    # Derived (design §6): written only from `derive.py`, never entered.
    title: Mapped[str] = mapped_column(
        String(TITLE_MAX_LENGTH), nullable=False, default='', server_default=''
    )
    ulez_compliant: Mapped[bool | None] = mapped_column(Boolean)

    description: Mapped[str] = mapped_column(Text, nullable=False, default='', server_default='')
    specs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    specs_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default='1'
    )

    # System-owned (design §5): written only through `system_update()` (slice 2.6).
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    photo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


_visible = visible_predicate(Listing.status, Listing.moderation_status, Listing.archived_at)

# Design §7. Descending sorts (`updated_at DESC`, `listed_at DESC`) read these ascending
# indexes backwards, so no DESC (expression) index is needed.
Index(
    'ix_listings_dealer_id_status_updated_at', Listing.dealer_id, Listing.status, Listing.updated_at
)
# Serves the (make_id, model_id) FK and the make_id FK; taxonomy rows are never deleted,
# but a RESTRICT check must not scan the table.
Index('ix_listings_make_id_model_id', Listing.make_id, Listing.model_id)
Index(
    'ix_listings_vrm_live',
    Listing.vrm,
    postgresql_where=and_(Listing.vrm.is_not(None), _status_in(Listing.status, LIVE_STATUSES)),
)
Index(
    'ix_listings_visible_make_id_model_id_price_pence',
    Listing.make_id,
    Listing.model_id,
    Listing.price_pence,
    postgresql_where=_visible,
)
Index('ix_listings_visible_listed_at', Listing.listed_at, postgresql_where=_visible)
Index(
    'ix_listings_visible_latitude_longitude',
    Listing.latitude,
    Listing.longitude,
    postgresql_where=_visible,
)
