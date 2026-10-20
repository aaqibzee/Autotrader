"""The bundled taxonomy CSVs: reading and validating them, with no database involved.

Validation runs over the whole dataset before the loader writes anything, so a bad row
aborts the load instead of leaving the taxonomy half-applied. The same function backs
the data-quality tests on the committed CSVs, so a bad PR fails CI without a database.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.modules.taxonomy.enums import BodyType
from app.modules.taxonomy.models import SLUG_PATTERN
from app.modules.taxonomy.naming import normalise_lookup

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / 'data' / 'taxonomy'
NAME_MAX_LENGTH = 80

_SLUG = re.compile(SLUG_PATTERN)
_BODY_TYPES = frozenset(BodyType)
_BOOLEANS = {'true': True, 'false': False}


class TaxonomyDataError(ValueError):
    """The dataset is invalid; `problems` lists every reason, not just the first."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__('; '.join(problems))
        self.problems = problems


@dataclass(frozen=True)
class MakeRow:
    slug: str
    name: str
    is_popular: bool


@dataclass(frozen=True)
class ModelRow:
    make_slug: str
    slug: str
    name: str
    body_types: tuple[str, ...]


@dataclass(frozen=True)
class AliasRow:
    """An external spelling. `model_slug` empty means the alias names the make itself."""

    make_slug: str
    model_slug: str
    alias: str


@dataclass(frozen=True)
class TaxonomyData:
    makes: tuple[MakeRow, ...]
    models: tuple[ModelRow, ...]
    aliases: tuple[AliasRow, ...]


def _read_rows(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != columns:
            raise TaxonomyDataError(
                [f'{path.name}: header must be {",".join(columns)}, got {reader.fieldnames}']
            )
        return [{key: (value or '').strip() for key, value in row.items()} for row in reader]


def read_taxonomy(directory: Path = DEFAULT_DATA_DIR) -> TaxonomyData:
    makes = _read_rows(directory / 'makes.csv', ('slug', 'name', 'is_popular'))
    models = _read_rows(directory / 'models.csv', ('make_slug', 'slug', 'name', 'body_types'))
    aliases = _read_rows(directory / 'aliases.csv', ('make_slug', 'model_slug', 'alias'))

    problems: list[str] = []
    make_rows: list[MakeRow] = []
    for line, row in enumerate(makes, start=2):
        is_popular = _BOOLEANS.get(row['is_popular'].lower())
        if is_popular is None:
            problems.append(f'makes.csv:{line}: is_popular must be true or false')
            continue
        make_rows.append(MakeRow(slug=row['slug'], name=row['name'], is_popular=is_popular))
    if problems:
        raise TaxonomyDataError(problems)

    return TaxonomyData(
        makes=tuple(make_rows),
        models=tuple(
            ModelRow(
                make_slug=row['make_slug'],
                slug=row['slug'],
                name=row['name'],
                body_types=tuple(part.strip() for part in row['body_types'].split('|')),
            )
            for row in models
        ),
        aliases=tuple(
            AliasRow(make_slug=row['make_slug'], model_slug=row['model_slug'], alias=row['alias'])
            for row in aliases
        ),
    )


def make_lookup_keys(make: MakeRow, aliases: Iterable[AliasRow]) -> set[str]:
    """Every normalised spelling that resolves to `make`: its name, its slug, its aliases."""
    keys = {normalise_lookup(make.name), normalise_lookup(make.slug)}
    keys.update(normalise_lookup(a.alias) for a in aliases if not a.model_slug)
    keys.discard('')
    return keys


def model_lookup_keys(model: ModelRow, aliases: Iterable[AliasRow]) -> set[str]:
    keys = {normalise_lookup(model.name), normalise_lookup(model.slug)}
    keys.update(normalise_lookup(a.alias) for a in aliases)
    keys.discard('')
    return keys


def _check_name_and_slug(where: str, name: str, slug: str, problems: list[str]) -> None:
    if not name:
        problems.append(f'{where}: name is empty')
    elif len(name) > NAME_MAX_LENGTH:
        problems.append(f'{where}: name is longer than {NAME_MAX_LENGTH} characters')
    elif not normalise_lookup(name):
        problems.append(f'{where}: name {name!r} has no letters or digits')
    if not _SLUG.fullmatch(slug) or len(slug) > NAME_MAX_LENGTH:
        problems.append(f'{where}: slug {slug!r} is not a valid slug')


def validate_taxonomy(data: TaxonomyData) -> list[str]:
    """Every problem in the dataset; an empty list means it is safe to load."""
    problems: list[str] = []

    make_slugs: set[str] = set()
    for make in data.makes:
        where = f'make {make.slug!r}'
        _check_name_and_slug(where, make.name, make.slug, problems)
        if make.slug in make_slugs:
            problems.append(f'{where}: duplicate slug')
        make_slugs.add(make.slug)

    model_slugs: set[tuple[str, str]] = set()
    for model in data.models:
        where = f'model {model.make_slug}/{model.slug}'
        _check_name_and_slug(where, model.name, model.slug, problems)
        if model.make_slug not in make_slugs:
            problems.append(f'{where}: unknown make {model.make_slug!r}')
        if (model.make_slug, model.slug) in model_slugs:
            problems.append(f'{where}: duplicate slug within the make')
        model_slugs.add((model.make_slug, model.slug))
        if not model.body_types or model.body_types == ('',):
            problems.append(f'{where}: needs at least one body type')
        for body_type in model.body_types:
            if body_type and body_type not in _BODY_TYPES:
                problems.append(f'{where}: unknown body type {body_type!r}')

    aliases_by_target: dict[tuple[str, str], list[AliasRow]] = defaultdict(list)
    for alias in data.aliases:
        where = f'alias {alias.alias!r}'
        if not normalise_lookup(alias.alias):
            problems.append(f'{where}: has no letters or digits')
        elif len(normalise_lookup(alias.alias)) > NAME_MAX_LENGTH:
            problems.append(f'{where}: longer than {NAME_MAX_LENGTH} characters once normalised')
        if alias.make_slug not in make_slugs:
            problems.append(f'{where}: unknown make {alias.make_slug!r}')
        elif alias.model_slug and (alias.make_slug, alias.model_slug) not in model_slugs:
            problems.append(f'{where}: unknown model {alias.make_slug}/{alias.model_slug}')
        aliases_by_target[(alias.make_slug, alias.model_slug)].append(alias)

    # A spelling may resolve to only one target: makes globally, models within their make.
    make_owner: dict[str, str] = {}
    for make in data.makes:
        for key in make_lookup_keys(make, aliases_by_target[(make.slug, '')]):
            owner = make_owner.setdefault(key, make.slug)
            if owner != make.slug:
                problems.append(f'{key!r} resolves to both make {owner!r} and {make.slug!r}')

    model_owner: dict[tuple[str, str], str] = {}
    for model in data.models:
        for key in model_lookup_keys(model, aliases_by_target[(model.make_slug, model.slug)]):
            owner = model_owner.setdefault((model.make_slug, key), model.slug)
            if owner != model.slug:
                problems.append(
                    f'{key!r} resolves to both {model.make_slug}/{owner} and '
                    f'{model.make_slug}/{model.slug}'
                )

    return problems
