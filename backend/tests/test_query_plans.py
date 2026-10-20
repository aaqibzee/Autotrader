"""The nightly query-plan check and the invariant CLI (Feature 02 slice 2.9).

The real budget (50 ms over 50,000 listings) is measured by the nightly job; these tests
prove the checker can fail: on a sequential scan, a slow median, an empty result.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from uuid import UUID

import pytest
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import sync_engine
from app.modules.listings.demo_seed import seed_demo
from app.modules.listings.services import InvariantMismatch
from app.modules.taxonomy.dataset import read_taxonomy
from app.modules.taxonomy.services import load_taxonomy
from scripts import check_query_plans as plans
from scripts import verify_listings
from tests.test_demo_seed import NOW, TODAY


def _plan(node: dict[str, Any], execution_ms: float = 1.0) -> list[dict[str, Any]]:
    return [{'Plan': node, 'Execution Time': execution_ms}]


SORT_OVER_SEQ_SCAN = {
    'Node Type': 'Sort',
    'Actual Rows': 10,
    'Plans': [
        {'Node Type': 'Hash Join', 'Plans': [
            {'Node Type': 'Seq Scan', 'Relation Name': 'makes'},
            {'Node Type': 'Seq Scan', 'Relation Name': 'listings'},
        ]},
    ],
}  # fmt: skip
INDEXED = {
    'Node Type': 'Bitmap Heap Scan',
    'Relation Name': 'listings',
    'Actual Rows': 10,
    'Plans': [{'Node Type': 'Bitmap Index Scan', 'Index Name': 'ix_listings_visible'}],
}


def test_a_nested_sequential_scan_of_listings_is_found() -> None:
    # A seq scan of a small lookup table (makes) is fine; of listings it is not.
    assert plans.plan_problems(_plan(SORT_OVER_SEQ_SCAN)) == ['sequential scan on listings']
    assert plans.plan_problems(_plan(INDEXED)) == []


@pytest.mark.parametrize(
    ('runs', 'problem'),
    [
        ([_plan(INDEXED, 5.0)] * 3, None),
        ([_plan(INDEXED, 5.0), _plan(INDEXED, 80.0), _plan(INDEXED, 90.0)], 'median execution'),
        ([_plan(INDEXED, 200.0), _plan(INDEXED, 5.0), _plan(INDEXED, 6.0)], None),  # one outlier
        ([_plan({**INDEXED, 'Actual Rows': 0})] * 3, 'no rows'),
        ([_plan(INDEXED), _plan(SORT_OVER_SEQ_SCAN), _plan(INDEXED)], 'sequential scan'),
    ],
)
def test_check_query_rules(
    monkeypatch: pytest.MonkeyPatch, runs: list[list[dict[str, Any]]], problem: str | None
) -> None:
    queue = iter(runs)
    monkeypatch.setattr(plans, 'explain', lambda session, query: next(queue))
    result = plans.check_query(None, 'q', None, budget_ms=50, runs=3)  # type: ignore[arg-type]
    if problem is None:
        assert result.problems == []
    else:
        assert len(result.problems) == 1 and problem in result.problems[0]


@pytest.fixture
def session() -> Generator[Session, None, None]:
    with Session(sync_engine) as session:
        try:
            load_taxonomy(session, read_taxonomy())
            seed_demo(session, listings=400, today=TODAY, now=NOW)
            yield session
        finally:
            session.rollback()


def test_the_registered_query_runs_under_explain_analyze(session: Session) -> None:
    # 400 rows is too few for the planner to prefer an index on its own; forcing it here
    # checks the plumbing (binding, JSON, row count), and the nightly job checks the plan.
    session.execute(text('SET LOCAL enable_seqscan = off'))
    [result] = plans.check_all(session, budget_ms=1_000, runs=2)
    assert result.name == 'visible_ford_5k_10k_by_price'
    assert result.rows > 0
    assert result.problems == []


def test_the_check_fails_a_real_sequential_scan(session: Session) -> None:
    # Negative proof on a real plan: with index scans off, the checker must object.
    for setting in ('enable_indexscan', 'enable_bitmapscan', 'enable_indexonlyscan'):
        session.execute(text(f'SET LOCAL {setting} = off'))
    [result] = plans.check_all(session, budget_ms=1_000, runs=1)
    assert result.problems == ['sequential scan on listings']


def test_cli_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plans, 'logger', structlog.testing.CapturingLogger())
    good = plans.PlanResult('q', 1.0, 5)
    bad = plans.PlanResult('q', 1.0, 5, ['sequential scan on listings'])
    for results, code in (([good], 0), ([good, bad], 1)):
        monkeypatch.setattr(plans, 'check_all', lambda session, results=results, **_: results)
        assert plans.main([]) == code

    def no_taxonomy(session: Session, **_: Any) -> Any:
        raise LookupError('no Ford in the taxonomy')

    monkeypatch.setattr(plans, 'check_all', no_taxonomy)
    assert plans.main([]) == 1


def test_verify_listings_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = structlog.testing.CapturingLogger()
    monkeypatch.setattr(verify_listings, 'logger', captured)
    monkeypatch.setattr(verify_listings, 'verify_listing_invariants', lambda session: [])
    assert verify_listings.main() == 0

    mismatch = InvariantMismatch(UUID(int=7), 'title', 'stored', 'expected')
    monkeypatch.setattr(verify_listings, 'verify_listing_invariants', lambda session: [mismatch])
    assert verify_listings.main() == 1
    assert captured.calls[-1].args == ('listing_invariants_failed',)
    assert captured.calls[-1].kwargs['first'] == [
        {'listing_id': str(UUID(int=7)), 'column': 'title'}
    ]
