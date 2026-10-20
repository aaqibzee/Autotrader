"""Enum-backed CHECK constraints (Feature 02 §1).

Enumerations are `text` columns with a named CHECK listing the allowed values, backed by
one `StrEnum`. `alembic check` cannot see a CHECK's body, so a CHECK and its enum can
drift silently; every constraint built here is tagged in `info` so the drift test can
find all of them by walking the metadata and compare each against `pg_constraint`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import CheckConstraint, MetaData

_INFO_KEY = 'enum_check'


@dataclass(frozen=True)
class EnumCheck:
    table: str
    column: str
    enum: type[StrEnum]
    array: bool

    @property
    def name(self) -> str:
        return f'ck_{self.table}_{self.column}'


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def enum_check_sql(column: str, enum: type[StrEnum], *, array: bool = False) -> str:
    values = ', '.join(_sql_literal(member.value) for member in enum)
    if array:
        # Every element must be a member; `<@` is "is contained by".
        return f'{column} <@ ARRAY[{values}]::text[]'
    return f'{column} IN ({values})'


def enum_check(column: str, enum: type[StrEnum], *, array: bool = False) -> CheckConstraint:
    """A CHECK named `ck_<table>_<column>` (via the metadata naming convention)."""
    return CheckConstraint(
        enum_check_sql(column, enum, array=array),
        name=column,
        info={_INFO_KEY: (column, enum, array)},
    )


def enum_checks(metadata: MetaData) -> Iterator[EnumCheck]:
    """Every enum-backed CHECK declared on `metadata`'s tables, in a stable order."""
    for table in metadata.sorted_tables:
        tagged = [c.info[_INFO_KEY] for c in table.constraints if _INFO_KEY in c.info]
        for column, enum, array in sorted(tagged, key=lambda entry: entry[0]):
            yield EnumCheck(table=table.name, column=column, enum=enum, array=array)


def replace_enum_check(
    table: str, column: str, enum: type[StrEnum], *, array: bool = False
) -> None:
    """Migration helper: swap an enum CHECK for one matching `enum`, without downtime.

    The new constraint is added `NOT VALID` (enforced for new writes, no table scan,
    brief lock), then validated in its own transaction, which scans the table holding
    only a SHARE UPDATE EXCLUSIVE lock so reads and writes continue. If validation
    fails, the NOT VALID constraint stays and a rerun replaces it again.
    """
    from alembic import op

    name = f'ck_{table}_{column}'
    op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}')
    op.execute(
        f'ALTER TABLE {table} ADD CONSTRAINT {name} '
        f'CHECK ({enum_check_sql(column, enum, array=array)}) NOT VALID'
    )
    with op.get_context().autocommit_block():
        op.execute(f'ALTER TABLE {table} VALIDATE CONSTRAINT {name}')
