# Feature 02 — Delivery Slices

Design: [02-vehicle-taxonomy-and-seed-data.md](02-vehicle-taxonomy-and-seed-data.md)
(the *what*). How we build: [IMPLEMENTATION_PLAYBOOK.md](IMPLEMENTATION_PLAYBOOK.md).
This file is the *order and size* of the work. One slice per session; each ends green on
`main` (playbook §1).

**Total:** 9 slices, about 16 h (the design doc's 13 h realistic estimate plus the
amendments below and per-slice verification).

| # | Slice | Est. | Depends on | Status |
|---|---|---|---|---|
| 2.1 | Model conventions, enum/CHECK tooling, taxonomy schema | 1.5 h | — | Done (2026-10-19) |
| 2.2 | Taxonomy data, loader and alias resolver | 2 h | 2.1 | Done (2026-10-20) |
| 2.3 | Postcode-district dataset and lookup | 1.5 h | — | Done (2026-10-20) |
| 2.4 | `Dealer` core and `Listing` schema | 2 h | 2.1 | Done (2026-10-20) |
| 2.5 | Pure derivations and the `specs` model | 1.5 h | 2.1, 2.3 | Done (2026-10-20) |
| 2.6 | Visibility, `listed_at`, `system_update`, factories, invariants | 2 h | 2.4, 2.5 | Not Started |
| 2.7 | Deterministic demo seed generator | 2.5 h | 2.2, 2.3, 2.6 | Not Started |
| 2.8 | Seed safety: reset, region scope, production controls | 1.5 h | 2.7 | Not Started |
| 2.9 | Scale proof, CI wiring, docs | 1.5 h | 2.8 | Not Started |

Slices 2.1 and 2.3 have no dependency on each other; 2.3 can be done any time before 2.5.

---

## Design amendments (made while planning; applied to the design doc)

- **A1.** **Demo plates can never be real plates.** Current-format UK plates never use I, Q or
   Z in the two-letter memory tag, so every demo VRM is `Z` + letter + age identifier +
   three letters (e.g. `ZA19KXR`). A random valid plate would otherwise attach a stranger's
   car to a fake listing. `normalise_vrm()` still accepts them (length rule only).
- **A2.** **Demo dealers do not look like real businesses or premises.** Names come from neutral
   word lists ("Northgate Example Motors") and are checked against no real register;
   their location is a postcode-district centroid, and `postcode` stores the outward
   code only (`geo_precision = district` once Feature 04 adds that column). A full
   postcode is someone's real address.
- **A3.** **Postcode-district file is derived, not downloaded ready-made.** No district-centroid
   file is published. `scripts/build_postcode_districts.py` derives it from the ONS
   Postcode Directory (OGL; contains Royal Mail, OS and ONS IPR, so attribution is
   required) using the *median* coordinate of live, geographic postcodes per outward
   code. Only the ~2,700-row derived CSV is committed, with source edition, licence text
   and rebuild command in `backend/data/geo/README.md`.
- **A4.** **Stock photos leave Feature 02.** Sourcing ~40 redistributable car photos is a
   licensing task, and Feature 06 owns `ListingImage` and the attach step anyway.
   Feature 02 ships no images; cards use Feature 03's placeholder until Feature 06 §8.
   *(Open decision, see the end of this file.)*
- **A5.** **Concurrent runs are serialised in the database.** `load_taxonomy` and `seed_demo`
   take a `pg_advisory_xact_lock` so two deploys or two operators cannot interleave,
   independent of the deploy script's `flock`.
