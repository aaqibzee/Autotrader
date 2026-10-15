# Feature 07 — Search & Browse

**Status:** Not Started
**Priority:** Must-Have (the core consumer experience)
**Milestone:** M3 Discovery
**Effort:** 13h optimistic / 26h realistic / 40h pessimistic
*(raised from 10/20/32h after a scale review: the `SearchParams` contract and its
versioning, a complete `SearchBackend` interface used by alerts and similar cars, a
one-connection request budget, a per-query timeout, pagination stability, and the
k6/EXPLAIN performance harness are defined here. See "Scale review" at the end.)*
**Depends on:** 02, 03, 04, 05

## Description

Find a car: location plus filters, sorted, paginated, with live result counts. This is
where most consumer sessions start and end. Report §4 says it's "trivial to get
'working', hard to get 'good'" and flags "filter combinatorics + pagination/perf on a
large seeded dataset" as the slow part. This doc defines what "good" means for the
MVP in measurable terms, and defines the search contract that alerts (11), similar
cars (08) and SEO landing pages (13) reuse.

---

## Scope

### 1. Filters (all optional, all combinable)
| Filter | Type | Notes / bounds |
|---|---|---|
| Postcode + distance | text + select (10/25/50/100/national) | Full postcode or outward code (§6). Default is national if no postcode. |
| Make → Model | dependent comboboxes | Model options limited to the chosen make. Up to 20 models within one make. |
| Price | min/max range | £500 steps to £10k, then £1k, then £5k |
| Year | min/max | 1900 – current year + 1 |
| Mileage | max | Presets of 10k, 20k, 30k, 50k, 75k, 100k |
| Fuel, Body type, Transmission, Colour | multi-select | Values from Feature 02 §1 |
| Engine size | min/max | cc |
| Doors, Seats | min | |
| Likely ULEZ compliant | toggle | From Feature 02 §6 |
| Keywords | text ≤ 60 chars | Matches `title` + `variant` only (trigram), not the description |
| Price rating | multi-select | Added by Feature 12 ("Great or good price only") |

