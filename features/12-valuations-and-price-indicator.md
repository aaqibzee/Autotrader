# Feature 12 — Valuations & Price Indicator

**Status:** Not Started
**Priority:** Must-Have
**Milestone:** M4 Engagement
**Effort:** 10h optimistic / 20h realistic / 32h pessimistic
*(raised from 8/16/28h after a scale review: a hard provider-cost budget, a durable
provider-result cache, a production guard against stub values, set-based nightly
recompute, licence-aware display and saved-valuation erasure. Still flagged by report
§4 as an integration bottleneck. See "Scale review" at the end.)*
**Depends on:** 02, 04, 05, 07, 08, 09

## Description

Two related features:
1. **"Value my car"**: a consumer enters a plate and mileage and gets a retail / private / part-exchange estimate range. Report §3: "Valuations tool: Retail / Trade / Part-exchange valuations." It's a strong acquisition hook, since sellers are future buyers.
2. **Price indicator**: every listing gets a badge (*Great price / Good price / Fair price / Higher price / No rating*) comparing its price with the expected market value. Report §3 notes the real site's "price indicator" rating.

Report §4 and §6 are explicit that the real platform's valuation accuracy is a
**proprietary data moat** that can't be rebuilt: "any clone's valuation feature is
only as good as whatever third-party API you bolt on." This feature is designed
around that limit. It uses licensed data where available, falls back to transparent
on-platform comparables, and **shows "No rating" rather than a made-up number.**
Every provider call costs money, so this feature also bounds that cost.

---

## Scope