- **A6.** **Table names are plural snake case**, matching Feature 01's `feature_flags`:
   `makes`, `vehicle_models` (not `models`, which collides with every ORM's vocabulary),
   `make_aliases`, `model_aliases`, `dealers`, `listings`. Index and constraint names
   follow the metadata naming convention, so the design doc's index names are
   illustrative.
- **A7.** **Model placement under module boundaries.** Domain models live in
   `app/modules/<domain>/models.py`. Cross-module links are FKs by table name
   (`ForeignKey('dealers.id')`) with no ORM `relationship()` across modules, so
   import-linter's "modules import each other's services only" holds. `app/models/__init__.py`
   imports every module's models so Alembic and the mapper registry see them. Because
   that package now reaches into `app.modules`, only Alembic imports the package itself:
   `app.core` imports platform models by submodule (`app.models.feature_flag`), or the
   "Core does not depend on domain modules" contract breaks (found in 2.1).
- **A9.** **One lookup normal form, enforced by the database.** "Upper-case, collapse spaces
   and hyphens" (2.2) could not make `Volks wagen` equal `VOLKSWAGEN`. The normal form is:
   strip accents, spell `&`/`+` as `AND`/`PLUS` (so `Ka+` is not `Ka`), upper-case, keep
   only `A-Z0-9`. Aliases are stored in it and the CHECK is now `alias ~ '^[A-Z0-9]+$'`
   (`ck_*_alias_normalised`, replacing 2.1's upper-case check). The loader also stores every
   make's and model's own name and slug as aliases, so the resolvers are one indexed
   lookup rather than name, then slug, then alias, and the alias tables are owned
   entirely by the loader (found in 2.2).
- **A10.** **Slugs are an explicit CSV column, never derived at load time.** Deriving them
   from `name` would turn every rename into a slug change. A "slug change" is detected
   as a row whose slug disappears while a new slug arrives with the same normalised name
   (within the make, for models), and the whole load is rejected (found in 2.2).
- **A8.** **Hybrids follow the petrol ULEZ rule.** Design §6 said "everything else `false`",
   which would mark every hybrid non-compliant (a 2020 Prius is compliant). UK hybrids
   and plug-in hybrids are overwhelmingly petrol-electric, so `hybrid` and
   `plug_in_hybrid` use the petrol cut-off; `other` stays `false`. The UI still says
   "Likely" and links to TfL's checker.
- **A11.** **The district file covers Great Britain only, and names areas, not post towns.**
   The ONSPD user guide licenses Northern Ireland (`BT`) postcodes from Land and Property
   Services for internal business use only, not under OGL, so they cannot be committed
   (playbook §4). `region_for_postcode` maps any `BT` code to Northern Ireland by rule (the
   area *is* NI); `district_for` returns `None` there, so Feature 04's offline fallback has
   no NI centroid. ONSPD also has no post town (Royal Mail PAF, licensed), so the fifth
   column is `area_name`: the local authority holding most of the district's postcodes.
   Only small-user postcodes count, because large-user and PO Box postcodes sit at the
   sorting office and form pseudo-districts (`BS98`). Result: 2,738 districts, so the
   sanity threshold is > 2,700, not > 2,800 (found in 2.3).
- **A12.** **Drafts may be incomplete; nothing else may.** Feature 05 autosaves half-filled
   drafts and `duplicate` drops mileage and registration date, so every field the publish
   validator requires (make, model, year, registration date, mileage, price, body, fuel,
   transmission, plus the derived `ulez_compliant` and a non-empty `title`) is nullable,
   and one CHECK (`ck_listings_publish_complete`) requires them all unless the status is
   `draft` or `archived`. The database is the backstop for `validate_publishable`. Design
   §3's `status = 'draft' OR published_at IS NOT NULL` also refused archiving a
   never-published draft, which Feature 05 allows; it is now `status IN ('draft',
   'archived') OR …` (found in 2.4).
- **A13.** **Two composite FKs.** `(make_id, model_id)` → `vehicle_models (make_id, id)`, so a
   listing's model always belongs to its make. `(dealer_id, is_demo)` → `dealers (id,
   is_demo)` `ON DELETE CASCADE`, so a listing's `is_demo` always equals its dealer's: the
   2.8 reset deletes demo dealers and cascades, and this makes it impossible for that
   cascade to reach a real listing. `dealers.region_code` is an enum CHECK over the 12
   ONS codes (`geo.Region`). Postcodes are stored normalised (`SW1A 1AA` or outward code
   only), enforced by `ck_dealers_postcode_format` (found in 2.4).
- **A14.** **Derivations for incomplete drafts.** Design §6's slug example dropped the
   title's last word (`…-st-line` for "…ST-Line 5dr") with no rule behind it; the slug is
   now every word of the title, capped at 80 characters on a word boundary, `car` if
   nothing usable is left. It is cosmetic (Feature 08 redirects on the id). `derive_ulez`
   returns `None` when the fuel type or registration date is missing, which is what the
   nullable column and `ck_listings_publish_complete` (A12) expect; electric and `other`
   need no date (found in 2.5).

---

## Slice 2.1 — Model conventions, enum/CHECK tooling, taxonomy schema (1.5 h)

**Goal:** the patterns every later table uses, proven on the smallest real tables.

**Build**
- `app/modules/taxonomy/enums.py`: `BodyType`, `FuelType`, `Transmission`, `Colour`
  (`StrEnum`, values exactly as design §1).
- `app/db/checks.py`: `enum_check(column, enum)` returns a named `CheckConstraint`
  (`ck_<table>_<column>`); a registry records every enum-backed CHECK for the drift
  test. Migration helper `replace_enum_check(table, column, enum)` emits
  `ADD CONSTRAINT … NOT VALID` then `VALIDATE CONSTRAINT` (zero-downtime, design §1).
- `app/modules/taxonomy/models.py`: `Make`, `VehicleModel` (`body_types` as
  `text[]` with a CHECK that every element is a `BodyType`), `MakeAlias`, `ModelAlias`.
  UUIDv7 ids, `TimestampMixin`, unique slugs (`uq_makes_slug`, unique
  `(make_id, slug)`), slug format CHECK `^[a-z0-9]+(-[a-z0-9]+)*$`, aliases stored
  upper-case (CHECK `alias = upper(alias)`).
- Register in `app/models/__init__.py`; Alembic migration with the CHECKs hand-written.
- import-linter: add `app.modules.taxonomy` to the existing contracts (no new rule needed;
  verify it is covered).

**Tests that prove it**
- Drift test: for every registered enum CHECK, the allowed values parsed from
  `pg_constraint` equal the `StrEnum` (design AC *Schema*). Negative proof: a test
  table with a deliberately mismatched CHECK makes the comparison fail.
- Direct-SQL inserts with a bad slug, a lower-case alias, or an unknown body type fail
  at the database.
- Round trip + `alembic check` clean.

**Done when:** gate green (playbook §6); migration round trip clean; slice committed and pushed.

**Notes (done 2026-10-19):**
- The enum-CHECK "registry" is the metadata itself: `enum_check()` tags each constraint's
  `info` and `enum_checks(metadata)` walks every table, so nothing can be left
  unregistered. The drift test asserts it found `vehicle_models.body_types`, so it cannot
  pass vacuously on zero constraints.
- `replace_enum_check` runs `VALIDATE` in an Alembic `autocommit_block`. Inside the same
  transaction as `ADD … NOT VALID` it would hold the ACCESS EXCLUSIVE lock for the whole
  scan, which defeats the point. `alembic/env.py` now sets `transaction_per_migration=True`
  so that block commits only its own revision. Tested both ways: widening succeeds;
  narrowing below existing rows fails validation and leaves a NOT VALID check, which the
  drift test reports.
- The naming convention now uses the `column_0_N` forms, so multi-column keys are named
  after every column (`uq_vehicle_models_make_id_slug`, not `…_make_id`). Single-column
  names are unchanged (`alembic check` is clean against the existing schema).
- Autogenerate *did* emit these CHECKs because they sit on new tables; it only misses
  CHECKs added to existing tables. The migration keeps them as literal SQL rather than
  building them from the live enums, so a later enum change cannot rewrite history.
- FKs: alias → make/model `ON DELETE CASCADE`; model → make keeps RESTRICT (taxonomy is
  never deleted). Alias uniqueness: `make_aliases.alias` globally, `model_aliases
  (model_id, alias)`.
- import-linter: the wildcard contracts already cover `taxonomy`. Probes: a `listings`
  file importing `taxonomy.models` breaks the contract; `taxonomy` importing its own
  `models` is allowed, which 2.2's services need.
- **Follow-up for 2.2:** `ck_*_alias_upper_case` only enforces upper case. Once 2.2 fixes
  the resolver's normal form, tighten the CHECK to that exact form (playbook §2).

---

## Slice 2.2 — Taxonomy data, loader and alias resolver (2 h)

**Goal:** real UK makes/models in every environment, loaded safely on every deploy.

**Build**
- `backend/data/taxonomy/makes.csv` (~45), `models.csv` (~450), `aliases.csv`, UTF-8,
  with a `README.md` stating sources (manufacturer UK sites; names are facts, not a
  licensed product) and the review rule.
- `app/modules/taxonomy/services.py`:
  - `slugify(name)`: NFKD transliteration (`Citroën` → `citroen`, `Škoda` → `skoda`).
  - `load_taxonomy(rows) -> LoadReport(inserted, updated, deactivated, unchanged)`:
    upsert by slug, **never delete** (missing rows → `is_active = false`), **slug
    immutable** (a CSV row may rename `name`; the service rejects a slug change),
    one transaction under `pg_advisory_xact_lock`.
  - `resolve_make(text)` / `resolve_model(make_id, text)`: normalise (upper-case,
    collapse spaces and hyphens) and look up name, slug, then alias. Returns `None`
    when unmatched (Feature 05 logs unmatched lookups).
- `scripts/load_taxonomy.py` CLI printing the `LoadReport` as one JSON log line.
- `ops/deploy/deploy.sh`: run `load_taxonomy` after migrations (design §1).

**Design / security / scale notes**
- CSV validated *before* any write: duplicate slugs, a model with an unknown make,
  invalid body types or an alias mapping to two targets aborts the whole load.
- Data-quality tests on the committed CSVs themselves, so a bad PR fails CI without
  touching a database.

**Tests that prove it** (design AC *Taxonomy*)
- Two consecutive loads: the second reports 0 inserts, 0 updates.
- Removing a model from the input deactivates it; a listing-like reference row on it
  still loads (finished in 2.4 when `listings` exists; here assert the row survives).
- Renaming `name` succeeds; attempting to change a slug raises.
- `"VW"`, `"VOLKSWAGEN"`, `"volkswagen"`, `"Volks wagen"` resolve to the same make;
  `"MERCEDES-BENZ"` and `"Mercedes Benz"` too.
- Two loads started concurrently both succeed and the result equals a single load.
- The real CLI runs against the test database.

**Notes (done 2026-10-20):**
- Data: 50 makes, 546 models (discontinued models kept: used market), 60 explicit
  aliases; 656 alias rows once names and slugs are added. Real CLI: first run inserted
  596 rows, second run 0 inserted / 0 updated / 596 unchanged.
- Module split: `naming.py` (pure `slugify`, `normalise_lookup`), `dataset.py` (CSV
  rows, reading, `validate_taxonomy`; no database, so the CSV data-quality tests need
  none), `services.py` (loader, resolvers, and re-exports of `slugify`, the only entry
  point other modules may import). Advisory-lock keys live in one enum,
  `app/db/locks.py`, so 2.7's seed lock cannot reuse a number by accident.
- Resolvers return only *active* rows: a deactivated make or model keeps its id for
  existing references but is no longer offered for new lookups. Its aliases are removed.
- Concurrency is proven both ways: with the lock, the second loader is observed
  waiting in `pg_locks` and the result equals a single load; with the lock stubbed out
  and both loaders forced past the read, exactly one fails with a unique violation.
- New rows must use `slugify(name)` as their slug (data-quality test); a renamed row
  goes in `RENAMED_SLUGS` in `tests/test_taxonomy_data.py` (rule in
  `backend/data/taxonomy/README.md`).
- `deploy.sh` runs the loader after migrations as the app role (DML only), before the
  traffic switch; the previous release never reads the new rows.
- **Follow-up (Feature 05):** DVLA-style model strings carry the trim
  (`GOLF MATCH TSI`) and will not resolve. Feature 05 logs unmatched lookups as planned
  and may want a longest-prefix fallback.
- **Follow-up (later, low risk):** "one alias, one model within a make" is enforced by
  the loader's validation, not the database (`model_aliases` has no `make_id`). Enforcing
  it there needs a denormalised `make_id` plus a composite FK. Revisit if anything other
  than the loader ever writes aliases.
- gitleaks could not run locally (the pre-commit environment fails on an unrelated
  hook's pinned revision); CI's pre-commit job covers it.

---

## Slice 2.3 — Postcode-district dataset and lookup (1.5 h)

**Goal:** offline outward-code → centroid/region lookup, reused by Features 04 and 07.

**Build**
- `scripts/build_postcode_districts.py --onspd <path>`: streams the ONSPD CSV (it is
  large; never load it whole: memory budget, playbook §7), keeps live geographic
  postcodes (non-null coordinates, no termination date), groups by outward code, takes
  the **median** lat/lng, and maps each district to its ONS region code. Deterministic
  output, sorted.
- `backend/data/geo/postcode_districts.csv` (outward code, lat, lng, region code, post
  town) and `backend/data/geo/README.md` (ONSPD edition, licence and attribution text,
  rebuild command).
- `app/modules/geo/districts.py`: `district_for(outward_code)` and
  `region_for_postcode(postcode)`, backed by a module-level dict loaded once
  (`lru_cache`; ~3,000 rows is a few hundred KB).

**Design / security / scale notes**
- Manual prerequisite: a developer downloads the ONSPD edition once (it is not fetched
  in CI or at runtime). Record the edition date.
- Postcode parsing accepts full postcodes and outward codes, any case and spacing; it
  never logs the full postcode.

**Tests that prove it**
- Dataset sanity: > 2,800 districts; every coordinate inside the UK bounding box; every
  region code is one of the 12 ONS regions/nations; no duplicate outward codes.
- Known fixtures: `SW1A` → London, `M1` → North West, `EH1` → Scotland, `BT1` → Northern Ireland.
- Builder unit test on a small synthetic ONSPD-shaped file: median (not mean) is used,
  terminated and non-geographic postcodes are excluded.

**Notes (done 2026-10-20):**
- Built from the **ONSPD August 2026** edition (ArcGIS item `9e5a92a3cfb14dc7ad43d6ea7a7b8c7f`),
  newer than the February 2026 default in the open decisions. The builder reads the zip
  as downloaded and streams the 1.5 GB CSV from inside it: 27 s locally, never extracted.
- A11 changed three things against the plan: no Northern Ireland rows (licence), `area_name`
  instead of post town (ONSPD has none), small-user postcodes only. `BT1` → Northern
  Ireland still holds, by rule rather than from the file; the district threshold is
  > 2,700. GB regions all present (11, plus NI by rule).
- Column names carry the boundary year (`rgn26cd`); the builder matches them by prefix so
  next year's `rgn27cd` needs no change, and fails if a column is missing or ambiguous.
  Majority region and authority ties break on the lower code; output is byte-identical
  per edition.
- Guards proven: swapping median for mean and dropping the NI exclusion each fail the
  builder tests; corrupting one committed row (coordinates, region, NI, area name) or
  truncating the file fails the dataset sanity check.
- `district_for`, `region_for_postcode`, `outward_code` and `all_districts` live in
  `app/modules/geo/districts.py` (2.5 re-exports `region_for_postcode` from `derive.py`).
  Nothing in the module logs, and unparseable input returns `None` without echoing it.
- **Follow-up (Feature 04 §7):** the offline fallback has no Northern Ireland centroid. A
  `BT` dealer registered while postcodes.io is down needs another fallback (hold
  registration, or region-only with no coordinates).
- **Follow-up (2.4/2.8):** `dealers.region_code` should be CHECK-constrained to the
  `REGIONS` keys, and 2.8's `--region NW` needs a short-code alias table over them.
- **Follow-up (Feature 15):** the ONSPD attribution text in `backend/data/geo/README.md`
  must appear on the site's attribution page.

---

## Slice 2.4 — `Dealer` core and `Listing` schema (2 h)

**Goal:** the central tables, with the database refusing every contradictory row.

**Build**
- `app/modules/dealers/models.py`: `Dealer` core (design §2): `status` enum CHECK
  (`DealerStatus`), `is_demo`, UUIDv7, `TimestampMixin`.
- `app/modules/listings/enums.py`: `ListingStatus`, `ModerationStatus`.
- `app/modules/listings/models.py`: `Listing` with every column, range CHECK and
  consistency CHECK in design §3; `specs` JSONB + `specs_version`; `dealer_id` FK
  `ON DELETE CASCADE`.
- Indexes from design §7. The partial indexes use **the same SQLAlchemy expression**
  as `publicly_visible()` (stubbed here, completed in 2.6), so the predicate text in
  the index and in every query is identical and Postgres can match them.
- Migration, CHECKs hand-written.

**Tests that prove it** (design AC *Schema*)
- Table-driven direct-SQL rejection: `price_pence = 0`, `mileage = -1`,
  `fuel_type = 'steam'`, `status = 'archived'` without `archived_at`, `sold` without
  `sold_at`, `active` without `published_at`, `listed_at` without `published_at`,
  `description` over 5,000 chars, `doors = 8`.
- **Cascade introspection test:** every FK in the schema that references `listings` or
  `dealers` has `ON DELETE CASCADE`. Later features' tables are checked automatically
  (design §9 rule, enforced mechanically). Negative proof with a throwaway table.
- UUIDv7 ids sort by creation time.
- Round trip + `alembic check` clean (watch for partial-index predicate drift; playbook §3).

**Notes (done 2026-10-20):**
- A12 and A13 above came out of this slice; the design doc is updated to match.
- **Partial indexes match queries under a generic plan.** `visible_predicate()` in
  `listings/models.py` builds both the index predicates and `publicly_visible()`, with the
  constants rendered inline (`literal_execute`), never as bound parameters. Proven with
  `PREPARE` + `EXPLAIN EXECUTE` under `plan_cache_mode = force_generic_plan`: the visible
  index is used; the same rule with bound parameters cannot use it (negative test).
  psycopg switches to prepared statements after 5 executions, so bound constants would have
  silently lost the index on hot search queries.
- `alembic check` does not compare partial-index predicates, so a new introspection test
  (`partial_index_drift`) builds each model index under a probe name and compares
  Postgres's own rendering of both predicates. It walks every partial index in the
  metadata, so later features are covered. Negative proof: a recreated index with a
  different predicate is reported.
- Cascade introspection test walks `pg_constraint` for every FK onto `listings` or
  `dealers`; negative proof with a throwaway non-cascading table.
- Indexes: descending sorts read ascending indexes backwards, so there are no `DESC`
  expression indexes. `(dealer_id, status, updated_at)` serves the dealer FK and its
  cascade; `(make_id, model_id)` serves both taxonomy FKs (taxonomy is RESTRICT).
- Shared helpers moved to `app/db/checks.py`: `SLUG_PATTERN`/`slug_format_check()` and
  `coordinate_checks()`, because modules may not import each other's `models`.
  `geo.Region` (StrEnum) replaces 2.3's plain dict; `app/modules/geo/services.py` is the
  module's public entry point.
- 2.2's deferred check is done: a listing on a model the loader deactivates survives the load.
- The migration created `uq_vehicle_models_make_id_id` after `listings` as autogenerated,
  which the composite FK needs first; moved up by hand, and the downgrade drops it last.
- **Follow-up (Feature 04):** writers must normalise postcodes to `SW1A 1AA` form before
  saving (the CHECK refuses anything else); geo has `outward_code()` but no full-postcode
  normaliser yet.
- **Follow-up (2.5/2.6):** `VRM_PATTERN` in `listings/models.py` is the CHECK for
  `normalise_vrm()`'s output; 2.5 should test the function against it directly.

---

## Slice 2.5 — Pure derivations and the `specs` model (1.5 h)

**Goal:** every derived value comes from one pure function; no database needed.

**Build**
- `app/modules/listings/derive.py`: `build_title`, `listing_slug`, `derive_ulez`,
  `normalise_vrm`, and `region_for_postcode` re-exported from geo (design §6).
- `app/modules/listings/specs.py`: `EquipmentItem` vocabulary (~120 codes with display
  groups), `ListingSpecsV1` (`extra="forbid"`, ranges per field), 16 KB serialised
  cap, `parse_specs(raw, version)` with the upgrade hook for a future V2.

**Tests that prove it**
- ULEZ boundaries: petrol registered 2005-12-31 vs 2006-01-01; diesel 2015-08-31 vs
  2015-09-01; electric always; hybrid and plug-in hybrid follow the petrol cut-off
  (A8); `other` is always `false`.
- VRM: spaces, lower case, punctuation, too short/long, `None` input; demo `Z…` plates accepted.
- Title and slug with Unicode, punctuation, very long variants (title ≤ 160 enforced).
- Specs: unknown key and > 16 KB both raise; a valid payload round-trips with
  `specs_version = 1`; unknown equipment code rejected; free-text extras capped at 10 × 60.
- Coverage of `derive.py` and `specs.py` at 100% (pure code, no excuse).

**Notes (done 2026-10-20):**
- Vocabulary: 123 equipment codes in 9 display groups (safety, driver assistance,
  comfort, infotainment, exterior, interior, practicality, performance, electric), each
  with a label for Feature 05's checklist and Feature 08's grouped display
  (`equipment_by_group`). Codes are stored, so they never change; retiring one needs a
  specs version bump.
- The 16 KB cap measures the raw payload's compact UTF-8 JSON *before* validation, so a
  huge body is refused without parsing it. The largest valid payload (every code, 10
  extras) is under half the cap, so the cap never refuses honest input.
- `parse_specs(raw, version)` refuses unknown versions and runs `UPGRADES[n]` step by
  step up to `SPECS_VERSION`; the hook is exercised by a test that simulates a V2.
  Field errors are pydantic `ValidationError`s (one location each, ready for a 422);
  size and version errors are `SpecsError`. `mot_checked_at` must be timezone-aware.
- `build_title` collapses whitespace, skips missing parts (a bare draft gives `''`, which
  the A12 CHECK allows only for drafts) and cuts at a word boundary at 160.
- `normalise_vrm`'s output is tested against `VRM_PATTERN`, and `VRM_PATTERN` against the
  live `ck_listings_vrm_normalised` definition (2.4 follow-up closed).
- A test runs `derive_ulez` over every `FuelType`, so adding a fuel without a ULEZ rule
  fails CI instead of falling through.
- import-linter's "only cross-import services" contract forbids reaching another module's
  `models` *indirectly* too, and `taxonomy.services` imports `taxonomy.models`. So 2.2's
  "services is the only entry point" cannot hold for listings: `derive.py` imports
  `slugify` from the pure `taxonomy.naming` (and `models.py` the enums from
  `taxonomy.enums`). Rule from here on: other modules import a module's `services`, or its
  pure leaf modules (`enums`, `naming`) that import no models. Caught by the gate, not by
  a test.
- Coverage is 100% for both files but only verified locally; the CI gate is the global
  85%. **Follow-up (2.9):** consider a per-file 100% gate for pure modules.

---

## Slice 2.6 — Visibility, `listed_at`, `system_update`, factories, invariants (2 h)

**Goal:** the single visibility rule, and background writes that never break a dealer's edit.

**Build**
- `app/modules/listings/visibility.py`: `publicly_visible()` expression and
  `on_change(session, listing)` (sets `listed_at` once, when first visible).
- `app/modules/listings/services.py`: `system_update(session, listing_id, **cols)`:
  allow-listed columns only (`moderation_status`, `listed_at`, `photo_count`,
  `latitude`, `longitude`); Core `UPDATE` that writes `updated_at = updated_at` so
  `onupdate` does not fire.
- `verify_listing_invariants(session)`: recomputes title, ULEZ, VRM normal form and
  the `listed_at` rule for every row and returns mismatches (used by the seed and by
  Feature 05).
- Test factories `tests/factories/dealers.py`, `tests/factories/listings.py` that build
  through `derive.py` and `on_change`, never hand-setting a derived column (playbook §2).

**Tests that prove it** (design AC *Visibility & system-owned columns*)
- `publicly_visible()` over every `status × moderation_status × archived` combination
  (table test against real rows, not just the expression).
- `system_update(moderation_status='hidden')` leaves `updated_at` unchanged, and an
  optimistic-lock check (`ensure_not_stale`) with the pre-change token still passes.
- `system_update` refuses a column outside the allow-list.
- `listed_at`: set on first visibility, null while held, unchanged by unpublish → republish.
- Invariant checker catches a deliberately corrupted title (negative proof).

---

## Slice 2.7 — Deterministic demo seed generator (2.5 h)

**Goal:** about 5,000 believable listings, identical for the same seed, in under 2 minutes, offline.

**Build**
- `app/modules/listings/demo_seed.py` (generation, pure given a `random.Random(seed)`)
  and `scripts/seed_demo.py` (CLI: `--listings`, `--random-seed`, `--profile perf`).
- Dealers: ~1 per 80 listings, spread over real districts weighted by region
  population; names and plates per A1–A2.
- Vehicles: make/model mix weighted to the UK used market; year distribution; mileage
  7–9k/year ± variance; price from `base_new_price × age_factor × mileage_factor ± noise`,
  clamped to the CHECK range; specs from the vocabulary; statuses mostly `active`
  with some `reserved`/`sold`/`draft`.
- Every row built through `derive.py` + `on_change`; bulk Core inserts in batches of
  1,000; `verify_listing_invariants()` runs at the end and fails the command on any
  mismatch. Advisory lock held for the run.

**Tests that prove it** (design AC *Seed*, part 1)
- Two runs with the same seed produce byte-identical exports (excluding ids and
  timestamps); a different seed differs.
- 500-listing run inside the test suite: invariants pass, network blocked.
- Price sanity: within each popular make, median price of 1-year-old > 5-year-old > 10-year-old.
- Every generated VRM starts with `Z`; no dealer name matches the real-name blocklist fixture.
- Timed run of 5,000 locally (single process; record the time in the slice notes).

---

## Slice 2.8 — Seed safety: reset, region scope, production controls (1.5 h)

**Goal:** demo data can be added and removed per region without any risk to real rows.

**Build**
- `--region R` (create only in that ONS region), `--reset` (hard-delete `is_demo`
  dealers and their listings, scoped by `--region` if given; cascades do the rest).
- Production rules: refuses without `--region` **and** `--confirm-production`;
  `--profile perf` always refused in production; every run logs operator (OS user),
  host, flags and counts.

**Tests that prove it** (design AC *Seed*, part 2)
- `--reset --region NW` removes only demo rows in NW; a non-demo listing and demo rows
  in other regions survive; no FK error.
- With `ENVIRONMENT=production`: missing `--region` or `--confirm-production` exits
  non-zero before touching the database; `--profile perf` exits non-zero.
- Reset is idempotent (second run deletes 0).

---

## Slice 2.9 — Scale proof, CI wiring, docs (1.5 h)

**Goal:** the performance claims are measured continuously, not asserted once.

**Build**
- CI `backend` job: `alembic upgrade head` → `load_taxonomy` → `seed_demo --listings 500`
  → `verify_listing_invariants` (smoke, every push).
- New `nightly.yml` (scheduled): seed 5,000 (assert < 2 min), seed `--profile perf`
  50,000 (assert < 10 min), then `EXPLAIN (ANALYZE, FORMAT JSON)` on
  `publicly_visible() AND make = Ford AND price BETWEEN £5k AND £10k ORDER BY price`:
  fail on a sequential scan of `listings` or > 50 ms. Feature 07 adds its 12 queries to
  this same job.
- Docs: design doc status → Done with implementation notes; FEATURES_PLAN status;
  `README.md` commands (`load_taxonomy`, `seed_demo`).

**Done when:** nightly job passes once on GitHub (ask the user to trigger it via
`workflow_dispatch` and check the Actions tab; playbook §7).

---

## How Feature 01's lessons apply here

| Lesson (playbook) | Where it bites in Feature 02 | What the slice does |
|---|---|---|
| Autogenerate misses CHECKs (§3) | ~25 CHECKs across 2.1 and 2.4 | Hand-written, plus the enum-drift introspection test |
| Enforce future rules mechanically (§3) | "Every table referencing listing/dealer cascades" | Schema-walking cascade test in 2.4, auto-covers Features 04–14 |
| Reader/writer agreement (§2) | `listed_at`, `title`, `ulez_compliant` read by 07, 08, 11 | One derivation path + `verify_listing_invariants()` |
| Background writes and lock tokens (§3) | moderation, relocation, photo counts | `system_update()` allow-list, tested against `ensure_not_stale` |
| Real DB, not SQLite (§2) | Partial indexes, JSONB, `text[]`, advisory locks | All tests on test-stack Postgres |
| Prove the guard can fail (§2) | drift test, cascade test, invariant checker | Each has a negative test |
| UTF-8 explicitly (§4) | Citroën, Škoda, Alfa Romeo, post towns | `encoding='utf-8'` on every CSV read/write; Unicode slug tests |
| Licensed data only (§4) | ONSPD, taxonomy, stock photos | Attribution READMEs; photos deferred (A4) |
| Demo data must not look real (§4) | plates, dealer names, addresses | A1–A2 |
| Memory budget (§7) | ONSPD is huge; 50k seed | Streaming builder; perf profile only in nightly CI |
| Destructive commands refuse by default (§5) | `seed_demo --reset` in production | 2.8 production rules |
| Small green increments (§1) | Feature 01 found 12 bugs only at the end | 9 slices, each pushed and CI-green |

---

## Open decisions (defaults chosen; change before the slice starts)

1. **Stock photos** (A4): default is to move them to Feature 06. Alternative:
   source ~40 CC0/own-generated images in Feature 02. Needed before Feature 06, not before 2.1–2.9.
2. **ONSPD edition** for 2.3: default is the latest quarterly edition (February 2026 at
   the time of planning). Needs one manual download (~200 MB+) by a developer.