### 2. Sort
| Sort | Order (always ending in `id` as a tie-breaker) |
|---|---|
| **Best match** (default) | `score DESC, listed_at DESC, id`, where `score = 0.7 × recency + 0.3 × photos`. `recency = 0.5 ^ (days since listed_at / 14)`, `photos = min(photo_count, 12) / 12`. Demo listings have their score halved, so real dealers' cars rank above otherwise similar demo stock. |
| Price ↑ / ↓ | `price_pence`, `id` |
| Mileage ↑ | `mileage`, `id` |
| Year ↓ (newest) | `year DESC`, `id` |
| Distance ↑ | haversine distance, `id` (only with a postcode) |
| Most recently listed | `listed_at DESC`, `id` (Feature 02 §5's watermark, not `published_at`) |

The `id` tie-breaker makes the ordering total, so a car can't appear on two pages or on
none when many share a price. `photo_count` is a system-owned listing column kept by
Feature 06 (Feature 02 §3).

### 3. `SearchParams`: the contract (owned here; stored by Feature 11, linked by 13)
- Two Pydantic models in `modules/search/params.py`:
  - **`SearchFilters`**: every §1 filter. This is the part saved searches store and alerts match.
  - **`SearchRequest`** = `SearchFilters` + `sort` + `page`
- **Normalisation:** `normalise()` returns a canonical form. Lists are sorted and de-duplicated, defaults are dropped, make/model **slugs are resolved to ids**, postcodes are upper-cased with a single space, and keywords are trimmed, lower-cased and whitespace-collapsed. `canonical_key()` is a SHA-256 of the canonical JSON, used for cache keys (§7), saved-search de-duplication (Feature 11) and canonical-URL decisions (Feature 13). `normalise()` is idempotent.
- **URLs use slugs; storage uses ids.** `?make=ford&model=fiesta,focus` in the address bar, `{make_id, model_ids}` in a saved search. Slugs are immutable (Feature 02 §1), so both stay valid.
- **Versioning** *(moved here from Feature 11)*: stored filters carry `params_version` (`SEARCH_PARAMS_VERSION = 1`). Adding an optional filter whose default means "no filter" does **not** bump the version. Renaming or removing a value or field **does**, and adds an `upgrade_vN_to_vN+1()` function applied on read. A fixture of every historical version is kept in `tests/fixtures/search_params/` and must upgrade and return results on the seed. A saved search must never silently match nothing after a deploy.
- **Validation:** API requests with out-of-bounds or unknown values return 422 with per-field `errors[]`. The SSR results page is lenient instead: it drops filters an old link carries that no longer exist (e.g. a removed colour) and shows a notice ("Some filters in this link are no longer available"), rather than an error page.

### 4. `SearchBackend` interface (every search consumer goes through it)
```python
class SearchBackend(Protocol):
    def search(self, req: SearchRequest) -> SearchPage: ...           # results page + total
    def count(self, f: SearchFilters) -> int: ...
    def facets(self, f: SearchFilters) -> Facets: ...
    def match_ids(self, f: SearchFilters, listed_after: datetime,
                  limit: int) -> list[UUID]: ...                       # Feature 11 alerts
    def similar(self, listing_id: UUID, limit: int) -> list[UUID]: ...  # Feature 08
```
- `PostgresSearchBackend` (§5) is the only implementation in the MVP. Internally it uses `build_listing_query(SearchFilters)`. Nothing outside `modules/search` calls `build_listing_query` directly (import-linter), so a later OpenSearch backend (Phase 2) replaces alerts, similar cars and landing pages too, not just the search page.
- A **shared contract test suite** runs against any backend: identical id sets from `search`, `count`, `match_ids` (minus the time filter) and facet totals.

### 5. Postgres implementation: queries and indexes
- **Base:** `publicly_visible()` (Feature 02 §5), plus filters on typed indexed columns. No feature writes its own status filter.
- **Distance:** a bounding box computed in Python (lat ± r/69, lng ± r/(69·cos lat)) as an indexed prefilter, then the exact haversine via an `IMMUTABLE` SQL function `distance_miles(lat1, lng1, lat2, lng2)` for the radius filter, the distance sort and the displayed distance.
- **Facets:** one `GROUP BY` per facet dimension (make, model within the chosen make, fuel, body, transmission, colour), each excluding its own filter, run **sequentially on the request's single connection**. Rejected: running them concurrently, which takes 6 connections per request from a 15-connection API pool (Feature 01 §6) and fails under modest load.
- **Per-query timeout:** search transactions run `SET LOCAL statement_timeout = '1500ms'`. A timeout returns 503 `search_unavailable` (Feature 03 §3 shows retry), increments `search_timeouts_total`, and doesn't hold a connection for the app role's full 5 s.
- **Indexes** (all partial on `publicly_visible()`, all created `CONCURRENTLY` once `listing` holds production rows, Feature 01 §6). They replace or confirm Feature 02 §7's starter set:

  | Index | Serves |
  |---|---|
  | `(make_id, model_id, price_pence, id)` | make/model + price filter and sort |
  | `(price_pence, id)` | national price sort |
  | `(listed_at DESC, id)` | newest-first sort, alerts (`match_ids`) |
  | `(latitude, longitude)` | bounding box |
  | `(mileage)`, `(year)` | range filters |
  | GIN `gin_trgm_ops` on `(title || ' ' || coalesce(variant, ''))` | keywords (`pg_trgm`, Feature 01 §6) |

  Low-cardinality columns (fuel, body, transmission) get no index of their own. EXPLAIN at 50k decides whether that holds.
- **Plan regression test:** a set of 12 canonical queries (national, postcode + radius, make/model + price, keywords, each sort) runs `EXPLAIN` against the 50k perf dataset (Feature 02 §8) in the nightly CI job and fails on a sequential scan of `listing`.

### 6. Location
- Postcode geocoding uses Feature 04 §7's service: full postcodes via postcodes.io (cached 30 days), and **outward codes** ("M1", "SW1A") resolved locally from Feature 02 §8's district file without a network call
- **postcodes.io unavailable:** a full postcode falls back to its district centroid, and results show "Distances are approximate". Search never fails because geocoding did.
- An unknown postcode returns 422 `postcode_not_found`, which the UI shows as inline guidance, never an empty results page
- The postcode stays in the URL so links can be shared. It never reaches third parties via the referrer (`strict-origin-when-cross-origin`, Feature 01 §4), and logs keep only the outward code (§12, Feature 01 §11).

### 7. Caching and the request budget
| Cache | Key | TTL |
|---|---|---|
| Results page | `search:v1:{canonical_key}:{sort}:{page}` (cache Redis, `cache.get_or_set`, Feature 01 §8) | 60 s |
| Count, facets | `search:v1:{canonical_key}:count` / `:facets` | 60 s |
| Taxonomy (`/taxonomy/*`) | HTTP `Cache-Control: public, max-age=3600` | 1 h |
| Client-side search API GETs at Cloudflare | Cache Rule on `/api/v1/search/*` honouring `Cache-Control: public, s-maxage=30` | 30 s |

- Search responses contain **no per-user data** (save hearts are client islands, Feature 03 §6), so they're safe to cache at the edge.
- Staleness is bounded: a listing that is sold or taken down can show in cached results for up to 60 s. The detail page purges its edge cache on every status, visibility or price change (Feature 08 §5), so it reflects changes within seconds.
- **One request uses at most one DB connection.** Uncached p95 budget at 50k listings:

  | Step | p95 |
  |---|---|
  | geocode (cached) | 5 ms |
  | results page | 80 ms |
  | count | 40 ms |
  | facets (6 queries) | 120 ms |
  | card batch loads | 20 ms |
  | **`GET /search/listings` total** | **< 300 ms** |

### 8. API
- `GET /search/listings?…` returns `{items: ListingCard[], page, page_size, total, facets, suggestions?}`. It follows the Feature 01 §5 pagination shape. `suggestions` appears only when `total = 0` (§10).
- `GET /search/count?…` returns `{total}`: a cheap count used by the "Show 1,204 cars" button
- `GET /taxonomy/makes`, `GET /taxonomy/makes/{slug}/models` (active entries only; inactive ones are still accepted in params so old links work)
- **`ListingCard` payload:** id, slug, title, variant, price, year, mileage, fuel, transmission, cover image variants, photo count, dealer name and town, distance (when a postcode is given), `is_demo`, status (for the Reserved badge), and price rating (Feature 12). It is batch-loaded: **≤ 5 queries per results page** (`assert_max_queries`).

### 9. Limits and abuse
- `page_size` 24, **max 50 pages** (1,200 results). Page 51 returns 400 `page_limit_exceeded` and the UI says "refine your search." This is a deliberate anti-scraping and performance cap.
- Rate limits via Feature 04 §5, policy values in Feature 14 §6: 120 requests/min per IP on `/search/*`, 60/min on `/search/count`
- Bounded input (§1, §3): ≤ 20 models, keywords ≤ 60 chars, numeric ranges validated. A request can't construct an unbounded query.

### 10. UI
- `/cars` (search results): filter sidebar on desktop, filter sheet on mobile with a sticky "Show N cars" button, result header (count, sort, active-filter chips with ✕), grid of `ListingCard`s, pagination
- **URL is the state:** every filter maps to a query param, so back/forward, refresh and shared links all work. SEO landing paths (`/cars/ford/fiesta`, `/cars/in/manchester`) map to the same component (Feature 13 §2).
- **SSR first page** through `apiPublic` (no cookies, Feature 03 §6). Filter changes then fetch client-side.
- "Show N cars" calls `/search/count`, debounced 300 ms, with superseded requests aborted (AbortController), so a slow response never overwrites a newer one
- Home page hero: postcode + make + model + max price, then "Search N cars"
- **Designed states:** loading skeletons; zero results with **suggestions** computed server-side (the count if the radius were widened one step, and if the most restrictive filter were removed; at most 2 extra counts, only when `total = 0`); postcode not found; approximate-distance notice; `search_unavailable` with retry; the refine prompt at page 50
- The result count is announced via `aria-live` (Feature 03 §8)

### 11. Performance budgets and load tests
- Measured on the 5,000-listing seed during development, and on the **50,000-listing perf profile** (Feature 02 §8) for acceptance
- **k6 scenarios** in `ops/k6/search_mix.js` (Feature 01 deferred them to here): 70% results with 2–5 filters + postcode, 20% count, 10% facet-heavy. Target **30 requests/s for 10 minutes** with p95 < 300 ms and errors < 0.5%. Run against **staging, never the shared production VM** (it would degrade the other apps on that box). Feature 15 runs the final pass.

### 12. Observability
- Metrics (Feature 01 §12): `search_latency_seconds{endpoint, cache_hit}`, `search_zero_results_total`, `search_timeouts_total`, cache hit ratio
- One structured log line per search with the normalised filters, the postcode reduced to its outward code, the result count and timing
- A weekly "top zero-result searches" list (make/model/region) for the admin ops dashboard (Feature 14). During cold start it shows where supply is missing.

---

## Key Decisions

**Postgres, not Elasticsearch, for the MVP.** Report §3 infers Elasticsearch/Solr-class
search at the real platform's scale. With tens of thousands of listings, indexed
Postgres plus cached facets meets the latency budget without operating another
stateful service on a shared VM. The `SearchBackend` interface plus the Phase 2
backlog item make the migration deliberate, triggered by a measured p95 breach.

**Every search consumer goes through `SearchBackend`, not just the search page.**
Yaqlo's CLAUDE.md records the failure mode this prevents: two independently written
filters disagreeing. An alert that matches a car the search page wouldn't show is
exactly that bug. If alerts called the Postgres builder directly, swapping in
OpenSearch later would recreate it silently.

**`SearchParams` versioning lives with the type's owner.** Feature 11 stores the
filters, but this feature changes them. If the upgrade functions lived in Feature 11,
a filter rename here could ship without them.

**Facets sequential on one connection.** Concurrency would cut wall time slightly but
multiplies connections per request by six. On a shared VM with a fixed pool, that's
the difference between graceful slowdown and pool exhaustion.

**A total order on every sort.** Offset pagination over a non-unique sort key returns
duplicates and gaps between pages. Users see it as "the same car twice", and scrapers
get inconsistent results.

**Real stock ranks above demo stock in best match.** During cold start, a new real
dealer whose cars sit below hundreds of demo listings would conclude the platform
doesn't work for them.

**Reserved cars show in results with a badge**, matching marketplace convention and
avoiding "where did that car go" confusion. Sold cars do not appear in search.

**Keyword search is deliberately narrow.** Description text is noisy, so title +
variant trigram matching covers "ST-Line", "GTI" or "Tesla Model 3 Long Range"
without irrelevant hits.

## Acceptance Criteria (performance measured on the 50,000-listing perf profile)

**Correctness**
- Facet counts exactly equal the total you get after applying that option (property-based test across random filter combinations)
- For the same filters, `search`, `count`, `match_ids` (minus the time filter) and `similar`'s candidate query agree with the shared contract suite
- Distance sort and radius are correct against known postcode pairs (±0.5 miles). The bounding box never excludes a listing that brute-force haversine includes (property test).
- Paging through every page of a 1,000-result search sorted by price returns each id exactly once, including when many listings share a price
- Draft, sold, archived, `held`, `hidden` and `removed` listings never appear (table-driven test)
- In best match, a real listing ranks above an otherwise identical demo listing

**SearchParams**
- `normalise()` is idempotent. Two URLs differing only in parameter order or explicit defaults produce the same `canonical_key()`.
- Every historical `params_version` fixture upgrades to the current version and returns results on the seed
- The API returns 422 with field errors for 21 models or a 61-character keyword. The SSR page given an unknown fuel value drops it and shows the notice.

**Limits & failure**
- Page 51 returns 400 `page_limit_exceeded`, and the UI shows the refine prompt
- The 121st search request in a minute from one IP returns 429 with `Retry-After`
- A query exceeding 1.5 s returns 503 `search_unavailable`, and the UI shows retry
- With postcodes.io stubbed as down, a full-postcode search returns results with `approximate_distance = true`. An invalid postcode shows inline guidance, never an empty results page.
- One search request checks out at most one DB connection (pool instrumentation test)

**Performance**
- p95 `GET /search/listings` under 300 ms uncached with 4+ filters and a postcode. `GET /search/count` under 100 ms. Cached responses under 30 ms.
- The 12 canonical queries show no sequential scan on `listing` (nightly EXPLAIN test)
- A results page runs in ≤ 5 queries (`assert_max_queries`)
- The k6 `search_mix` scenario sustains 30 requests/s for 10 minutes on staging with p95 < 300 ms and errors < 0.5%

**UI**
- Filters → URL → reload reproduces the exact result set. The back button restores the previous filters.
- Mobile: the filter sheet is usable one-handed, and "Show N cars" updates within 500 ms of a change. A superseded count request is aborted and never overwrites a newer one.
- Zero results shows at least one suggestion with its count (e.g. "Widen to 50 miles: 37 cars")
- The result count is announced to screen readers when it changes

**Observability**
- `search_latency_seconds`, `search_zero_results_total` and `search_timeouts_total` appear on `/metrics`. Search log lines contain only the outward code of a postcode.

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: `SearchFilters`/`SearchRequest` contract with normalisation, a canonical key and versioning with upgraders (§3)
- P0: full `SearchBackend` interface including `match_ids` and `similar`, plus a backend contract suite (§4)
- P0: facets sequential on one connection, with a per-step latency budget (§5, §7)
- P0: total ordering with an `id` tie-breaker (§2)
- P0: per-query 1.5 s timeout with a typed 503 (§5)
- P0: response shape aligned with Feature 01 §5 (§8)
- P1: explicit best-match formula with a demo penalty (§2)
- P1: partial indexes plus a nightly EXPLAIN regression test (§5)
- P1: outward-code support and a postcodes.io fallback (§6)
- P1: caching table including the edge rule for search API GETs (§7)
- P1: bounded input and rate limits (§9)
- P1: lenient SSR handling of stale links (§3)
- P1: zero-result suggestions (§10)
- P1: aborted superseded counts (§10)
- P1: k6 scenario at 30 requests/s run on staging (§11)
- P1: search metrics and a zero-result report (§12)

**Ownership moves:** `SearchParams` versioning moves here from Feature 11 (§3). The k6
scenarios that Feature 01 deferred are written here (§11). Search-specific indexes
are owned here (§5), replacing Feature 02 §7's starter set.

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| OpenSearch/Elasticsearch backend | p95 `GET /search/listings` > 300 ms at real volume after index tuning, or listings > ~250k (Phase 2 item 7) |
| Keyset ("search after") pagination | Raising the 50-page cap becomes a product requirement |
| Approximate counts ("10,000+") | Count queries exceed 40 ms p95 |
| Cache stampede protection (single-flight in `get_or_set`) | Cache-miss bursts visible as DB CPU spikes on popular queries |
| Price/mileage histograms on range sliders | Usability testing shows range filters are hard to set |
| Free-text location ("Manchester") without a postcode | Analytics show > 20% of first searches have no postcode |
| Learned ranking / personalisation | Real usage data exists (report §4: AI can't intuit "good" ranking without it) |
| PostGIS / `earthdistance` | Polygon areas (regions, ULEZ zones) become filters |

**Scale traps to avoid:** running a search cluster on the shared VM for tens of
thousands of documents; a separate search microservice; infinite scroll on SEO pages.
