"""Taxonomy loading and lookup (Feature 02 §1).

`load_taxonomy` makes the database match the bundled CSVs. It runs on every deploy, so it
is idempotent and conservative: makes and models are matched by slug, never deleted (a
row missing from the CSV is deactivated, so listings and URLs that reference it keep
working), and a slug never changes once created.

Aliases are owned entirely by the loader. Besides the CSV's explicit aliases, every
make's and model's own name and slug are stored as aliases in normal form, so the
resolvers are a single indexed lookup instead of three.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, insert, select, tuple_
from sqlalchemy.orm import Session

from app.db.locks import AdvisoryLock, hold_advisory_lock
from app.db.uuid7 import uuid7
from app.modules.taxonomy.dataset import (
    NAME_MAX_LENGTH,
    AliasRow,
    TaxonomyData,
    TaxonomyDataError,
    make_lookup_keys,
    model_lookup_keys,
    validate_taxonomy,
)
from app.modules.taxonomy.models import Make, MakeAlias, ModelAlias, VehicleModel
from app.modules.taxonomy.naming import normalise_lookup, slugify

__all__ = [
    'CatalogueModel',
    'LoadReport',
    'SlugChangeError',
    'TaxonomyDataError',
    'catalogue',
    'load_taxonomy',
    'make_names',
    'model_names',
    'normalise_lookup',
    'resolve_make',
    'resolve_model',
    'slugify',
]


class SlugChangeError(ValueError):
    """The input would change an existing row's slug, which is immutable."""


@dataclass(frozen=True)
class LoadReport:
    """Row counts over makes and models together; aliases are counted separately."""

    inserted: int = 0
    updated: int = 0
    deactivated: int = 0
    unchanged: int = 0
    aliases_added: int = 0
    aliases_removed: int = 0


@dataclass
class _Counts:
    inserted: int = 0
    updated: int = 0
    deactivated: int = 0
    unchanged: int = 0


def _read_existing_makes(session: Session) -> dict[str, Make]:
    return {make.slug: make for make in session.scalars(select(Make))}


def _check_no_slug_change(where: str, name: str, slug: str, removed: dict[str, str]) -> None:
    """A new slug arriving as an old one disappears under the same name is a slug change."""
    old_slug = removed.get(normalise_lookup(name))
    if old_slug is not None:
        raise SlugChangeError(
            f'{where}: {name!r} would move from slug {old_slug!r} to {slug!r}; slugs are '
            f'immutable, so keep {old_slug!r} and change only the name'
        )


def _sync_makes(session: Session, data: TaxonomyData, counts: _Counts) -> dict[str, UUID]:
    existing = _read_existing_makes(session)
    wanted = {make.slug for make in data.makes}
    removed = {
        normalise_lookup(make.name): slug for slug, make in existing.items() if slug not in wanted
    }

    for row in data.makes:
        make = existing.get(row.slug)
        if make is None:
            _check_no_slug_change('make', row.name, row.slug, removed)
            session.add(Make(id=uuid7(), slug=row.slug, name=row.name, is_popular=row.is_popular))
            counts.inserted += 1
        elif (make.name, make.is_popular, make.is_active) != (row.name, row.is_popular, True):
            make.name, make.is_popular, make.is_active = row.name, row.is_popular, True
            counts.updated += 1
        else:
            counts.unchanged += 1

    for slug, make in existing.items():
        if slug not in wanted and make.is_active:
            make.is_active = False
            counts.deactivated += 1

    session.flush()
    return {make.slug: make.id for make in session.scalars(select(Make))}


def _sync_models(
    session: Session, data: TaxonomyData, make_ids: dict[str, UUID], counts: _Counts
) -> dict[tuple[str, str], UUID]:
    make_slugs = {make_id: slug for slug, make_id in make_ids.items()}
    existing = {
        (make_slugs[model.make_id], model.slug): model
        for model in session.scalars(select(VehicleModel))
    }
    wanted = {(model.make_slug, model.slug) for model in data.models}
    removed = {
        (make_slug, normalise_lookup(model.name)): slug
        for (make_slug, slug), model in existing.items()
        if (make_slug, slug) not in wanted
    }

    for row in data.models:
        model = existing.get((row.make_slug, row.slug))
        body_types = list(row.body_types)
        if model is None:
            removed_in_make = {
                key: slug
                for (make_slug, key), slug in removed.items()
                if make_slug == row.make_slug
            }
            _check_no_slug_change(
                f'model of {row.make_slug!r}', row.name, row.slug, removed_in_make
            )
            session.add(
                VehicleModel(
                    id=uuid7(),
                    make_id=make_ids[row.make_slug],
                    slug=row.slug,
                    name=row.name,
                    body_types=body_types,
                )
            )
            counts.inserted += 1
        elif (model.name, list(model.body_types), model.is_active) != (row.name, body_types, True):
            model.name, model.body_types, model.is_active = row.name, body_types, True
            counts.updated += 1
        else:
            counts.unchanged += 1

    for key, model in existing.items():
        if key not in wanted and model.is_active:
            model.is_active = False
            counts.deactivated += 1

    session.flush()
    return {
        (make_slugs[model.make_id], model.slug): model.id
        for model in session.scalars(select(VehicleModel))
    }


