# Feature 02 — Delivery Slices

Design: [02-vehicle-taxonomy-and-seed-data.md](02-vehicle-taxonomy-and-seed-data.md)
(the *what*). How we build: [IMPLEMENTATION_PLAYBOOK.md](IMPLEMENTATION_PLAYBOOK.md).
This file is the *order and size* of the work. One slice per session; each ends green on
`main` (playbook §1).

**Total:** 9 slices, about 16 h (the design doc's 13 h realistic estimate plus the
amendments below and per-slice verification).

| # | Slice | Est. | Depends on | Status |
|---|---|---|---|---|
| 2.1 | Model conventions, enum/CHECK tooling, taxonomy schema | 1.5 h | — | Not Started |
| 2.2 | Taxonomy data, loader and alias resolver | 2 h | 2.1 | Not Started |
| 2.3 | Postcode-district dataset and lookup | 1.5 h | — | Not Started |
| 2.4 | `Dealer` core and `Listing` schema | 2 h | 2.1 | Not Started |
| 2.5 | Pure derivations and the `specs` model | 1.5 h | 2.1, 2.3 | Not Started |
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
   code. Only the ~3,000-row derived CSV is committed, with source edition, licence text
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
   imports every module's models so Alembic and the mapper registry see them.
- **A8.** **Hybrids follow the petrol ULEZ rule.** Design §6 said "everything else `false`",
   which would mark every hybrid non-compliant (a 2020 Prius is compliant). UK hybrids
   and plug-in hybrids are overwhelmingly petrol-electric, so `hybrid` and
   `plug_in_hybrid` use the petrol cut-off; `other` stays `false`. The UI still says
   "Likely" and links to TfL's checker.

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
