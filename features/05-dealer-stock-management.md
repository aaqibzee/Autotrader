# Feature 05 — Dealer Stock Management

**Status:** Not Started
**Priority:** Must-Have
**Milestone:** M2 Supply
**Effort:** 9h optimistic / 19h realistic / 29h pessimistic
*(raised from 7/14/22h after a scale review: the transition state machine, domain
events that later features subscribe to, the moderation hook, stats ownership and
plate-lookup failure paths are defined here so features 08–14 never patch the listing
write path. See "Scale review" at the end.)*
**Depends on:** 02, 04

## Description

The dealer's core workflow: add a car, describe it, price it, publish it, and later
mark it reserved or sold. Report §3 describes the real "Retailer" stock management
dashboard. This is its MVP subset: **manual entry**, accelerated by a **registration
plate lookup** that prefills most fields from DVLA/DVSA data, so a dealer can list a
car in under 3 minutes. This feature is the **only writer of dealer-owned listing
fields**. Everything else that reacts to listing changes does so through the events
in §4.

---

## Scope

### 1. Listing lifecycle (state machine)
```
draft ──publish──▶ active ──reserve──▶ reserved
  ▲                │  ▲  ◀──unreserve──    │
  └──unpublish─────┘  │                    │
                      │ sell (from active or reserved)
                      │                    ▼
                      └──unsell (≤ 7 d)── sold ──(30 days, system)──▶ archived
any non-archived state ──archive──▶ archived ──restore──▶ draft
```
| Action | From | To | Side effects |
|---|---|---|---|
| `publish` | draft | active | §2 pipeline |
| `unpublish` | active | draft | |
| `reserve` / `unreserve` | active ↔ reserved | | |
| `sell` | active, reserved | sold | `sold_at = now()` |
| `unsell` | sold (within 7 days of `sold_at`) | active | `sold_at = null` (for "sold by mistake") |
| `archive` | any except archived | archived | `archived_at = now()` |
| `restore` | archived | draft | `archived_at = null`, `sold_at = null` |

- **One function, `listings.transition(listing_id, action, actor)`**, performs every transition. It runs a conditional `UPDATE … WHERE id = :id AND status IN (:allowed_from) RETURNING *`. Zero rows means 409 `invalid_transition` with the current representation, so two staff pressing "Sold" at once produce one success and one clear conflict, never a double transition.
- Transitions don't require the lock token (they're one-tap quick actions), but they **do** bump `updated_at`, because status is a dealer-owned field. An open edit form on a car that was just sold should get a 409, not overwrite it.
- After every transition: `visibility.on_change()` (Feature 02 §5) and a `ListingStatusChanged` event (§4).
- **A `removed` listing (Feature 14 takedown) can't be published again** (409 `listing_removed`). A `held` listing shows "Under review" in the stock table. The dealer can still unpublish or archive it.
- **Sold listings auto-archive** 30 days after `sold_at` (beat task daily at 03:00 Europe/London, batches of 500, idempotent, `actor = system`). Until then Feature 08/13 serve the sold page.

### 2. Publish pipeline
`POST /dealer/listings/{id}/publish` (accepts `Idempotency-Key`, Feature 01 §5):
1. `require_approved_dealer` (Feature 04 §9), else 403 `dealer_not_approved`
2. **Publish validator** `validate_publishable(listing)`: make, model, year (≤ current year + 1), registration date (not in the future), mileage, price, fuel, transmission, body type, **≥ 3 `ready` images** (Feature 06), description ≥ 50 characters. Returns 422 listing every failing field. It is also added to Feature 02 §8's post-seed invariant check.
3. **Live-listing cap:** at most 500 `active` + `reserved` listings per dealer during the beta (`MAX_LIVE_LISTINGS_PER_DEALER`), else 409 `listing_limit_reached`. It bounds the damage from a compromised or abusive dealer account.
4. `transition(… 'publish')` sets `published_at`, copies the dealer's lat/long, and (re)derives `title` and `ulez_compliant` via Feature 02 §6.
5. **Moderation hook:** `moderation.evaluate(listing, trigger="publish")` returns `clear` or `held` and writes `moderation_status` through `system_update()`. Feature 14 §4 implements the checks. Until Feature 14 ships, the hook is a no-op returning `clear`.
6. `visibility.on_change()` sets `listed_at` if the listing is now visible, then emits `ListingPublished`.

