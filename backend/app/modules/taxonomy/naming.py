"""Text normal forms for taxonomy names (Feature 02 §1).

Two forms, both pure:

- `slugify(name)`: the URL form stored in `slug` (`Citroën` -> `citroen`).
- `normalise_lookup(text)`: the form every alias is stored in and every lookup is reduced
  to before comparing (`Mercedes Benz`, `MERCEDES-BENZ` -> `MERCEDESBENZ`). The database
  refuses an alias in any other form (`ALIAS_PATTERN`), so the writer and the reader
  cannot disagree about it.
"""

from __future__ import annotations

import re
import unicodedata

# Symbols that carry meaning in model names ("Ka+", "Qashqai+2", "Rolls & Co"): spelled out
# rather than dropped, or "Ka+" would collide with "Ka".
_SYMBOL_WORDS = {'&': ' and ', '+': ' plus '}
_NON_SLUG = re.compile(r'[^a-z0-9]+')
_NON_LOOKUP = re.compile(r'[^A-Z0-9]+')


def _ascii_fold(text: str) -> str:
    for symbol, word in _SYMBOL_WORDS.items():
        text = text.replace(symbol, word)
    decomposed = unicodedata.normalize('NFKD', text)
    return ''.join(char for char in decomposed if not unicodedata.combining(char))


def slugify(name: str) -> str:
    """URL slug: lower-case ASCII words joined by single hyphens. Raises if nothing is left."""
    slug = _NON_SLUG.sub('-', _ascii_fold(name).lower()).strip('-')
    if not slug:
        raise ValueError(f'{name!r} has no characters usable in a slug')
    return slug


def normalise_lookup(text: str) -> str:
    """Upper-case ASCII letters and digits only; spaces, hyphens and punctuation removed.

    Returns '' when nothing is left; callers treat that as "no match".
    """
    return _NON_LOOKUP.sub('', _ascii_fold(text).upper())
