# Feature 02 — Vehicle Taxonomy & Seed Inventory

**Status:** Planning. Delivered in 9 slices: [02-vehicle-taxonomy-and-seed-data.slices.md](02-vehicle-taxonomy-and-seed-data.slices.md), which also lists the design amendments (A1–A13) applied below.
**Priority:** Must-Have
**Milestone:** M1 Foundation
**Effort:** 6h optimistic / 13h realistic / 20h pessimistic (slice plan: ~16 h including per-slice verification)
*(raised from 5/10/16h after a scale review: the listing visibility model, system-owned
column writes, a minimal `Dealer` table and a production-safe, deterministic seed are
decided here because features 05, 07, 08, 11, 13 and 14 all read them. See "Scale
review" at the end.)*
**Depends on:** 01

## Description

The vehicle data model, and the reference data every filter, form and search page is
built on. Report §4 warns that "vehicle spec data model has real variability
(make/model/trim/options) — schema design needs care even if CRUD is fast." This
feature does that design once, up front. It also defines **when a listing is
publicly visible** (one predicate, used everywhere), and ships a seed script producing
about 5,000 realistic demo listings, so every later feature is built and measured
against real volume rather than an empty table.

---

## Scope

### 1. Reference data — taxonomy (production data, not demo data)
| Table | Fields | Notes |
|---|---|---|
| `Make` | `id`, `name`, `slug`, `is_popular`, `is_active` | ~45 makes sold in the UK. `slug` is used in SEO URLs (`/cars/volkswagen`). |
| `Model` | `id`, `make_id`, `name`, `slug`, `body_types[]`, `is_active` | ~450 models. Unique `(make_id, slug)`. |
| `MakeAlias` / `ModelAlias` | `alias` (lookup normal form: accents stripped, `&`/`+` spelled out, upper-case `A-Z0-9` only; CHECK-enforced, A9), `make_id` / `model_id` | Maps external strings ("VW", "Volks wagen", "MERCEDES-BENZ") onto our taxonomy. Owned by the loader, which also stores each row's own name and slug here, so lookup is one query. Used by Feature 05's plate lookup and any later import. |

- Source of truth: hand-curated CSVs in `backend/data/taxonomy/` (`makes.csv`, `models.csv`, `aliases.csv`), reviewed in PRs. Make and model names are factual data, not a licensed product.
- **`uv run python -m scripts.load_taxonomy`** upserts by slug, is idempotent (a second run changes nothing), and **never deletes**: a row removed from the CSV is set `is_active = false`, so listings, saved searches and SEO URLs that reference it keep working. It runs in every environment as a deploy step after migrations (Feature 01 §15), inside a `pg_advisory_xact_lock` so concurrent runs serialise (A5). It is separate from the demo seed, which production may or may not run.
- **Slugs are immutable once created.** They are an explicit CSV column, never derived at load time (A10), and the loader rejects a load that would move a row to a new slug. A rename changes `name` only. Slugs appear in SEO URLs (Feature 13) and shared links; ids, not slugs, are what saved searches store (Feature 07).
- **Enumerations are `text` columns with named CHECK constraints** (`ck_listing_fuel_type`, …), backed by one Python `StrEnum` each, not native Postgres enums:
  - `BodyType`: hatchback, saloon, estate, suv, coupe, convertible, mpv, pickup, van
  - `FuelType`: petrol, diesel, hybrid, plug_in_hybrid, electric, other
  - `Transmission`: manual, automatic
  - `Colour` (15): black, white, silver, grey, blue, red, green, yellow, orange, brown, beige, gold, purple, bronze, other
  - Adding a value is a migration that replaces the CHECK (`NOT VALID` then `VALIDATE`, zero-downtime per Feature 01 §6). A test asserts every CHECK list equals its `StrEnum`, because `alembic check` does not detect CHECK drift.

### 2. `Dealer` (minimal core, created here, extended by Feature 04)
`Listing.dealer_id` needs a target table before Feature 04 exists, and the seed needs
demo dealers. This feature creates the core; Feature 04 adds the account columns
(address, phone, approval fields, logo, opening hours) in its own migration.

`id` (UUIDv7), `name`, `slug` (unique, immutable once approved), `postcode` (normalised,
`SW1A 1AA` or outward code only, CHECK), `latitude`, `longitude` (nullable together: no
offline centroid for Northern Ireland, A11), `region_code` (ONS region, derived from the
postcode district; enum CHECK over the 12 codes, A13), `status` (`pending` / `approved` / `rejected` / `suspended`, CHECK; transitions owned by Feature 14 §3), `is_demo` (bool),
plus `TimestampMixin`.

### 3. `Listing` (the central table; Feature 05 is its main writer)
**Typed, indexed columns, i.e. everything that is filterable or sortable:**

| Column | Type / rule |
|---|---|
| `id` | UUIDv7 (Feature 01 §5) |
| `dealer_id` | FK → `dealer.id` |
| `status` | `draft` / `active` / `reserved` / `sold` / `archived` (CHECK). The dealer-driven lifecycle, owned by Feature 05. |
| `moderation_status` | `clear` / `held` / `hidden` / `removed` (CHECK, default `clear`). **System-owned** (§5); written only by Feature 14's moderation service. |
| `make_id`, `model_id` | FK → taxonomy; composite FK `(make_id, model_id)` → `vehicle_models (make_id, id)` so the model belongs to the make (A13) |
| `variant` | text ≤ 80 chars, free text ("1.0 EcoBoost ST-Line 5dr") |
| `year`, `registration_date` | `year` CHECK 1900–2100 (the "not in the future" rule is app-level) |
| `mileage` | int miles, CHECK 0–1,000,000 |
| `price_pence` | int, CHECK 10,000–500,000,000 (£100–£5m) |
| `body_type`, `fuel_type`, `transmission`, `colour` | text + CHECK (§1) |
| `engine_size_cc` | int, nullable (EVs), CHECK 0–10,000 |
| `doors`, `seats` | int, CHECK 1–7 and 1–9 |
| `owners` | int, nullable |
| `ulez_compliant` | bool, **derived** (§6) |
| `latitude`, `longitude` | copied from the dealer at publish (Feature 05); **system-owned** after that (§5) |
| `vrm` | normalised plate (§6), nullable, never shown in full publicly |
| `title` | text ≤ 160, **derived** (§6) |
| `description` | text, CHECK `char_length ≤ 5000`, plain text only |
| `published_at` | set by the dealer's publish action (Feature 05) |
| `listed_at` | **system-owned** (§5): the first moment the listing became publicly visible. Set once, never reset. |
| `photo_count` | int, default 0, **system-owned** (§5): number of `ready` images, kept by Feature 06 §4–§5; used by Feature 07's best-match sort |
| `sold_at`, `archived_at` | timestamps for the matching states |
| `is_demo` | bool, copied from `dealer.is_demo` at create; composite FK `(dealer_id, is_demo)` → `dealers (id, is_demo)` keeps them equal (A13) |
| `specs`, `specs_version` | JSONB + int (§4) |
| `created_at`, `updated_at` | `TimestampMixin`; `updated_at` is the optimistic-lock token (Feature 01 §5) |

**Consistency CHECKs (the database refuses contradictory rows):**
- `(status = 'archived') = (archived_at IS NOT NULL)`: one soft-delete signal (Feature 01 §5), not two that can disagree
- `status <> 'sold' OR sold_at IS NOT NULL`
- `status IN ('draft','archived') OR published_at IS NOT NULL` (an unpublished draft can be archived, A12)
- `listed_at IS NULL OR published_at IS NOT NULL`
- **Drafts may be incomplete (A12):** the vehicle fields Feature 05's publish validator requires, plus `ulez_compliant` and a non-empty `title`, are nullable; `ck_listings_publish_complete` requires all of them unless `status` is `draft` or `archived`.

### 4. `specs` JSONB (display-only long tail, versioned)
- Validated on every write by a Pydantic model `ListingSpecsV1` (`extra="forbid"`), stored with `specs_version = 1`. A later shape change adds `ListingSpecsV2` plus an upgrade function applied on read, mirroring Feature 07's `SearchParams` versioning.
- Fields: `equipment` (list of codes from a bundled `EquipmentItem` vocabulary of ~120 items with a display group, e.g. *Comfort*, *Safety*, *Infotainment*; plus up to 10 free-text extras ≤ 60 chars), `power_bhp`, `acceleration_0_62_s`, `top_speed_mph`, `co2_g_km`, `mpg_combined`, `battery_kwh`, `range_miles`, `boot_litres`, `insurance_group`, `mot_expiry`, `mot_checked_at` (from the Feature 05 lookup; Feature 08 shows "as of" this date).
- Size cap: 16 KB serialised (422 above it).
- **Rule:** a field moves out of JSONB into a typed column, by migration and backfill, the moment any feature filters or sorts on it.

### 5. Public visibility and system-owned columns
- **One predicate:** `modules/listings/visibility.py` exposes `publicly_visible()`, a SQLAlchemy expression:
  `status IN ('active','reserved') AND moderation_status = 'clear' AND archived_at IS NULL`.
  Search (07), the detail page (08), similar cars (08), alerts (11), sitemaps and landing pages (13) all use it. **No feature writes its own status filter.** Sold listings are not "visible" in search; Feature 08/13 handle the 30-day sold page explicitly.
- **System-owned columns** (`moderation_status`, `listed_at`, `photo_count`, and `latitude`/`longitude` after a dealer relocation) are written only through `listings.system_update(listing_id, **cols)`. It issues a Core `UPDATE … SET <cols>, updated_at = listing.updated_at`, so the `onupdate` hook does not fire and a dealer's open edit form is **not** invalidated by background or admin work (Yaqlo was hit by this twice; Feature 01 §5 rule).
- **`listed_at` is set by `visibility.on_change(listing)`**, which every transition that can change visibility calls (Feature 05 publish/unpublish/reserve, Feature 14 hold release). It sets `listed_at = now()` only when the listing is visible and `listed_at IS NULL`. Alerts (11) and the "most recently listed" sort (07) use `listed_at`, not `published_at`, because a listing held for review at publish (Feature 14) only becomes visible later. Never resetting it stops "unpublish → republish" being used to jump to the top of the newest-first sort.

### 6. Derived fields — one pure function each
`modules/listings/derive.py`, used by Feature 05's write path **and** by the seed, so
seeded rows can never differ from real ones:
- `build_title(year, make, model, variant)` → `"2019 Ford Fiesta 1.0 EcoBoost ST-Line 5dr"`
- `listing_slug(title)` → `2019-ford-fiesta-1-0-ecoboost-st-line` (Feature 08 URL)
- `derive_ulez(fuel_type, registration_date)`: Euro 4 petrol is roughly 2006 onward, Euro 6 diesel roughly September 2015 onward, EVs always qualify, hybrids and plug-in hybrids follow the petrol cut-off because UK hybrids are overwhelmingly petrol-electric (A8), `other` is `false`. Labelled "Likely ULEZ compliant" in the UI with a TfL link.
- `normalise_vrm(raw)`: upper-case, strip spaces and non-alphanumerics, validate length 2–7 (`None` if invalid). Every VRM comparison (duplicate detection, lookups, Feature 14 checks) uses the normalised form.
- `region_for_postcode(postcode)`: outward code → ONS region via the bundled district CSV (§8).

### 7. Indexes (baseline; search tuning is owned by Feature 07)
| Index | Serves |
|---|---|
| `uq_make_slug`, `uq_model_make_id_slug`, `uq_dealer_slug` | taxonomy and dealer URLs |
| `ix_listing_dealer_id_status_updated_at` `(dealer_id, status, updated_at DESC)` | dealer stock table (Feature 05) |
| `ix_listing_vrm` partial `WHERE vrm IS NOT NULL AND status IN ('active','reserved')` | duplicate-VRM warning (05) and hold check (14) |
| Partial `WHERE <publicly_visible>`: `(make_id, model_id, price_pence)`, `(listed_at DESC)`, `(latitude, longitude)` | starter search indexes; Feature 07 §5 confirms or replaces them with EXPLAIN at 50k rows |
| `(dealer_id)` on `Listing`, FK indexes on every FK column | joins and cascades |

No GIN on `specs` until a spec filter exists (§4 rule).

### 8. Demo seed — `uv run python -m scripts.seed_demo`
| Flag | Behaviour |
|---|---|
| `--listings N` (default 5,000) | ~60 demo dealers (one per ~80 listings), spread across real UK postcode districts. Names come from neutral word lists and locations are district centroids with the outward code only, never a real full postcode (A2) |
| `--random-seed S` (default 42) | Fully deterministic: the same seed and N produce an identical dataset (performance tests compare like with like) |
| `--profile perf` | 50,000 listings for Feature 07's budgets. **Refused when `ENVIRONMENT=production`.** |
| `--region R` | Only create (or with `--reset`, only remove) demo dealers in ONS region `R` |
| `--reset` | Removes **only** `is_demo = true` dealers and listings (in `--region` if given). Never touches real rows. |

- **Geography without network:** a bundled postcode-district centroid CSV (`backend/data/geo/postcode_districts.csv`: outward code, lat, lng, region code, area name), derived by `scripts/build_postcode_districts.py` from the ONS Postcode Directory as the median coordinate of live, small-user geographic postcodes per outward code. ONSPD is OGL but contains Royal Mail, OS and ONS IPR, so the attribution text ships in `backend/data/geo/README.md` (A3). The file covers Great Britain only: Northern Ireland postcodes are not OGL, so `BT` codes get their region by rule but no centroid (A11). Feature 04 and Feature 07 reuse it as the offline fallback when postcodes.io is unavailable.
- Make/model/year mix weighted toward the real UK used market (high counts of Ford, Vauxhall, VW, BMW, Mercedes, Audi, Toyota, Nissan, Kia, Hyundai)
- **Prices from a depreciation curve** (`base_new_price × age_factor × mileage_factor ± noise`), so the price indicator (Feature 12) and price sort produce believable results. Mileage correlated with age (~7–9k miles/year ± variance).
- **Real derivation path:** every seeded row is built by the §6 functions and goes through `visibility.on_change()`, so `title`, `ulez_compliant`, `listed_at` and `vrm` are set exactly as Feature 05 would set them. Bulk inserts (batches of 1,000) are allowed for speed, but **no column is hand-set** that a real writer derives. A post-seed check, `verify_listing_invariants()`, recomputes each derived field and fails on any mismatch. Feature 05 adds its publish validator to that check.
- **Images:** none in this feature (A4). Sourcing redistributable stock photos and attaching `ListingImage` rows both move to Feature 06 §8, which owns that table. Until then, cards render Feature 03's missing-image placeholder.
- **Demo plates can never be real plates (A1):** every demo VRM is `Z` + letter + age identifier + three letters (e.g. `ZA19KXR`). Current-format UK plates never use Z in the memory tag, so no demo listing can carry a stranger's registration.
- **Never seed by scraping real listings.** The report notes the real site actively defends against that, and it is a legal risk.

### 9. Demo data in production (cold-start controls)
- Demo inventory can run in production during the regional beta (FEATURES_PLAN risk table). Running `seed_demo` there requires `--region` **and** `--confirm-production`, and logs who ran it.
- **Switching demo off for a region** as real dealers arrive is `seed_demo --reset --region R`. Demo rows are not user data, so they are hard-deleted. **Every later table that references `listing.id` or `dealer.id` must declare `ON DELETE CASCADE`** (or the reset fails with an FK error). The reset test (Acceptance Criteria, *Seed*) is re-run by each feature that adds such a table.
- `is_demo` lets later features label demo stock ("Example listing", Feature 08), exclude it from alerts (11), comparables (12) and the search index (13), and route demo enquiries to a notice (10).

### 10. Testing
- Factories for `Listing` build through §6 and §5 (Feature 01 §14 rule). A factory that hand-sets `listed_at` or `title` fails review.
- The seed runs in CI at `--listings 500` on every build (fast smoke), and at 5,000 in the nightly job.

---

## Key Decisions

**Typed columns for anything filterable, JSONB for everything else.** Report §2 notes
that the real platform uses a SQL + MongoDB mix for exactly this tension. Postgres
JSONB covers the document side without a second database. The rule is that a field
moves out of JSONB into a typed column the moment any feature filters or sorts on it.

**`variant` stays free text in the MVP.** A full trim/derivative taxonomy (CAP-code
style) is a licensed data product. A free-text variant, with make, model, fuel,
transmission and engine size structured, gets 95% of the search value.

**Prices in integer pence, mileage in integer miles.** No floats anywhere in money or
distance comparisons.

**Text + CHECK instead of native Postgres enums.** Rejected: `CREATE TYPE … AS ENUM`.
Adding a value to a native enum can't be used in the same transaction, and removing or
renaming one means recreating the type and rewriting every dependent column. Fuel and
body types *will* change (Feature 07's `SearchParams` versioning exists for that), so
the cheaper-to-evolve form is chosen before any data exists.

**Moderation is a separate column from the dealer lifecycle.** Rejected: adding `held`
and `hidden` to `status`. A dealer's "reserved" and an admin's "hidden pending review"
are independent facts. Folding them together loses the dealer's state when an admin
hides a listing, and makes every status transition in Feature 05 aware of moderation.
Keeping both, plus one `publicly_visible()` predicate, means Feature 14 can be added
without touching any query in features 07–13.

**System-owned columns never bump the lock token.** Moderation, `listed_at` and dealer
relocation are written by admins and background work. If they bumped `updated_at`,
every one of them would throw away a dealer's in-progress edit with a 409. This is the
Yaqlo failure, prevented structurally rather than by care.

**`listed_at` separate from `published_at`.** A reader/writer mismatch caught at design
time: Feature 11's alert watermark and Feature 07's newest-first sort both mean "became
visible to buyers", which `published_at` stops meaning as soon as Feature 14 can hold a
listing at publish.

**Demo data is a first-class, labelled concept.** Report §6 names cold start as the
biggest risk. Demo stock lets the product launch looking alive. `is_demo` lets us
label it and keep it out of anything that would mislead (alerts, comparables, the
search index), and remove it per region as real dealers join.

**Taxonomy load and demo seed are separate commands.** Production needs the taxonomy
on every deploy; it may never need demo stock. One command for both would either
skip the taxonomy in production or seed demo cars by accident.

**ULEZ compliance is derived, not entered.** The real rule depends on the exact Euro
standard, which we don't have, so the UI says "Likely ULEZ compliant" and links to
TfL's checker. It's a high-value filter for London buyers at near-zero cost.

## Acceptance Criteria

**Schema**
- Migrations create all tables, CHECKs and indexes. `alembic upgrade head → downgrade base → upgrade head` succeeds and `alembic check` reports no drift.
- Inserting a listing with `price_pence = 0`, `mileage = -1`, `fuel_type = 'steam'`, or `status = 'archived'` with no `archived_at` fails **at the database** (direct SQL, bypassing the app)
- Every CHECK-backed column's allowed values equal its Python `StrEnum` (introspection test)
- New `Listing` and `Dealer` ids are UUIDv7 and sort by creation time

**Taxonomy**
- `load_taxonomy` run twice: the second run reports 0 inserts and 0 updates. Removing a model from the CSV sets `is_active = false` and an existing listing on that model still loads.
- An attempt to change a slug through the service is rejected; changing `name` succeeds
- `"VW"`, `"VOLKSWAGEN"` and `"volkswagen"` all resolve to the same `Make` through `MakeAlias`

**Visibility & system-owned columns**
- `publicly_visible()` is table-tested over every `status × moderation_status` combination: only `active`/`reserved` with `clear` and no `archived_at` pass
- `system_update(listing_id, moderation_status='hidden')` leaves `updated_at` unchanged, and a dealer PATCH carrying the pre-change token still succeeds
- `listed_at` is set the first time a listing becomes visible, stays null while it is held, and is unchanged by unpublish → republish

**Specs**
- A `specs` payload with an unknown key, or over 16 KB, returns 422. A valid payload is stored with `specs_version = 1`.

**Seed**
- `seed_demo --listings 5000` completes in under 2 minutes with network access blocked. `--profile perf` creates 50,000 listings in under 10 minutes and is refused with `ENVIRONMENT=production`.
- Two runs with the same `--random-seed` produce byte-identical exports of the listing table (excluding ids and timestamps)
- `verify_listing_invariants()` passes on seeded data: every `title`, `ulez_compliant`, `vrm` and `listed_at` equals what §6/§5 compute
- `seed_demo --reset --region NW` removes only demo rows in that region. A manually created non-demo listing, and demo rows in other regions, survive. The reset raises no FK error with every table defined so far (re-run by each later feature that references `listing` or `dealer`).
- `seed_demo` in production without `--region` and `--confirm-production` exits non-zero
- A query for `publicly_visible() AND make=Ford AND price between £5k and £10k ORDER BY price` over the seeded data runs in under 50 ms (EXPLAIN shows an index scan)
- Price sanity holds: median price for 1-year-old cars > 5-year-old > 10-year-old, within each make

---

## Scale review — what was added, and what was deliberately deferred

Reviewed against large-scale concerns, building on Feature 01's conventions rather
than redefining them.

**Added (P0/P1), with their sections:**
- P0: minimal `Dealer` core table so `Listing.dealer_id` and demo dealers exist before Feature 04 (§2)
- P0: `moderation_status` column and the single `publicly_visible()` predicate, so Feature 14 needs no query changes in 07–13 (§3, §5)
- P0: system-owned columns written through `system_update()` without bumping the lock token (§5)
- P0: `listed_at` as the visibility watermark for alerts and the newest-first sort (§3, §5)
- P0: seed through the real derivation functions plus an invariant check (§6, §8)
- P0: `ON DELETE CASCADE` rule for every table referencing `listing`/`dealer`, so the per-region demo reset keeps working (§9)
- P1: text + CHECK enumerations with a drift test (§1)
- P1: database-level CHECK constraints for ranges and state consistency (§3)
- P1: taxonomy loader separate from the demo seed, idempotent, deactivate-not-delete, immutable slugs (§1)
- P1: `MakeAlias`/`ModelAlias` tables for external-string mapping (§1)
- P1: versioned, validated `specs` with a controlled equipment vocabulary (§4)
- P1: `normalise_vrm()` and the other derivations as single functions (§6)
- P1: deterministic seed, `--profile perf` 50k dataset, region scoping, production guard (§8, §9)
- P1: offline postcode-district centroid file reused as the geocoding fallback (§8)

**Ownership moves:** attaching seed images moves to Feature 06 §8 (the owner of
`ListingImage`). Search-specific index tuning is owned by Feature 07 §5; this feature
ships only the starter set.

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| Licensed derivative/trim taxonomy (CAP-style codes) | Dealer CSV/feed import (Phase 2 item 1), or a valuation provider that keys on derivative codes |
| Model generations / year ranges on `Model` | Search UX research shows buyers filtering by generation, or the alias table can't disambiguate |
| Admin UI for editing taxonomy and aliases | More than ~5 alias additions a week from Feature 05's unmatched-lookup log |
| Exact Euro-standard ULEZ data | A data source for Euro standard per vehicle is licensed |
| GIN index on `specs` | The first spec-based filter is added (and that field should become typed per §4 instead) |
| Table partitioning of `Listing` by status | `Listing` exceeds ~5M rows, or archived rows exceed 80% of the table |

**Scale traps to avoid:** a second document database (MongoDB) for specs, as in report
§2; a full trim taxonomy built in-house; scraping real listings to make the demo look
realistic.
