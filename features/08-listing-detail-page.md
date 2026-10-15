# Feature 08 — Listing Detail Page

**Status:** Not Started
**Priority:** Must-Have
**Milestone:** M3 Discovery
**Effort:** 6h optimistic / 11h realistic / 18h pessimistic
*(raised from 4/8/14h after a scale review: the full status × moderation → HTTP table,
CDN purge on listing changes, never-cached error paths, privacy-preserving view
counting and a dealer preview are defined here. See "Scale review" at the end.)*
**Depends on:** 03, 05, 06, 07

## Description

The page a buyer decides on, and the page search engines index. Report §3 lists
its contents on the real site: "photos, spec, price, seller info, 'price indicator'
rating." It is **server-rendered** (Feature 01 decision) because listing pages are the
main organic-search entry point. It's also the most-cached page on the site, so this
feature defines how a change to a listing reaches buyers quickly despite the cache.

---

## Scope

### 1. URL and canonicalisation
- `/car-details/{listing_id}/{slug}`, where the slug comes from Feature 02 §6 (`2019-ford-fiesta-1-0-ecoboost-st-line`)
- The id is authoritative. A wrong or outdated slug 301s to the canonical one. A malformed UUID is a 404, never a 422 or 500.
- Query strings (UTM tags from alert emails, Feature 11) are ignored for rendering. The canonical link tag always points to the clean URL.

### 2. Page sections (mobile order)
1. **Gallery**: swipeable, image counter, full-screen viewer with pinch-zoom, keyboard arrows on desktop. First image eager-loaded (LCP); variants and alt text from Feature 06 §6.
2. **Headline**: title, variant, price (large, tabular numbers), **price indicator badge** (Feature 12; hidden until that ships), key facts row (year · mileage · fuel · transmission · body · engine)
3. **Primary actions**: "Contact dealer" (Feature 10), "Call" (§6), save heart (Feature 09, client island), share (Web Share API, with copy-link fallback)
4. **Overview grid**: registration year, owners, colour, doors, seats, ULEZ ("Likely compliant" + TfL link), MOT expiry with "as of {mot_checked_at}" when known (Feature 02 §4)
5. **Description**: dealer-written plain text, **HTML-escaped**, line breaks preserved, URLs not turned into links (Feature 05 §3)
6. **Features & equipment**: grouped by Feature 02 §4's vocabulary groups, collapsed after 8 items
7. **Performance & running costs**: bhp, 0–62, MPG, CO₂, insurance group, EV range/battery, each shown only when present. Never a placeholder value.
8. **Dealer card**: name, logo (Feature 06 §9), address, opening hours, link to the dealer's other stock. "Open now" and "distance from you" are **client islands** (§4).
9. **Similar cars** (§8)
10. **Report this listing** link (Feature 14)

### 3. States and HTTP status (owned here; Feature 13 adds robots and sitemap rules on top)
| Listing state | HTTP | Content | Robots |
|---|---|---|---|
| active, `clear` | 200 | full page | index (unless demo) |
| reserved, `clear` | 200 | "Reserved" banner; contact still allowed ("ask to be told if it becomes available") | index (unless demo) |
| sold ≤ 30 days ago | 200 | "This car has been sold" banner, gallery limited to the cover image, contact disabled, similar cars first | index |
| sold > 30 days ago, or archived after having been listed (`listed_at` set) | **410** | branded Gone page (Feature 03 §4) with similar cars | — |
| draft, or archived without ever being listed | 404 | not-found page with a link back to search | — |
| moderation `held` or `hidden` | 404 | not-found page (the listing may come back) | noindex |
| moderation `removed` | 410 | Gone page, no listing content | — |
| `is_demo` (any visible state) | as above | "Example listing" badge and tooltip; contact routes to a demo notice | **noindex** always |

This table resolves an earlier disagreement (archived: 404 here, 410 in Feature 13).
A once-listed page that search engines may have indexed gets 410. A page that was
never public gets 404.

### 4. Rendering and caching
- Server components fetch through `apiPublic` (no cookies, Feature 03 §6) over the internal URL with a 3 s timeout (Feature 01 §3). **The HTML contains no per-user data.** The save heart, "Price dropped since you saved", "Open now" (computed in Europe/London in the browser, so it can't be frozen in a cached page) and "distance from you" (from the visitor's last search postcode in local storage) are client islands.
- Response headers:

  | Response | `Cache-Control` |
  |---|---|
  | 200 | `public, s-maxage=60, stale-while-revalidate=300` |
  | 410 | `public, max-age=3600` (deliberate and stable) |
  | 404, 5xx | `no-store` (Feature 03 §4) |

