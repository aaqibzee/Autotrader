"""feature flag names must be normalised

Revision ID: d4dbde7c7413
Revises: 20261015_0001
Create Date: 2026-10-19 13:29:16.238880
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4dbde7c7413'
down_revision: Union[str, None] = '20261015_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Autogenerate does not detect CHECK constraints; this body is hand-written.
def upgrade() -> None:
    # Bring any pre-existing rows into the form is_enabled() queries for.
    op.execute("UPDATE feature_flags SET name = lower(replace(name, '-', '_'))")
    op.create_check_constraint(
        op.f('ck_feature_flags_name_normalised'),
        'feature_flags',
        sa.text(r"name ~ '^[a-z0-9]+(_[a-z0-9]+)*$'"),
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_feature_flags_name_normalised'), 'feature_flags', type_='check')