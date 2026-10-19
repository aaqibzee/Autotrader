from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, event
from sqlalchemy.orm import Session


class QueryCountExceeded(AssertionError):
    pass


@contextmanager
def assert_max_queries(
    bind: Engine | Connection | Session,
    maximum: int,
) -> Iterator[list[str]]:
    if maximum < 0:
        raise ValueError('maximum query count must be non-negative')

    target: Engine | Connection
    if isinstance(bind, Session):
        target = bind.get_bind()
    else:
        target = bind

    statements: list[str] = []

    def count_statement(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(target, 'before_cursor_execute', count_statement)
    try:
        yield statements
        if len(statements) > maximum:
            raise QueryCountExceeded(
                f'Expected at most {maximum} SQL statements, observed {len(statements)}.'
            )
    finally:
        event.remove(target, 'before_cursor_execute', count_statement)