### 1. Provider adapter and selection
```python
class ValuationProvider(Protocol):
    def value(self, vrm: str, mileage: int) -> ValuationResult | None: ...
# ValuationResult: retail_pence, private_pence, trade_pence,
#                  confidence (high | medium | low), provider, as_of
```
- Implementations: `StubProvider` (deterministic from Feature 02 §8's depreciation curve, for dev and tests) and **one commercial UK provider**, chosen during this feature
- **Provider selection is the first task of this feature.** Candidates to evaluate include the established UK valuation data vendors (e.g. Cap HPI, Glass's, and API-first aggregators). Pricing, licence terms and coverage are **unverified and must be checked directly**. Criteria:
  - per-call cost at the expected volume
  - a licence that allows **displaying values to consumers** (not just internal use), and whether derived values (a badge, an "expected price") may be shown publicly
  - retail + trade + private coverage, and a mileage adjustment
  - a sandbox, plus caching rights (how long a result may be stored and reused)
- A **shared contract test suite** runs against both implementations (recorded sandbox responses for the real one). Swapping providers is a config change (`VALUATION_PROVIDER`).
- Calls go through Feature 01 §9's shared client (timeout overridden to 4 s, circuit breaker). An open breaker means `IntegrationUnavailable`.

### 2. Durable provider cache
- `ProviderValuation(vrm_hmac, mileage_band, provider, result JSONB, fetched_at)`, unique `(vrm_hmac, mileage_band, provider)`, in **Postgres**, not the cache Redis. Rejected: Redis. Its `allkeys-lru` policy (Feature 01 §8) would evict paid results under memory pressure, and we'd pay for them again.
- `mileage_band` = 5,000-mile bands. `vrm_hmac` = HMAC of the normalised VRM (Feature 02 §6), so this table and its logs don't hold plates.
- Reuse windows (subject to the provider's caching terms, to verify): **7 days** for consumer valuations, **30 days** for listing indicators. Rows older than 90 days are purged nightly.

### 3. Cost controls
- **Monthly call budget:** `ProviderUsage(month, calls)`, incremented atomically in Postgres *before* each call. At 80% of `VALUATION_MONTHLY_CALL_BUDGET`, Feature 15's alert fires. At **100%**, the provider path switches off for the rest of the month: indicators use comparables only, and "Value my car" shows "temporarily unavailable". No surprise invoice.
- **Who may trigger a call:** a consumer valuation (rate-limited, §5), and a listing indicator **only** when the listing has a VRM, isn't demo, and has no cached result inside the 30-day window. **The nightly refresh never calls the provider**; it recomputes from cached provider results and comparables (§6). Rejected: re-valuing every listing nightly, which would make cost scale with listings × days.
- Metric `valuation_provider_calls_total{trigger}` and a `valuation_budget_used_ratio` gauge

### 4. Production honesty guard
- If `ENVIRONMENT=production` and `VALUATION_PROVIDER=stub`, the app boots with the `value_my_car` flag (Feature 01 §2) **forced off** and the indicator's provider path disabled (comparables only), and logs a warning at boot. Stub-derived numbers are structurally impossible to show to the public.
- With no real provider contract, the MVP launches on comparables only, with "Value my car" hidden behind the flag (Feature 03 §5 hides its header link).

### 5. "Value my car" (`/value-my-car`)
1. Plate entry, then confirm the vehicle using Feature 05 §5's DVLA lookup service (consumer rate limits, below). A "Not your car?" option re-enters. A DVLA outage shows "We can't look up plates right now — try again later" (Feature 03 §3), never a 500.
2. Mileage (0–1,000,000, warned if implausible for the age) plus condition. Condition is a documented, configurable adjustment: excellent **+3%**, good **0%**, fair **−7%**.
3. Result: **ranges, not single figures** ("Part exchange: £8,200–£8,900"). The width depends on provider confidence: high ±4%, medium ±7%. **Low confidence or no result shows "We can't value this car accurately"**, never a guessed figure. Plus the provider name, an "as of" date, and a plain-English disclaimer ("an estimate, not an offer").
4. CTAs: "See similar cars for sale near you" (a prefilled `SearchFilters`, Feature 07 §3) and "Save this valuation" (requires a consumer account, Feature 09)
- **Rate limits** (Feature 04 §5; policy table in Feature 14 §6): 5 per day per IP signed out, 20 per day per account, plus a global daily cap of 1/20 of the monthly budget. Over the limit → 429 with a sign-in prompt for signed-out users. Provider calls cost money, and valuations are a scraping target.
- **Data:** VRM and mileage aren't logged (Feature 01 §11 redaction covers VRMs). Anonymous valuations are kept only as the HMAC-keyed cache. `SavedValuation(user_id, vrm, mileage, condition, result JSONB, created_at)` (max 20 per user) is registered with Feature 09 §6's personal-data handler: deleted on erasure, included in export.

### 6. Price indicator (listings)
**Expected value**, `valuations.expected_value(listing) -> Expected | None` (also used
by Feature 14 §4's price check):
1. **Provider path:** the listing has a VRM, a cached or newly fetched provider result exists (§2–§3) with confidence `high` or `medium`, and the provider path is enabled → expected = `retail` adjusted to the listing's mileage band
2. **Comparables fallback:** publicly visible plus sold-in-last-90-days listings with the same model, year ± 1 and mileage ± 15k, **excluding demo listings when rating a real one**. Requires **n ≥ 8**. Expected = median price, adjusted linearly for the mileage difference (slope from the same sample).
3. Neither available → **"No rating"**

| Ratio `price / expected` | Badge |
|---|---|
| ≤ 0.93 | Great price |
| 0.93–0.98 | Good price |
| 0.98–1.04 | Fair price |
| > 1.04 | Higher price |

(Thresholds are config values, tuned once real data exists.)

- **Triggers:** subscribes to Feature 05 §4's `ListingPublished` and `ListingPriceChanged` events and `dispatch()`es `recompute_indicator(listing_id)` on the `default` queue after commit (target: within 1 minute)
- **Nightly refresh** (03:30 Europe/London): **set-based**. One SQL pass computes comparables statistics per `(model, year, mileage band)` group with window functions, then upserts indicators for all publicly visible listings in batches of 1,000. It is never a query per listing. Target: under 5 minutes at 50k listings.
- **Staleness:** an indicator older than 48 h is shown as "No rating", so a broken nightly job degrades honestly instead of showing week-old ratings
- Demo listings are rated only against demo comparables, labelled as such, and never mixed with real ones

### 7. Storage and reads
- `ListingPriceIndicator(listing_id PK, FK ON DELETE CASCADE, rating, expected_pence, method (provider | comparables | none), sample_size, provider, inputs_as_of, computed_at)`, upserted, so it **never touches `Listing.updated_at`** (Feature 01 §5 rule)
- Batch-loaded by search cards (Feature 07 §8), the detail page (Feature 08 §4) and the dealer stock table (Feature 05 §9). Index on `(rating)` for Feature 07's `price_rating` filter. That filter is an additive optional field, so no `params_version` bump (Feature 07 §3).

### 8. Display and explainer
- The badge is always text plus colour (never colour alone, Feature 03 §1)
- The public "How we rate prices" explainer names **that** listing's method, sample size and date ("Compared with 14 similar cars listed in the last 90 days, 3 Oct 2026"). **The expected price itself isn't shown publicly** unless the provider licence allows displaying derived values (to verify). Only the badge is shown.
- The dealer stock table (private) shows the rating and "£X above expected" as a repricing hint (a first step toward report §3's "pricing/repricing suggestions")
- "No rating" carries a reason in the explainer ("Not enough similar cars to compare yet")

### 9. Observability
- Metrics: provider calls by trigger, budget ratio, provider latency and breaker state (Feature 01 §12), indicator recompute lag, nightly duration, and the **rating distribution**. Feature 15 alerts if more than 60% of real listings are "Great price", or more than 60% are "Higher price", which indicates broken thresholds or inputs rather than a market fact.

---

## Key Decisions

**The adapter is designed for the provider to be absent.** The MVP can launch on
the stub plus comparables if no provider contract is signed in time. The stub is
never shown to consumers as a real valuation (§4 enforces it). With no real provider,
"Value my car" is hidden behind a feature flag.

**A hard monthly budget, and no nightly provider calls.** A per-call API with a
nightly refresh multiplies cost by listings × 30. The provider is consulted once per
listing per cache window. When the budget runs out, the product degrades to
comparables, which it already supports.

**Provider results are cached in Postgres, not Redis.** A cache that can evict paid
data under memory pressure turns a memory spike into a bill.

**Demo listings are excluded from comparables when rating real listings.** Synthetic
prices from the seed curve must not set the price of real cars.

**Ranges and disclaimers, and no figure at low confidence.** A single "Your car is
worth £8,450" invites complaints and reads like an offer. The real platform's moat is
accuracy, so the clone's defence is honesty about uncertainty.

**Stale indicators turn into "No rating".** A rating computed from last week's market
is a fabricated claim about today's. Hiding it is the honest failure mode.

**No in-house ML.** This is explicitly out of scope per report §4. The comparables
method is a transparent median, not a model, and the explainer says so.

## Acceptance Criteria

**Provider & cache**
- `StubProvider` and the real provider both pass the shared contract test suite. Swapping them is a config change.
- A provider timeout or 5xx falls back to comparables within 5 s total, and the user sees a range or "unavailable", never a 500
- A second valuation of the same VRM and mileage band within 7 days makes no provider call (call-count assertion), including after the cache Redis is flushed
- `ProviderValuation` rows contain no plaintext VRM

**Cost**
- At 100% of the monthly budget, the next listing publish makes no provider call and rates by comparables, and "Value my car" shows "temporarily unavailable". At 80%, the budget alert metric crosses its threshold.
- The nightly refresh makes zero provider calls (call-count assertion over a full run)
- A demo listing never triggers a provider call

**Honesty**
- Booting with `ENVIRONMENT=production` and `VALUATION_PROVIDER=stub` forces `value_my_car` off and disables the provider path
- A low-confidence provider result shows "We can't value this car accurately", not a range
- With fewer than 8 comparables and no provider result, the rating is "No rating", with its reason in the explainer
- An indicator older than 48 hours is rendered as "No rating"
- A real listing's comparables never include demo listings (test with mixed data)
- The public explainer names the method, sample size and date actually used, and doesn't show the expected price

**Recompute**
- A price change triggers a recompute within 1 minute, and the listing's `updated_at` is unchanged by it. A rolled-back price change triggers nothing.
- The nightly refresh rates 50,000 listings in under 5 minutes, without one query per listing (query-count assertion on a 1,000-listing batch)

**Value my car & data**
- Condition adjustments apply exactly +3% / 0% / −7% to the provider figures
- The signed-out valuation rate limit (5/day/IP) returns 429 with a sign-in prompt
- A DVLA outage during plate confirmation shows the retry message, never a 500
- Saved valuations are deleted on account erasure and included in `GET /me/export`. The 21st saved valuation returns 409.

**Observability**
- A test dataset where 70% of listings rate "Great price" raises the distribution alert metric

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: hard monthly provider budget with comparables-only degradation (§3)
- P0: no provider calls from the nightly refresh, and none for demo listings (§3)
- P0: durable Postgres cache of provider results, keyed by VRM HMAC (§2)
- P0: production guard against stub values (§4)
- P0: set-based nightly recompute (§6)
- P0: licence-aware display, with the expected price not shown publicly until verified (§1, §8)
- P0: saved-valuation erasure and export (§5)
- P1: confidence-dependent range widths, and no figure at low confidence (§5)
- P1: staleness → "No rating" (§6)
- P1: `expected_value()` service shared with Feature 14 (§6)
- P1: global daily valuation cap (§5)
- P1: rating-distribution sanity alert (§9)
- P1: event-driven recompute after commit (§6)
- P1: indicator table read paths and index (§7)

**Ownership moves:** none. This feature now *provides* `expected_value()` for Feature
14 §4's price-outlier check.

**Held for user decision:** none. The third-party adapter with the "No rating" fallback
is kept exactly as decided.

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| Trended valuations (6-month history/forecast, report §2) | A provider offers it under a display licence, or Phase 2 dealer analytics |
| Part-exchange flow ("value your car, then browse with that budget") | Phase 2 item 4 |
| Using `ListingPriceChange` history in comparables (time-adjusted prices) | Comparables sample sizes regularly exceed ~30, enough to model time effects |
| Second provider / provider fallback chain | Provider outages exceed the breaker's tolerance more than monthly, or coverage gaps exceed ~10% of lookups |
| Valuation fraud detection (scripted plate enumeration beyond rate limits) | Budget burn from valuations exceeds expectations with rate limits in place |
| Dealer-facing valuation tool (trade prices for stock purchasing) | Phase 2 dealer subscriptions |

**Scale traps to avoid:** building an in-house ML valuation model (report §4: the
moat is proprietary data, not code); re-valuing the whole inventory against the
provider on a schedule.
