"""taxonomy aliases must be in lookup normal form

Revision ID: 4c3a08d3e71a
Revises: e1cff08ecd05
Create Date: 2026-10-20 08:00:50.990176
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '4c3a08d3e71a'
down_revision: str | None = 'e1cff08ecd05'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Autogenerate does not detect CHECK changes on existing tables; this body is hand-written.
# Literal on purpose (a migration is a snapshot): the output of naming.normalise_lookup.
_NORMALISED = "alias ~ '^[A-Z0-9]+$'"
_UPPER_CASE = 'alias = upper(alias)'
_TABLES = ('make_aliases', 'model_aliases')


def upgrade() -> None:
    for table in _TABLES:
        # Aliases are owned by load_taxonomy, which recreates them on the next deploy, so a
        # row in the old form is dropped rather than rewritten (rewriting could collide).
        op.execute(f"DELETE FROM {table} WHERE alias !~ '^[A-Z0-9]+$'")
        op.drop_constraint(op.f(f'ck_{table}_alias_upper_case'), table, type_='check')
        op.create_check_constraint(
            op.f(f'ck_{table}_alias_normalised'), table, sa.text(_NORMALISED)
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(op.f(f'ck_{table}_alias_normalised'), table, type_='check')
        op.create_check_constraint(
            op.f(f'ck_{table}_alias_upper_case'), table, sa.text(_UPPER_CASE)
        )
