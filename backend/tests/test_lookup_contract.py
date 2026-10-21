"""The lookup normal form is shared with the web client (Feature 03 slice 3.8).

`ops/contracts/lookup-normal-form.json` holds the cases; web/lib/format/lookup.test.ts
reads the same file, so a change to either implementation that the other does not make
fails one of the two suites.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.taxonomy.naming import normalise_lookup

CONTRACT = Path(__file__).resolve().parents[2] / 'ops' / 'contracts' / 'lookup-normal-form.json'
CASES = json.loads(CONTRACT.read_text(encoding='utf-8'))['cases']


def test_contract_has_cases() -> None:
    assert len(CASES) >= 10


@pytest.mark.parametrize(('raw', 'expected'), CASES)
def test_normalise_lookup_matches_the_shared_contract(raw: str, expected: str) -> None:
    assert normalise_lookup(raw) == expected