- **API unavailable or timed out:** a branded 503 page with retry and `Retry-After`, `no-store`. A transient failure is never cached, and never shown as a 404 (that would tell crawlers the car is gone).
- `GET /api/v1/listings/{id}` (public) returns the listing, `ready` images, a dealer summary and the indicator, in **≤ 4 queries**, with p95 < 150 ms (Feature 13 budget). Rate limit: 300 requests/min per IP (Feature 04 §5; listed in Feature 14 §6).

### 5. CDN purge on listing changes
- A subscriber to Feature 05 §4's `ListingStatusChanged`, `ListingVisibilityChanged`, `ListingPriceChanged` and `ListingUpdated` events `dispatch()`es `purge_listing_urls(listing_id)` **after commit**. A rolled-back change purges nothing.
- It purges the canonical detail URL and `/api/v1/listings/{id}` through Cloudflare's purge-by-URL API (Feature 01 §9 client, shared with Feature 06 §7; purge rate limits per plan: to verify). Purges for the same listing within 10 s are coalesced.
- Failures retry 3 times with backoff, then log and increment `cdn_purge_failures_total`. The 60 s TTL is the backstop, so the page is at most about a minute stale.
- Result: a sale, takedown or price change is visible to buyers within seconds, not after the cache expires.

### 6. Contact actions and phone reveal
- The dealer's phone number is **not in the HTML**. "Call" calls `POST /listings/{id}/phone-reveal`, which returns the number (then opens `tel:`) and increments `ListingStats.call_clicks` (Feature 05 §6; a counter, not a lead, per Feature 10 §8), deduplicated per visitor per listing per day
- Rate limit: 20 reveals per hour per IP (Feature 04 §5). Demo listings return the demo notice instead.
- "Contact dealer" opens Feature 10's form. It's disabled for sold listings.

### 7. View counting
- `POST /listings/{id}/view` is sent with `navigator.sendBeacon` once the page has been visible for 2 s (not for prerenders or background tabs). It's never counted in the SSR handler, which also serves crawlers and CDN revalidations.
- **Dedupe:** key = `HMAC(daily_salt, client_ip | user_agent | listing_id)` in the cache Redis with a 24 h TTL. `daily_salt` is random, rotates at midnight UK time and is kept for 48 h, so the same visitor's hashes can't be linked across days. No raw IP or UA is stored. *(Retention of dedupe keys moved here from Feature 15.)*
- **Bot filtering:** user agents matching a maintained bot pattern list are not counted. Where Cloudflare provides a bot signal on the current plan (to verify), low scores are not counted either.
- Writes go through `stats.increment(listing_id, "views")` (Feature 05 §6), **never** to `Listing`, so the optimistic lock stays clean. Rate limit: 60 per minute per IP.

### 8. Similar cars
- `SearchBackend.similar(listing_id, 6)` (Feature 07 §4): same model, year ± 2, nearest price, publicly visible, excluding this listing. Demo listings are excluded when the main listing is real.
- If that finds fewer than 3, it falls back to the same make and body type
- The result (ids) is cached for 10 minutes per listing in the cache Redis and rendered server-side as `ListingCard`s

### 9. Dealer preview
- `/dealer/listings/{id}/preview` renders the same page component from the draft or current data, with a "Preview — not visible to buyers" banner. It is dealer-scoped (`get_dealer_owned_or_404`, Feature 04 §9), `private, no-store` and `noindex`.

### 10. Accessibility and performance
- Gallery: swipe, keyboard arrows, focus-trapped full-screen viewer, image counter announced, every image with alt text
- LCP < 2.5 s, CLS < 0.1, first-load JS ≤ 150 KB gzipped (Feature 13 budgets). The pinch-zoom viewer is loaded on demand, not in the initial bundle.

### 11. Observability
- Metrics: detail SSR latency, API latency, `cdn_purge_failures_total`, view beacons accepted/deduplicated/bot-filtered

---

## Key Decisions

**Views are counted client-side, not in the SSR handler.** The SSR handler also
serves crawlers and CDN revalidations. Counting there would inflate the stats dealers
see. Bots that run JS are partially filtered by the daily dedupe plus the bot list.

**Purge on change instead of short TTLs.** Rejected: dropping `s-maxage` to a few
seconds. That pushes most traffic back to the shared VM, and still leaves a taken-down
listing visible for that window. Event-driven purge plus a 60 s TTL gives a high hit
rate *and* near-instant takedowns.

**One status table covering moderation.** Rejected: letting moderation states fall
through to whatever the lifecycle state says. A `hidden` listing that was `active`
would otherwise still render with 200.