### 3. Editing and optimistic locking
- `PATCH /dealer/listings/{id}` requires `updated_at` (Feature 01 §5). A mismatch returns 409 `stale_update` with the current representation, which Feature 03 §3's `ConflictDialog` renders.
- The PATCH schema contains **only dealer-owned fields**. `moderation_status`, `listed_at`, coordinates, `is_demo`, `title` and `ulez_compliant` are not accepted (derived or system-owned, Feature 02 §5–§6).
- **Validation:** Feature 02's CHECK ranges mirrored in Pydantic (so users get field errors, not 500s), `specs` through `ListingSpecsV1` (Feature 02 §4), and the description stored as plain text (control characters stripped except newlines, runs of blank lines collapsed to two, ≤ 5,000 chars). HTML is not parsed. It is escaped at render (Feature 08).
- **Editing a live (active/reserved) listing re-runs the publish validator**, so an edit can't leave a public listing with no price or fewer than 3 photos (422, listing unchanged). A change to price, description or VRM on a live listing re-runs `moderation.evaluate(listing, trigger="edit")`.
- **Autosave is for drafts only.** Drafts autosave 3 s after the last change and on blur, carrying and refreshing the lock token. A live listing has an explicit "Save changes" button. Rejected: autosaving live listings, which would publish half-typed prices and descriptions to buyers.
- **Price changes** write a `ListingPriceChange(listing_id, old_pence, new_pence, changed_at, actor_user_id)` row and emit `ListingPriceChanged` **in the same transaction** as the update. Feature 11 (price-drop alerts) and Feature 12 (indicator recompute) read them.
- `POST /dealer/listings/{id}/duplicate` creates a draft copying vehicle fields, specs, price and description, but **not** the VRM, mileage, registration date or images.

### 4. Domain events (how later features react without patching this one)
- `core/events.py` is a small in-process registry: `subscribe(EventType, handler)` and `emit(event)`. Listing events: `ListingPublished`, `ListingUpdated(changed_fields)`, `ListingPriceChanged(old, new)`, `ListingStatusChanged(old, new)`, `ListingVisibilityChanged(visible)`.
- Handlers run **synchronously inside the emitting transaction** and may only (a) write their own module's tables or (b) call `dispatch()` (Feature 01 §7). Heavy work always goes through `dispatch()`, so it runs after commit and never for a rolled-back change.
- Subscribers register in `app/modules/<module>/subscriptions.py` at startup. **The `listings` module never imports a subscriber**, which import-linter enforces (Feature 01 §10). Known subscribers: Feature 08 (CDN purge on visibility change), Feature 12 (indicator recompute on price change or publish), Feature 14 (dealer notifications on holds).
- Events are not persisted. A handler that needs durability uses the outbox pattern (Feature 01 §7).

### 5. Plate lookup (VRM → prefill)
- `POST /dealer/vehicle-lookup {vrm}` normalises the VRM (Feature 02 §6), then calls in parallel:
  - **DVLA Vehicle Enquiry Service**: make, colour, fuel, year/month of first registration, engine cc, CO₂, tax and MOT status, MOT expiry. API-key auth.
  - **DVSA MOT History API**: model, MOT test history with odometer readings. OAuth client-credentials plus API key. The access token is cached in the cache Redis until 60 s before expiry.
  - Endpoints, auth flows, quotas and caching/display terms for both are **to verify** against current DVLA/DVSA documentation during this feature.
- Both go through Feature 01 §9's shared client (timeouts, breaker). The total lookup budget is 6 s.
  - If **both** fail, return 503 `integration_unavailable` ("Lookup unavailable — enter details manually", Feature 03 §3), never a 500.
  - If **one** fails, return a partial prefill with that source marked `unavailable`.
- **Mapping:** DVLA/DVSA strings resolve through `MakeAlias`/`ModelAlias` (Feature 02 §1) with a fuzzy fallback (≥ 0.9 similarity, single best match only). An unmatched model leaves the field empty for the dealer to pick, never a wrong guess, and upserts a `TaxonomyMiss(source, raw_make, raw_model, count, last_seen_at)` row so missing aliases get added (Feature 02 P2 trigger).
- The response flags each field `source: "dvla" | "mot"`, so the form shows "from DVLA" hints. MOT expiry and check date are stored in `specs` (Feature 02 §4).
- **Caching:** found results for 24 h, "not found" for 1 h, keyed by normalised VRM in the cache Redis.
- **Rate limits** (Feature 04 §5): 200 per day and 30 per minute per dealer.
- **Sanity warnings** (never blocking): entered mileage below the last MOT reading (possible clocking or a typo), average above 40k miles a year, and the same VRM already active in this dealer's stock. A VRM active at *another* dealer is Feature 14's hold check.

### 6. `ListingStats` (owned here; written by 08, 09, 10)
- `ListingStats(listing_id PK/FK ON DELETE CASCADE, views, saves, leads, call_clicks, updated_at)`
- Written **only** through `stats.increment(listing_id, field, by)`, an `INSERT … ON CONFLICT (listing_id) DO UPDATE SET field = GREATEST(field + :by, 0)`. No code path assumes the row exists, and readers `LEFT JOIN` and treat a missing row as zeros. (Reader/writer lesson: seeded or old listings with no stats row must still work.)
- Never touches `Listing`, so counters never bump the lock token (Feature 01 §5 rule)