def _sync_make_aliases(
    session: Session,
    data: TaxonomyData,
    aliases: dict[tuple[str, str], list[AliasRow]],
    make_ids: dict[str, UUID],
) -> tuple[int, int]:
    wanted = {
        (key, make_ids[make.slug])
        for make in data.makes
        for key in make_lookup_keys(make, aliases[(make.slug, '')])
    }
    existing = set(session.execute(select(MakeAlias.alias, MakeAlias.make_id)).tuples())
    stale, new = existing - wanted, wanted - existing
    # Deleted first: an alias moving to another make is a delete plus an insert, and the
    # alias column is unique.
    if stale:
        session.execute(
            delete(MakeAlias).where(tuple_(MakeAlias.alias, MakeAlias.make_id).in_(stale))
        )
    if new:
        session.execute(
            insert(MakeAlias),
            [{'id': uuid7(), 'alias': alias, 'make_id': make_id} for alias, make_id in sorted(new)],
        )
    return len(new), len(stale)


def _sync_model_aliases(
    session: Session,
    data: TaxonomyData,
    aliases: dict[tuple[str, str], list[AliasRow]],
    model_ids: dict[tuple[str, str], UUID],
) -> tuple[int, int]:
    wanted = {
        (key, model_ids[(model.make_slug, model.slug)])
        for model in data.models
        for key in model_lookup_keys(model, aliases[(model.make_slug, model.slug)])
    }
    existing = set(session.execute(select(ModelAlias.alias, ModelAlias.model_id)).tuples())
    stale, new = existing - wanted, wanted - existing
    if stale:
        session.execute(
            delete(ModelAlias).where(tuple_(ModelAlias.alias, ModelAlias.model_id).in_(stale))
        )
    if new:
        session.execute(
            insert(ModelAlias),
            [
                {'id': uuid7(), 'alias': alias, 'model_id': model_id}
                for alias, model_id in sorted(new)
            ],
        )
    return len(new), len(stale)


def load_taxonomy(session: Session, data: TaxonomyData) -> LoadReport:
    """Make the taxonomy tables match `data`, inside the caller's transaction.

    Nothing is written unless the whole dataset validates. Concurrent loads serialise on
    an advisory lock held until the caller commits, so the second sees the first's rows
    and changes nothing.
    """
    problems = validate_taxonomy(data)
    if problems:
        raise TaxonomyDataError(problems)

    hold_advisory_lock(session, AdvisoryLock.TAXONOMY_LOAD)
    aliases: dict[tuple[str, str], list[AliasRow]] = defaultdict(list)
    for alias in data.aliases:
        aliases[(alias.make_slug, alias.model_slug)].append(alias)

    counts = _Counts()
    make_ids = _sync_makes(session, data, counts)
    model_ids = _sync_models(session, data, make_ids, counts)
    make_added, make_removed = _sync_make_aliases(session, data, aliases, make_ids)
    model_added, model_removed = _sync_model_aliases(session, data, aliases, model_ids)

    return LoadReport(
        inserted=counts.inserted,
        updated=counts.updated,
        deactivated=counts.deactivated,
        unchanged=counts.unchanged,
        aliases_added=make_added + model_added,
        aliases_removed=make_removed + model_removed,
    )


def _lookup_key(text: str | None) -> str | None:
    key = normalise_lookup(text or '')
    # No alias is longer than a name, so a longer key cannot match; skip the query.
    return key if key and len(key) <= NAME_MAX_LENGTH else None


def resolve_make(session: Session, text: str | None) -> UUID | None:
    """The active make that `text` names (any case, spacing, hyphenation, or alias)."""
    key = _lookup_key(text)
    if key is None:
        return None
    return session.scalar(
        select(Make.id)
        .join(MakeAlias, MakeAlias.make_id == Make.id)
        .where(MakeAlias.alias == key, Make.is_active)
    )


def resolve_model(session: Session, make_id: UUID, text: str | None) -> UUID | None:
    """The active model of `make_id` that `text` names, or None."""
    key = _lookup_key(text)
    if key is None:
        return None
    return session.scalar(
        select(VehicleModel.id)
        .join(ModelAlias, ModelAlias.model_id == VehicleModel.id)
        .where(VehicleModel.make_id == make_id, ModelAlias.alias == key, VehicleModel.is_active)
    )


def make_names(session: Session, make_ids: Iterable[UUID]) -> dict[UUID, str]:
    """Display names by id, inactive makes included (listings keep referencing them)."""
    ids = set(make_ids)
    if not ids:
        return {}
    return dict(session.execute(select(Make.id, Make.name).where(Make.id.in_(ids))).tuples().all())


def model_names(session: Session, model_ids: Iterable[UUID]) -> dict[UUID, str]:
    """Display names by id, inactive models included."""
    ids = set(model_ids)
    if not ids:
        return {}
    rows = session.execute(
        select(VehicleModel.id, VehicleModel.name).where(VehicleModel.id.in_(ids))
    )
    return dict(rows.tuples().all())


@dataclass(frozen=True)
class CatalogueModel:
    """An active model with its make, for generators and pickers (no ORM objects leak)."""

    make_id: UUID
    make_slug: str
    make_name: str
    make_is_popular: bool
    model_id: UUID
    model_slug: str
    model_name: str
    body_types: tuple[str, ...]


def catalogue(session: Session) -> list[CatalogueModel]:
    """Every active model of an active make, sorted by make slug then model slug."""
    rows = session.execute(
        select(
            Make.id,
            Make.slug,
            Make.name,
            Make.is_popular,
            VehicleModel.id,
            VehicleModel.slug,
            VehicleModel.name,
            VehicleModel.body_types,
        )
        .join(VehicleModel, VehicleModel.make_id == Make.id)
        .where(Make.is_active, VehicleModel.is_active)
        .order_by(Make.slug, VehicleModel.slug)
    )
    return [
        CatalogueModel(
            make_id,
            make_slug,
            make_name,
            is_popular,
            model_id,
            model_slug,
            model_name,
            tuple(body_types),
        )
        for make_id, make_slug, make_name, is_popular, model_id, model_slug, model_name, body_types in rows
    ]