**410 only for pages that were once public.** Search engines drop a 410 quickly, which
is right for a page they may have indexed. A draft URL that never went public is
simply 404.

**Per-user details are client islands.** "Open now" and "distance from you" look
harmless, but in cached HTML they'd be wrong for most visitors (stale time, someone
else's postcode). The save heart would be a privacy leak.

**The phone number is revealed on tap.** It stops trivial number harvesting by
scrapers and gives dealers a "call clicked" lead signal (Feature 10) at no extra cost.

**Description is plain text only.** Dealer-supplied HTML is an XSS vector and makes
page styling inconsistent.

## Acceptance Criteria

**Rendering**
- With JS disabled, the title, price, key facts, description and first image are all present in the HTML. The dealer's phone number and the VRM are not.
- The page HTML is identical with and without a session cookie (apart from the CSP nonce)
- A description containing `<script>alert(1)</script>` renders as visible text, and no script runs

**URL & status**
- A table-driven test over status × moderation × `listed_at` × sold age asserts the HTTP code, robots meta and `Cache-Control` from §3–§4
- A wrong slug 301s to the canonical URL. A malformed UUID returns 404.
- With the API stubbed as down, the page returns 503 with `no-store` and a retry action, never 404 or 200

**Caching & purge**
- Selling, unpublishing, taking down or repricing a listing dispatches a purge of exactly the detail URL and its API URL after commit. A rolled-back change dispatches nothing.
- A failing purge is retried 3 times, then increments `cdn_purge_failures_total` with no user-facing error
- After a takedown, the next request through a test proxy honouring purges gets the 410

**Contact & phone**
- Phone reveal returns the number and increments `call_clicks` once per visitor per listing per day. The 21st reveal in an hour from one IP returns 429.
- On a sold listing the contact button is disabled. On a demo listing, contact and call show the demo notice.

**Views**
- 10 reloads by one visitor in a day count as 1 view, and the listing's `updated_at` is unchanged
- A request with a known bot user agent is not counted, and a beacon is not sent before the page has been visible for 2 s
- The same visitor produces different dedupe keys on consecutive days, and no raw IP is stored

**Similar cars, dealer card & preview**
- Similar cars never include the current listing, sold listings, or demo listings when the main listing is real. With fewer than 3 model matches, make-and-body fallbacks fill the section.
- "Open now" is correct either side of a clock change (unit test in Europe/London)
- A dealer preview of a draft renders with the banner, `private, no-store` and `noindex`. Another dealer gets 404.

**Performance & accessibility**
- LCP under 2.5 s and CLS under 0.1 on a throttled mid-range mobile profile (Lighthouse). First-load JS ≤ 150 KB gzipped.
- `GET /api/v1/listings/{id}` runs in ≤ 4 queries with p95 < 150 ms on the 50k perf profile
- The gallery works with swipe, keyboard and screen reader (images have alt text generated from the title and position)

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: complete status × moderation → HTTP/robots/cache table, resolving the archived 404/410 conflict with Feature 13 (§3)
- P0: event-driven CDN purge after commit (§5)
- P0: error and unavailable responses never cached, and a dependency outage is never shown as 404 (§4)
- P0: phone number kept out of the HTML (§6)
- P0: no per-user data in cached HTML (§4)
- P1: URL canonicalisation and malformed-id handling (§1)
- P1: privacy-preserving daily-salted view dedupe with bot filtering (§7)
- P1: similar-cars fallback and cache (§8)
- P1: dealer preview (§9)
- P1: query and latency budget for the detail API (§4)
- P1: on-demand gallery viewer within the JS budget (§10)
- P1: phone-reveal rate limit (§6)

**Ownership moves:** the listing lifecycle → HTTP status table moves here from Feature
13 (Feature 13 keeps robots, canonicals and sitemaps). Retention of view-dedupe keys
moves here from Feature 15 (§7).

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| Finance/monthly-price display | Only once FCA permissions are resolved (Phase 2 item 9); never in the MVP |
| Vehicle history check panel | Phase 2 item 6 |
| Video / 360° spin | Dealers ask for it and the image budget allows it |
| Buffered view counting (batch flush) | Row-lock waits on `listing_stats`, see Feature 05 P2 |
| "Recently viewed" for signed-out users | Analytics show frequent back-and-forth between detail pages |
| Server-side A/B testing of page layout | Enough traffic for significance (> ~10k detail views/day) |

**Scale traps to avoid:** per-user SSR on the detail page; counting views in the
render path; very short TTLs as a substitute for purging.
