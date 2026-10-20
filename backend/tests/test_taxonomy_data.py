"""Taxonomy normal forms and the committed CSVs, with no database (Feature 02 slice 2.2)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.modules.taxonomy.dataset import (
    DEFAULT_DATA_DIR,
    AliasRow,
    MakeRow,
    ModelRow,
    TaxonomyData,
    TaxonomyDataError,
    read_taxonomy,
    validate_taxonomy,
)
from app.modules.taxonomy.models import ALIAS_PATTERN
from app.modules.taxonomy.naming import normalise_lookup, slugify

# Rows renamed after their slug was published: the slug stays, so it no longer equals
# slugify(name). Add {(make_slug, model_slug or ''): reason} when renaming (README).
RENAMED_SLUGS: dict[tuple[str, str], str] = {}

# --- normal forms -------------------------------------------------------------------


@pytest.mark.parametrize(
    ('name', 'slug'),
    [
        ('Citroën', 'citroen'),
        ('Škoda', 'skoda'),
        ('Huracán', 'huracan'),
        ('Mercedes-Benz', 'mercedes-benz'),
        ('Alfa  Romeo', 'alfa-romeo'),
        ('ID. Buzz', 'id-buzz'),
        ('up!', 'up'),
        ('#1', '1'),
        ('e:Ny1', 'e-ny1'),
        ('Ka+', 'ka-plus'),
        ('Qashqai+2', 'qashqai-plus-2'),
        ('Rolls & Co', 'rolls-and-co'),
        (' -Leading and trailing- ', 'leading-and-trailing'),
    ],
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug


@pytest.mark.parametrize('name', ['', '   ', '!!!', '---', '́'])
def test_slugify_refuses_text_with_nothing_usable(name: str) -> None:
    with pytest.raises(ValueError):
        slugify(name)


@pytest.mark.parametrize(
    'spellings',
    [
        ['VW'],
        ['VOLKSWAGEN', 'volkswagen', 'Volks wagen', 'Volks-Wagen', ' volkswagen '],
        ['MERCEDES-BENZ', 'Mercedes Benz', 'mercedes_benz', 'Mercedes.Benz'],
        ['Citroën', 'CITROËN', 'Citroen', 'citroen'],
        ['Ka+', 'Ka Plus', 'KA PLUS'],
    ],
)
def test_spellings_share_one_lookup_key(spellings: list[str]) -> None:
    assert len({normalise_lookup(spelling) for spelling in spellings}) == 1


def test_symbols_keep_names_distinct() -> None:
    assert normalise_lookup('Ka+') != normalise_lookup('Ka')


@pytest.mark.parametrize(
    'text',
    ['Citroën', 'straße', 'Ølsen', '日本', 'A\tB\nC', 'ﬁat', '½', 'x' * 500, '', '+&'],
)
def test_lookup_keys_are_always_in_the_stored_alias_form(text: str) -> None:
    # Reader/writer agreement: whatever the resolver reduces input to is a form the
    # database accepts as an alias (or empty, which the resolver treats as no match).
    key = normalise_lookup(text)
    assert key == '' or re.fullmatch(ALIAS_PATTERN, key)


# --- the committed CSVs -------------------------------------------------------------


@pytest.fixture(scope='module')
def committed() -> TaxonomyData:
    return read_taxonomy()


def test_committed_taxonomy_is_valid(committed: TaxonomyData) -> None:
    assert validate_taxonomy(committed) == []


def test_committed_taxonomy_covers_the_uk_market(committed: TaxonomyData) -> None:
    assert len(committed.makes) >= 45
    assert len(committed.models) >= 450
    makes_with_models = {model.make_slug for model in committed.models}
    assert {make.slug for make in committed.makes} == makes_with_models
    popular = {make.slug for make in committed.makes if make.is_popular}
    # Design §8: the makes the used market is weighted toward.
    assert {
        'ford', 'vauxhall', 'volkswagen', 'bmw', 'mercedes-benz',
        'audi', 'toyota', 'nissan', 'kia', 'hyundai',
    } <= popular  # fmt: skip


def test_committed_slugs_are_derived_from_names(committed: TaxonomyData) -> None:
    mismatched = [
        (make.slug, '') for make in committed.makes if slugify(make.name) != make.slug
    ] + [
        (model.make_slug, model.slug)
        for model in committed.models
        if slugify(model.name) != model.slug
    ]
    assert sorted(set(mismatched) - set(RENAMED_SLUGS)) == []


@pytest.mark.parametrize('name', ['makes.csv', 'models.csv', 'aliases.csv'])
def test_committed_files_are_utf8_with_lf(name: str) -> None:
    raw = (DEFAULT_DATA_DIR / name).read_bytes()
    assert not raw.startswith(b'\xef\xbb\xbf'), 'no byte-order mark'
    assert b'\r' not in raw
    raw.decode('utf-8')


# --- validation refuses every kind of bad row ---------------------------------------


def _data(
    makes: list[MakeRow] | None = None,
    models: list[ModelRow] | None = None,
    aliases: list[AliasRow] | None = None,
) -> TaxonomyData:
    return TaxonomyData(
        makes=tuple(makes if makes is not None else [MakeRow('ford', 'Ford', True)]),
        models=tuple(
            models if models is not None else [ModelRow('ford', 'fiesta', 'Fiesta', ('hatchback',))]
        ),
        aliases=tuple(aliases or []),
    )


_FORD = MakeRow('ford', 'Ford', True)
_FIESTA = ModelRow('ford', 'fiesta', 'Fiesta', ('hatchback',))
_FOCUS = ModelRow('ford', 'focus', 'Focus', ('hatchback', 'estate'))


def test_minimal_dataset_is_valid() -> None:
    assert validate_taxonomy(_data()) == []


def test_the_same_alias_may_name_models_of_different_makes() -> None:
    data = _data(
        makes=[_FORD, MakeRow('seat', 'SEAT', False)],
        models=[_FIESTA, ModelRow('seat', 'leon', 'Leon', ('hatchback',))],
        aliases=[AliasRow('ford', 'fiesta', 'Classic'), AliasRow('seat', 'leon', 'Classic')],
    )
    assert validate_taxonomy(data) == []


@pytest.mark.parametrize(
    ('data', 'problem'),
    [
        (_data(makes=[_FORD, MakeRow('ford', 'Ford Two', False)]), 'duplicate slug'),
        (_data(makes=[_FORD, MakeRow('Bad Slug', 'Bad', False)]), 'not a valid slug'),
        (_data(makes=[_FORD, MakeRow('blank', '', False)]), 'name is empty'),
        (_data(makes=[_FORD, MakeRow('dots', '...', False)]), 'no letters or digits'),
        (_data(makes=[_FORD, MakeRow('long', 'L' * 81, False)]), 'longer than 80'),
        (_data(models=[ModelRow('fourd', 'fiesta', 'Fiesta', ('hatchback',))]), 'unknown make'),
        (_data(models=[_FIESTA, _FIESTA]), 'duplicate slug within the make'),
        (_data(models=[ModelRow('ford', 'kuga', 'Kuga', ('crossover',))]), 'unknown body type'),
        (_data(models=[ModelRow('ford', 'kuga', 'Kuga', ('',))]), 'at least one body type'),
        (_data(aliases=[AliasRow('fourd', '', 'Ford Motor')]), 'unknown make'),
        (_data(aliases=[AliasRow('ford', 'kuga', 'Kuga II')]), 'unknown model'),
        (_data(aliases=[AliasRow('ford', '', ' - ')]), 'has no letters or digits'),
        (_data(aliases=[AliasRow('ford', '', 'A' * 81)]), 'longer than 80'),
        (
            _data(
                makes=[_FORD, MakeRow('vauxhall', 'Vauxhall', True)],
                aliases=[AliasRow('vauxhall', '', 'FORD')],
            ),
            "'FORD' resolves to both make 'ford' and 'vauxhall'",
        ),
        (
            _data(makes=[_FORD, MakeRow('ford-uk', 'FORD', False)]),
            "'FORD' resolves to both make 'ford' and 'ford-uk'",
        ),
        (
            _data(models=[_FIESTA, _FOCUS], aliases=[AliasRow('ford', 'focus', 'Fiesta')]),
            "'FIESTA' resolves to both ford/fiesta and ford/focus",
        ),
    ],
)
def test_validation_refuses(data: TaxonomyData, problem: str) -> None:
    problems = validate_taxonomy(data)
    assert any(problem in reported for reported in problems), problems


def _write_csvs(directory: Path, makes: str, models: str, aliases: str) -> Path:
    for name, content in (('makes', makes), ('models', models), ('aliases', aliases)):
        (directory / f'{name}.csv').write_text(content, encoding='utf-8', newline='\n')
    return directory


def test_read_taxonomy_parses_rows(tmp_path: Path) -> None:
    data = read_taxonomy(
        _write_csvs(
            tmp_path,
            'slug,name,is_popular\nford, Ford ,TRUE\n',
            'make_slug,slug,name,body_types\nford,focus,Focus,hatchback| estate\n',
            'make_slug,model_slug,alias\nford,,Ford Motor\n',
        )
    )
    assert data == TaxonomyData(
        makes=(MakeRow('ford', 'Ford', True),),
        models=(ModelRow('ford', 'focus', 'Focus', ('hatchback', 'estate')),),
        aliases=(AliasRow('ford', '', 'Ford Motor'),),
    )


def test_read_taxonomy_refuses_a_wrong_header(tmp_path: Path) -> None:
    _write_csvs(
        tmp_path,
        'slug,name\nford,Ford\n',
        'make_slug,slug,name,body_types\n',
        'make_slug,model_slug,alias\n',
    )
    with pytest.raises(TaxonomyDataError, match='makes.csv: header must be'):
        read_taxonomy(tmp_path)


def test_read_taxonomy_refuses_a_bad_boolean(tmp_path: Path) -> None:
    _write_csvs(
        tmp_path,
        'slug,name,is_popular\nford,Ford,yes\n',
        'make_slug,slug,name,body_types\n',
        'make_slug,model_slug,alias\n',
    )
    with pytest.raises(TaxonomyDataError, match='makes.csv:2: is_popular must be'):
        read_taxonomy(tmp_path)