### 7. Audit trail
- `ListingAuditEvent(listing_id, actor_type: dealer | admin | system, actor_user_id, action, changes JSONB {field: [old, new]}, request_id, created_at)` is written in the same transaction as every create, edit, transition, moderation change (Feature 14) and relocation
- It answers "who changed the price / why was this archived?" for dealer support and disputes. Cursor-paginated. Admins see it in Feature 14. It is retained for the life of the listing plus 24 months.

### 8. Dealer relocation
- `listings.relocate_dealer_listings(dealer_id)` (called by Feature 04 §8 after a postcode change, via `dispatch()`) copies the dealer's new coordinates onto its draft, active and reserved listings in batches of 500 through `system_update()` (Feature 02 §5). No dealer's open edit is invalidated, and sold listings keep their historical location.

### 9. Endpoints and list performance (all via `dealer_scoped` / `get_dealer_owned_or_404`, Feature 04 §9)
- `GET /dealer/listings?status=&q=&sort=&page=`: page size 25. `q` matches title (`ILIKE`) or an exact normalised VRM. Sort by age-in-stock (`published_at`), price or last updated. Counts per status tab come from **one `GROUP BY` query**. Thumbnails, `ListingStats`, price indicator (Feature 12) and moderation state are batch-loaded: **≤ 6 queries per page** (`assert_max_queries`).
- `POST /dealer/listings` (create a draft; ≤ 1,000 drafts per dealer), `GET/PATCH /dealer/listings/{id}`
- `POST /dealer/listings/{id}/{action}` for each §1 action
- `POST /dealer/listings/{id}/duplicate`
- `GET /dealer/listings/{id}/history` (audit events, cursor-paginated)

