# Vehicle taxonomy

Makes, models and external spellings for cars sold in the UK (Feature 02 §1). This is
production reference data, loaded in every environment on every deploy:

```sh
cd backend
uv run python -m scripts.load_taxonomy          # prints one JSON line with the LoadReport
```

## Source and licence

Hand-curated from manufacturers' UK websites and current UK used-car stock. Make and
model names are facts, not a licensed product; no third-party dataset is copied, so
there is no attribution requirement. Do not import rows from a commercial vehicle
database (CAP, Glass's, DVLA bulk data): those are licensed.

## Files

| File | Columns | Notes |
|---|---|---|
| `makes.csv` | `slug,name,is_popular` | `is_popular` drives the short make list in search (Feature 07). |
| `models.csv` | `make_slug,slug,name,body_types` | `body_types` is `|`-separated values of `BodyType`. Discontinued models stay: this is a used-car site. |
| `aliases.csv` | `make_slug,model_slug,alias` | Other spellings (`VW`, `Mach-E`). Empty `model_slug` means a make alias. |

All files are UTF-8 with LF line endings (`Citroën`, `Škoda`, `Huracán`).

## Review rules

- **Slugs never change.** They are in public URLs. To rename, edit `name` only and leave
  `slug` as it is; the loader rejects a row that looks like the same make or model
  under a new slug. New rows use `slugify(name)` as their slug (a data-quality test
  checks this; add renamed rows to `RENAMED_SLUGS` in
  `tests/test_taxonomy_data.py`).
- **Never delete a row to retire it.** Deleting is safe (the loader only deactivates),
  but keep discontinued models: used stock still carries them.
- **Lookups ignore case, spacing, accents and punctuation.** `Mercedes Benz`,
  `MERCEDES-BENZ` and `mercedes benz` are the same, as are a row's own name and slug,
  so an alias is only needed for a genuinely different spelling. `&` and `+` count as
  `and` and `plus`, so `Ka+` and `Ka` stay distinct.
- **One spelling, one target.** An alias may name only one make, and only one model
  within a make. The loader and the data-quality tests both refuse ambiguity.
- The `make_aliases` and `model_aliases` tables are owned by the loader: it adds and
  removes rows to match these files, so never insert aliases by hand.
