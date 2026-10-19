from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from tests.helpers.query_count import QueryCountExceeded, assert_max_queries


def test_query_budget_allows_statements_within_limit() -> None:
    engine = create_engine('sqlite://')
    with engine.connect() as connection, assert_max_queries(connection, 1) as statements:
        connection.execute(text('SELECT 1'))
    assert len(statements) == 1
    engine.dispose()


def test_query_budget_fails_when_statement_limit_is_exceeded() -> None:
    engine = create_engine('sqlite://')
    with (
        engine.connect() as connection,
        pytest.raises(QueryCountExceeded, match='observed 2'),
        assert_max_queries(connection, 1),
    ):
        connection.execute(text('SELECT 1'))
        connection.execute(text('SELECT 2'))
    engine.dispose()
