"""vehicle taxonomy tables

Revision ID: e1cff08ecd05
Revises: d4dbde7c7413
Create Date: 2026-10-19 21:14:14.599322
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'e1cff08ecd05'
down_revision: str | None = 'd4dbde7c7413'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# CHECK bodies are literal on purpose: a migration is a snapshot, so it must not import
# the live StrEnum (a later enum change would rewrite history). The enum-drift test keeps
# the database and the enums in agreement; changes go through replace_enum_check.
_SLUG_FORMAT = "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'"
_ALIAS_UPPER_CASE = 'alias = upper(alias)'
_BODY_TYPES = (
    "body_types <@ ARRAY['hatchback', 'saloon', 'estate', 'suv', 'coupe', 'convertible', "
    "'mpv', 'pickup', 'van']::text[]"
)


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        'makes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('is_popular', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        *_timestamps(),
        sa.CheckConstraint(_SLUG_FORMAT, name=op.f('ck_makes_slug_format')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_makes')),
        sa.UniqueConstraint('slug', name=op.f('uq_makes_slug')),
    )
    op.create_table(
        'make_aliases',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('alias', sa.String(length=80), nullable=False),
        sa.Column('make_id', sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(_ALIAS_UPPER_CASE, name=op.f('ck_make_aliases_alias_upper_case')),
        sa.ForeignKeyConstraint(
            ['make_id'],
            ['makes.id'],
            name=op.f('fk_make_aliases_make_id_makes'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_make_aliases')),
        sa.UniqueConstraint('alias', name=op.f('uq_make_aliases_alias')),
    )
    op.create_index(op.f('ix_make_aliases_make_id'), 'make_aliases', ['make_id'], unique=False)
    op.create_table(
        'vehicle_models',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('make_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column(
            'body_types',
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        *_timestamps(),
        sa.CheckConstraint(_BODY_TYPES, name=op.f('ck_vehicle_models_body_types')),
        sa.CheckConstraint(_SLUG_FORMAT, name=op.f('ck_vehicle_models_slug_format')),
        sa.ForeignKeyConstraint(
            ['make_id'], ['makes.id'], name=op.f('fk_vehicle_models_make_id_makes')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_vehicle_models')),
        sa.UniqueConstraint('make_id', 'slug', name=op.f('uq_vehicle_models_make_id_slug')),
    )
    op.create_table(
        'model_aliases',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('alias', sa.String(length=80), nullable=False),
        sa.Column('model_id', sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(_ALIAS_UPPER_CASE, name=op.f('ck_model_aliases_alias_upper_case')),
        sa.ForeignKeyConstraint(
            ['model_id'],
            ['vehicle_models.id'],
            name=op.f('fk_model_aliases_model_id_vehicle_models'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_model_aliases')),
        sa.UniqueConstraint('model_id', 'alias', name=op.f('uq_model_aliases_model_id_alias')),
    )


def downgrade() -> None:
    op.drop_table('model_aliases')
    op.drop_table('vehicle_models')
    op.drop_index(op.f('ix_make_aliases_make_id'), table_name='make_aliases')
    op.drop_table('make_aliases')
    op.drop_table('makes')
