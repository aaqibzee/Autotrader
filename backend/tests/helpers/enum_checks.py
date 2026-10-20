from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import Connection, text

from app.db.checks import EnumCheck

# pg_get_constraintdef renders each allowed value as a quoted literal with a cast, e.g.
# `ARRAY['petrol'::text, ...]` or `'petrol'::character varying`.
_LITERAL = re.compile(r"'((?:[^']|'')*)'::")


def enum_check_drift(connection: Connection, checks: Iterable[EnumCheck]) -> list[str]:
    """Each enum CHECK whose live database definition disagrees with its StrEnum."""
    problems: list[str] = []
    for check in checks:
        row = connection.execute(
            text(
                'SELECT pg_get_constraintdef(c.oid), c.convalidated FROM pg_constraint c '
                'JOIN pg_class t ON t.oid = c.conrelid '
                "WHERE c.contype = 'c' AND c.conname = :name AND t.relname = :table"
            ),
            {'name': check.name, 'table': check.table},
        ).one_or_none()
        if row is None:
            problems.append(f'{check.name}: missing from the database')
            continue
        definition, validated = row
        allowed = {value.replace("''", "'") for value in _LITERAL.findall(definition)}
        expected = {member.value for member in check.enum}
        if allowed != expected:
            problems.append(
                f'{check.name}: database allows {sorted(allowed)}, '
                f'{check.enum.__name__} has {sorted(expected)}'
            )
        if not validated:
            problems.append(f'{check.name}: NOT VALID (existing rows were never checked)')
    return problems
