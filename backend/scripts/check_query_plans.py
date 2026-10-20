"""Fail when a budgeted listing query stops using an index or gets slow (Feature 02 §8).

    uv run python -m scripts.check_query_plans [--budget-ms 50] [--runs 3]

Run by the nightly job over the seeded perf dataset (50,000 listings). Each query in
`QUERIES` runs under `EXPLAIN (ANALYZE, FORMAT JSON)` `--runs` times after an `ANALYZE` of
its tables. A query fails if any run's plan sequentially scans `listings`, if its median
execution time is over budget, or if it returns no rows (a pass over an empty result
proves nothing). Feature 07 adds its search queries to `QUERIES`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import Select, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.telemetry import configure_logging
from app.db.session import SyncSessionLocal
from app.models import Listing, Make
from app.modules.listings.visibility import publicly_visible

DEFAULT_BUDGET_MS = 50.0
DEFAULT_RUNS = 3
ANALYZED_TABLES = ('listings', 'dealers', 'makes', 'vehicle_models')
GUARDED_RELATIONS = frozenset({'listings'})

logger = structlog.get_logger('scripts.check_query_plans')


def _ford_between_5k_and_10k_by_price(session: Session) -> Select[Any]:
    ford = session.scalar(select(Make.id).where(Make.slug == 'ford'))
    if ford is None:
        raise LookupError('no Ford in the taxonomy: run scripts.load_taxonomy first')
    return (
        select(Listing.id, Listing.title, Listing.price_pence)
        .where(publicly_visible(), Listing.make_id == ford)
        .where(Listing.price_pence.between(500_000, 1_000_000))
        .order_by(Listing.price_pence)
    )


# name -> builder. Feature 07 appends its search queries here (design §8, slice 2.9).
QUERIES: dict[str, Callable[[Session], Select[Any]]] = {
    'visible_ford_5k_10k_by_price': _ford_between_5k_and_10k_by_price,
}


@dataclass(frozen=True)
class PlanResult:
    name: str
    execution_ms: float
    rows: int
    problems: list[str] = field(default_factory=list)


def _nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get('Plans', ()):
        yield from _nodes(child)


def plan_problems(explained: list[dict[str, Any]]) -> list[str]:
    """Sequential scans of a guarded table in one `EXPLAIN (FORMAT JSON)` result."""
    return [
        f'sequential scan on {node["Relation Name"]}'
        for node in _nodes(explained[0]['Plan'])
        if node['Node Type'] == 'Seq Scan' and node.get('Relation Name') in GUARDED_RELATIONS
    ]


def explain(session: Session, query: Select[Any]) -> list[dict[str, Any]]:
    """`EXPLAIN (ANALYZE, FORMAT JSON)` of `query`, bound the way the app binds it."""
    compiled = query.compile(
        dialect=postgresql.psycopg.dialect(),  # type: ignore[no-untyped-call]
        compile_kwargs={'render_postcompile': True},
    )
    raw = session.connection().exec_driver_sql(
        f'EXPLAIN (ANALYZE, FORMAT JSON) {compiled}', compiled.params
    )
    value = raw.scalar_one()
    return json.loads(value) if isinstance(value, str) else value


def check_query(
    session: Session, name: str, query: Select[Any], *, budget_ms: float, runs: int
) -> PlanResult:
    plans = [explain(session, query) for _ in range(runs)]
    problems = sorted({problem for plan in plans for problem in plan_problems(plan)})
    execution_ms = statistics.median(plan[0]['Execution Time'] for plan in plans)
    rows = int(plans[-1][0]['Plan']['Actual Rows'])
    if execution_ms > budget_ms:
        problems.append(f'median execution {execution_ms:.1f} ms is over {budget_ms:g} ms')
    if rows == 0:
        problems.append('returned no rows, so the plan proves nothing')
    return PlanResult(name, round(execution_ms, 2), rows, problems)


def check_all(
    session: Session, *, budget_ms: float = DEFAULT_BUDGET_MS, runs: int = DEFAULT_RUNS
) -> list[PlanResult]:
    for table in ANALYZED_TABLES:  # fresh statistics: a just-seeded table has none
        session.connection().exec_driver_sql(f'ANALYZE {table}')
    return [
        check_query(session, name, build(session), budget_ms=budget_ms, runs=runs)
        for name, build in QUERIES.items()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Check listing query plans and timings.')
    parser.add_argument('--budget-ms', type=float, default=DEFAULT_BUDGET_MS)
    parser.add_argument('--runs', type=int, default=DEFAULT_RUNS)
    arguments = parser.parse_args(argv)

    configure_logging()
    try:
        with SyncSessionLocal.begin() as session:
            results = check_all(session, budget_ms=arguments.budget_ms, runs=arguments.runs)
    except LookupError as error:
        logger.error('query_plan_check_failed', reason=str(error))
        return 1
    for result in results:
        log = logger.error if result.problems else logger.info
        log(
            'query_plan_checked',
            query=result.name,
            execution_ms=result.execution_ms,
            rows=result.rows,
            problems=result.problems,
        )
    return 1 if any(result.problems for result in results) else 0


if __name__ == '__main__':
    sys.exit(main())