### 10. UI (`/dealer/stock`)
- Stock table with status tabs (Draft / Live / Reserved / Sold / Archived), search by title or plate, sort, thumbnail, an "Under review" badge for held listings, and views/saves/leads counters (zeros until features 08–10 write them)
- "Add a car": plate entry → prefilled form (with the "lookup unavailable — enter manually" path) → photos (Feature 06) → review → publish
- Edit form: sectioned (Vehicle, Price, Description, Features/equipment checklist from Feature 02 §4's vocabulary, Photos). Drafts show an autosave indicator; live listings have "Save changes".
- Inline quick actions: change price, mark reserved, mark sold, and an "Undo sold" link for 7 days
- Mobile-usable: dealers photograph and list cars on the forecourt from a phone

---

## Key Decisions

**Manual entry plus plate lookup, not feed ingestion.** Report §6 calls dealer feeds
"a long-tail integration problem, not a one-time build." The plate lookup gets most
of the data-entry speed of a feed with none of the format chaos. CSV import is the
first Phase 2 item.

**The plate lookup is an aid, not a source of truth.** DVLA doesn't return model or
variant, and our make/model mapping will have gaps. Every field stays editable, and
nothing auto-publishes from lookup data.

**The VRM is stored but never shown in full publicly.** It's used for lookups,
duplicate detection and the valuation (Feature 12). The public page shows nothing, or
only the age identifier, in line with common marketplace practice.

**One transition function with a conditional update.** Rejected: read the status,
check it in Python, then write. Under two concurrent requests both pass the check.
The conditional `UPDATE … WHERE status IN (…)` makes the database the arbiter.

**In-process domain events, not direct calls into later modules.** Rejected: calling
`valuations.recompute()` and `cdn.purge()` from `update_listing`. That makes the
listings module depend on every later feature, breaks the import-linter boundary,
and turns each new feature into an edit of this one. Rejected also: a message broker
for events. Celery plus after-commit dispatch already gives durability where it
matters.

**Optimistic locking on edits; counters and system fields elsewhere.** Two staff
editing the same car is realistic on a busy forecourt. Yaqlo learned that the lock
token must not be bumped by background writes, so counters live in `ListingStats`,
and moderation, `listed_at` and relocation go through `system_update()`.

**Autosave only for drafts.** A draft is private, so saving every few seconds is
pure convenience. A live listing is public, so saving is a publishing act and needs
an explicit button.

**Price changes are logged** (`ListingPriceChange`), because Feature 11 alerts on
price drops and Feature 12's indicator may later use price history.

## Acceptance Criteria

**Lifecycle**
- Every `(status, action)` pair is table-tested: allowed pairs reach the target state; all others return 409 `invalid_transition` with the current representation
- Two concurrent `sell` requests on the same listing produce exactly one 200 and one 409
- `unsell` succeeds within 7 days of `sold_at` and returns 409 after
- Sold listings archive automatically 30 days after `sold_at`. Re-running the beat task is a no-op.
- A `removed` listing cannot be published (409 `listing_removed`)

**Publish**
- Publishing without the required fields returns 422 listing each missing field. Only `ready` images count toward the 3-photo minimum.
- A pending dealer gets 403 `dealer_not_approved`
- A dealer at 500 live listings gets 409 `listing_limit_reached` on the next publish
- Retrying publish with the same `Idempotency-Key` performs one transition and emits one `ListingPublished`
- A moderation hook returning `held` leaves the listing `active` + `held`, not publicly visible, with `listed_at` null

**Editing**
- A PATCH with a stale `updated_at` returns 409 `stale_update` with the current version
- A PATCH that includes `moderation_status`, `listed_at`, coordinates or `title` is rejected with 422 and changes nothing
- Editing a live listing so it fails the publish validator returns 422 and leaves the listing unchanged
- A price change writes `ListingPriceChange` and `ListingAuditEvent` rows and emits `ListingPriceChanged`. If the transaction rolls back, none of these exist and no subscriber task is dispatched.
- Autosave requests are sent for drafts only. Editing a live listing sends nothing until "Save changes".
- `duplicate` creates a draft without the VRM, mileage, registration date or images

**Events & boundaries**
- A test subscriber registered for `ListingPublished` receives the event, and a dispatched task from it runs only after commit
- `modules.listings` importing any subscriber module fails import-linter

**Plate lookup**
- A valid VRM prefills make, fuel, colour, year, engine size and MOT mileage. An unknown VRM returns "not found" and is cached for 1 hour.
- With DVLA timing out, the response is 503 `integration_unavailable` within 6 s, never a 500. With only MOT down, a partial prefill marks MOT `unavailable`.
- A second lookup of the same VRM within 24 hours makes no provider call (call-count assertion)
- The 201st lookup by one dealer in a day returns 429
- An unmatched make or model leaves the field empty and increments a `TaxonomyMiss` row
- Entered mileage below the last MOT reading shows a warning but still saves

**Stats, relocation & audit**
- Recording a view or save does not change `Listing.updated_at`. A listing with no `ListingStats` row shows zero counters.
- `relocate_dealer_listings` updates active listings' coordinates without changing their `updated_at`
- Every transition and edit writes a `ListingAuditEvent` with the actor and `request_id`

**Tenancy & performance**
- Cross-dealer access to any listing endpoint returns 404 (Feature 01 §14 harness)
- The stock list runs in ≤ 6 queries per page and under 150 ms for a dealer with 1,000 listings
- Feature 02's demo reset still succeeds with `ListingStats`, `ListingPriceChange`, `ListingAuditEvent` and `TaxonomyMiss` present (cascade rule)

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: single `transition()` with a conditional update and a full transition table (§1)
- P0: publish pipeline with a moderation hook, so Feature 14 plugs in without editing this feature (§2)
- P0: in-process domain events with after-commit dispatch for subscribers (§4)
- P0: autosave restricted to drafts (§3)
- P0: `ListingStats` ownership with upsert writes and LEFT JOIN reads (§6)
- P0: PATCH schema limited to dealer-owned fields (§3)
- P0: dealer relocation via `system_update()` (§8)
- P1: publish validator re-run on live edits, and moderation re-evaluated on material edits (§3)
- P1: plate-lookup auth, partial results, negative cache, 6 s budget, `TaxonomyMiss` log (§5)
- P1: live-listing and draft caps (§2, §9)
- P1: `unsell` within 7 days (§1)
- P1: `ListingAuditEvent` trail (§7)
- P1: N+1-guarded stock list (§9)
- P1: idempotent publish (§2)

**Ownership moves:** none. This feature now *provides* `ListingStats` (written by 08,
09, 10), the listing events (consumed by 08, 12, 14) and the moderation hook
(implemented by Feature 14 §4).

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| Dealer CSV import, then feed/DMS ingestion | Phase 2 item 1; first dealer with more than ~50 cars in stock |
| Buffered counters (Redis increments flushed to `ListingStats`) | Row-lock waits on `listing_stats` show in `pg_stat_statements`, or > 50 increments/s on one listing |
| Persisted event log / event-sourced listing history | A second consumer needs to replay events, or an extraction of a module into a service |
| Bulk actions in the stock table (multi-select price change, archive) | Dealers with more than 100 live listings ask for it |
| Offline-first listing creation on mobile (local draft queue) | Field reports of lost work from forecourt connectivity, despite server-side draft autosave |
| Field-level merge in `ConflictDialog` | Conflict dialogs exceed ~1% of saves |

**Scale traps to avoid:** an ingestion pipeline for heterogeneous dealer feeds in the
MVP; a Kafka-style event bus for in-process listing events.
