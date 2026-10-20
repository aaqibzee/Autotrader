"""dealers and listings tables

Revision ID: ec9f1da5d225
Revises: 4c3a08d3e71a
Create Date: 2026-10-20 08:36:55.160201
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'ec9f1da5d225'
down_revision: str | None = '4c3a08d3e71a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# CHECK bodies and index predicates are literal on purpose: a migration is a snapshot and
# must not import live enums or the visibility predicate (see e1cff08ecd05). The enum-drift
# test and the partial-index test keep them in agreement with the code.
_VISIBLE = (
    "status IN ('active', 'reserved') AND moderation_status = 'clear' AND archived_at IS NULL"
)


def upgrade() -> None:
    # The composite FK from listings needs this key to exist first (Feature 02 A13).
    op.create_unique_constraint(
        op.f('uq_vehicle_models_make_id_id'), 'vehicle_models', ['make_id', 'id']
    )
    op.create_table(
        'dealers',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('slug', sa.String(length=120), nullable=False),
        sa.Column('postcode', sa.String(length=8), nullable=False),
        sa.Column('latitude', sa.Double(), nullable=True),
        sa.Column('longitude', sa.Double(), nullable=True),
        sa.Column('region_code', sa.String(length=9), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "postcode ~ '^[A-Z]{1,2}[0-9][A-Z0-9]?( [0-9][A-Z]{2})?$'",
            name=op.f('ck_dealers_postcode_format'),
        ),
        sa.CheckConstraint(
            "region_code IN ('E12000001', 'E12000002', 'E12000003', 'E12000004', 'E12000005', 'E12000006', 'E12000007', 'E12000008', 'E12000009', 'W92000004', 'S92000003', 'N92000002')",
            name=op.f('ck_dealers_region_code'),
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f('ck_dealers_slug_format')
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'suspended')",
            name=op.f('ck_dealers_status'),
        ),
        sa.CheckConstraint(
            '(latitude IS NULL) = (longitude IS NULL)', name=op.f('ck_dealers_coordinates_paired')
        ),
        sa.CheckConstraint('latitude BETWEEN -90 AND 90', name=op.f('ck_dealers_latitude_range')),
        sa.CheckConstraint(
            'longitude BETWEEN -180 AND 180', name=op.f('ck_dealers_longitude_range')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_dealers')),
        sa.UniqueConstraint('id', 'is_demo', name=op.f('uq_dealers_id_is_demo')),
        sa.UniqueConstraint('slug', name=op.f('uq_dealers_slug')),
    )
    op.create_table(
        'listings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('dealer_id', sa.Uuid(), nullable=False),
        sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('status', sa.String(length=16), server_default='draft', nullable=False),
        sa.Column(
            'moderation_status', sa.String(length=16), server_default='clear', nullable=False
        ),
        sa.Column('make_id', sa.Uuid(), nullable=True),
        sa.Column('model_id', sa.Uuid(), nullable=True),
        sa.Column('variant', sa.String(length=80), nullable=True),
        sa.Column('year', sa.SmallInteger(), nullable=True),
        sa.Column('registration_date', sa.Date(), nullable=True),
        sa.Column('mileage', sa.Integer(), nullable=True),
        sa.Column('price_pence', sa.Integer(), nullable=True),
        sa.Column('body_type', sa.String(length=16), nullable=True),
        sa.Column('fuel_type', sa.String(length=16), nullable=True),
        sa.Column('transmission', sa.String(length=16), nullable=True),
        sa.Column('colour', sa.String(length=16), nullable=True),
        sa.Column('engine_size_cc', sa.SmallInteger(), nullable=True),
        sa.Column('doors', sa.SmallInteger(), nullable=True),
        sa.Column('seats', sa.SmallInteger(), nullable=True),
        sa.Column('owners', sa.SmallInteger(), nullable=True),
        sa.Column('vrm', sa.String(length=7), nullable=True),
        sa.Column('title', sa.String(length=160), server_default='', nullable=False),
        sa.Column('ulez_compliant', sa.Boolean(), nullable=True),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column(
            'specs',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column('specs_version', sa.SmallInteger(), server_default='1', nullable=False),
        sa.Column('latitude', sa.Double(), nullable=True),
        sa.Column('longitude', sa.Double(), nullable=True),
        sa.Column('listed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('photo_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sold_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)",
            name=op.f('ck_listings_archived_iff_archived_at'),
        ),
        sa.CheckConstraint(
            "body_type IN ('hatchback', 'saloon', 'estate', 'suv', 'coupe', 'convertible', 'mpv', 'pickup', 'van')",
            name=op.f('ck_listings_body_type'),
        ),
        sa.CheckConstraint(
            "colour IN ('black', 'white', 'silver', 'grey', 'blue', 'red', 'green', 'yellow', 'orange', 'brown', 'beige', 'gold', 'purple', 'bronze', 'other')",
            name=op.f('ck_listings_colour'),
        ),
        sa.CheckConstraint(
            "fuel_type IN ('petrol', 'diesel', 'hybrid', 'plug_in_hybrid', 'electric', 'other')",
            name=op.f('ck_listings_fuel_type'),
        ),
        sa.CheckConstraint("jsonb_typeof(specs) = 'object'", name=op.f('ck_listings_specs_object')),
        sa.CheckConstraint(
            "moderation_status IN ('clear', 'held', 'hidden', 'removed')",
            name=op.f('ck_listings_moderation_status'),
        ),
        sa.CheckConstraint(
            "status <> 'sold' OR sold_at IS NOT NULL", name=op.f('ck_listings_sold_has_sold_at')
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'archived') OR published_at IS NOT NULL",
            name=op.f('ck_listings_published_has_published_at'),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'reserved', 'sold', 'archived')",
            name=op.f('ck_listings_status'),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'archived') OR (make_id IS NOT NULL AND model_id IS NOT NULL AND year IS NOT NULL AND registration_date IS NOT NULL AND mileage IS NOT NULL AND price_pence IS NOT NULL AND body_type IS NOT NULL AND fuel_type IS NOT NULL AND transmission IS NOT NULL AND ulez_compliant IS NOT NULL AND char_length(title) > 0)",
            name=op.f('ck_listings_publish_complete'),
        ),
        sa.CheckConstraint(
            "transmission IN ('manual', 'automatic')", name=op.f('ck_listings_transmission')
        ),
        sa.CheckConstraint("vrm ~ '^[A-Z0-9]{2,7}$'", name=op.f('ck_listings_vrm_normalised')),
        sa.CheckConstraint(
            '(latitude IS NULL) = (longitude IS NULL)', name=op.f('ck_listings_coordinates_paired')
        ),
        sa.CheckConstraint(
            'char_length(description) <= 5000', name=op.f('ck_listings_description_length')
        ),
        sa.CheckConstraint('doors BETWEEN 1 AND 7', name=op.f('ck_listings_doors_range')),
        sa.CheckConstraint(
            'engine_size_cc BETWEEN 0 AND 10000', name=op.f('ck_listings_engine_size_cc_range')
        ),
        sa.CheckConstraint('latitude BETWEEN -90 AND 90', name=op.f('ck_listings_latitude_range')),
        sa.CheckConstraint(
            'listed_at IS NULL OR published_at IS NOT NULL',
            name=op.f('ck_listings_listed_has_published_at'),
        ),
        sa.CheckConstraint(
            'longitude BETWEEN -180 AND 180', name=op.f('ck_listings_longitude_range')
        ),
        sa.CheckConstraint('mileage BETWEEN 0 AND 1000000', name=op.f('ck_listings_mileage_range')),
        sa.CheckConstraint('owners BETWEEN 0 AND 99', name=op.f('ck_listings_owners_range')),
        sa.CheckConstraint('photo_count >= 0', name=op.f('ck_listings_photo_count_range')),
        sa.CheckConstraint(
            'price_pence BETWEEN 10000 AND 500000000', name=op.f('ck_listings_price_pence_range')
        ),
        sa.CheckConstraint('seats BETWEEN 1 AND 9', name=op.f('ck_listings_seats_range')),
        sa.CheckConstraint('specs_version >= 1', name=op.f('ck_listings_specs_version_range')),
        sa.CheckConstraint('year BETWEEN 1900 AND 2100', name=op.f('ck_listings_year_range')),
        sa.ForeignKeyConstraint(
            ['dealer_id', 'is_demo'],
            ['dealers.id', 'dealers.is_demo'],
            name=op.f('fk_listings_dealer_id_dealers'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['make_id', 'model_id'],
            ['vehicle_models.make_id', 'vehicle_models.id'],
            name=op.f('fk_listings_make_id_vehicle_models'),
        ),
        sa.ForeignKeyConstraint(['make_id'], ['makes.id'], name=op.f('fk_listings_make_id_makes')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_listings')),
    )
    op.create_index(
        'ix_listings_dealer_id_status_updated_at',
        'listings',
        ['dealer_id', 'status', 'updated_at'],
        unique=False,
    )
    op.create_index(
        'ix_listings_make_id_model_id', 'listings', ['make_id', 'model_id'], unique=False
    )
    op.create_index(
        'ix_listings_visible_latitude_longitude',
        'listings',
        ['latitude', 'longitude'],
        unique=False,
        postgresql_where=sa.text(_VISIBLE),
    )
    op.create_index(
        'ix_listings_visible_listed_at',
        'listings',
        ['listed_at'],
        unique=False,
        postgresql_where=sa.text(_VISIBLE),
    )
    op.create_index(
        'ix_listings_visible_make_id_model_id_price_pence',
        'listings',
        ['make_id', 'model_id', 'price_pence'],
        unique=False,
        postgresql_where=sa.text(_VISIBLE),
    )
    op.create_index(
        'ix_listings_vrm_live',
        'listings',
        ['vrm'],
        unique=False,
        postgresql_where=sa.text("vrm IS NOT NULL AND status IN ('active', 'reserved')"),
    )


def downgrade() -> None:
    # Dropping the tables drops their indexes; the unique key goes last, once the listings
    # FK that depends on it is gone.
    op.drop_table('listings')
    op.drop_table('dealers')
    op.drop_constraint(op.f('uq_vehicle_models_make_id_id'), 'vehicle_models', type_='unique')
