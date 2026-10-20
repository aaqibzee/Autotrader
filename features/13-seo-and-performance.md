# Feature 13 — SEO & Performance

**Status:** Not Started
**Priority:** Must-Have
**Milestone:** M5 Launch
**Effort:** 7h optimistic / 14h realistic / 22h pessimistic
*(raised from 5/10/16h after a scale review: same-origin streamed sitemaps with atomic
swap, safe JSON-LD serialisation, landing-page index hysteresis, crawler access
alongside bot protection, bounded RUM and a non-flaky performance gate. See "Scale
review" at the end.)*
**Depends on:** 03, 07, 08

## Description

Make the inventory discoverable through search engines, and keep the site fast.
Report §6: "millions of indexable listing pages is itself an infra/performance
consideration (crawl budget, sitemap generation, stale-listing handling) beyond
typical CRUD-app concerns." At MVP scale it's thousands, not millions, but getting
the **indexing rules** right from the start avoids a crawl-budget and duplicate-content
mess that is very hard to undo later.

---

## Scope

### 1. Indexable page types
| Page | URL | Indexed? |
|---|---|---|
| Listing detail | `/car-details/{id}/{slug}` | Per Feature 08 §3 (active/reserved, sold for 30 days; demo never) |
| Make landing | `/cars/{make}` | Yes, when indexable (§2) |
| Make + model landing | `/cars/{make}/{model}` | Yes, when indexable (§2) |
| Location landing | `/cars/in/{town}` (curated list of ~100 UK towns) | Yes, when indexable (§2) |
| Make + location | `/cars/{make}/in/{town}` | Yes, when indexable (§2) |
| Any other filter combination (`?price_max=…&fuel=…`) | `/cars?…` | **No**: `noindex, follow`, canonical per §3 |
| Dealer page | `/dealers/{slug}` | Yes, once approved, not demo, and with ≥ 1 publicly visible listing |
| Value my car (when its flag is on), static pages | | Yes |
| Account, dealer portal, admin, `/dev` | | No (`noindex` via Feature 03 §6 headers, and disallowed in robots.txt) |

### 2. Landing pages
- Each landing route maps to a `SearchFilters` (Feature 07 §3): make/model by slug, towns from a bundled `backend/data/geo/towns.csv` (name, slug, centroid, 25-mile radius). It renders Feature 07's results component, plus a server-rendered intro paragraph (count, price range, popular models; cached 1 h) and internal links (popular models for the make, nearby towns).
- **Indexability with hysteresis:** the nightly sitemap job (§6) recomputes each landing's count of **non-demo** visible listings into `LandingPage(path, filters, indexable, result_count, changed_at)`. A page becomes indexable at **≥ 20** and stops being indexable below **15**. Rejected: one threshold at 20, where a page hovering at 19–21 flips between index and noindex daily, which search engines treat as instability. Demo listings never count, so a region running on demo stock (Feature 02 §9) has no indexable landings.
- Never generate pages or links for make × model × town combinations with no inventory. Unknown slugs return 404.
- Landing HTML: `Cache-Control: public, s-maxage=300, stale-while-revalidate=600` (counts change slowly). It's user-agnostic per Feature 03 §6.

### 3. Canonicals and URL hygiene
- `/cars?…` filter URLs: `noindex, follow`, with the canonical pointing to the most specific **indexable** landing whose filters are a subset of the URL's (e.g. `?make=ford&fuel=diesel&price_max=8000` → `/cars/ford`), else `/cars`
- Page 2 and beyond of a landing: `noindex, follow`, self-canonical. Page 1 is the indexed one.
- UTM and other tracking parameters are stripped from canonicals. Parameter order doesn't matter (Feature 07 §3's canonical key).
- Host canonicalisation at Cloudflare: one host (apex → `www`, or the reverse, decided at domain setup), HTTPS only, 301. Paths lower-case with no trailing slash, 301 otherwise.

### 4. Listing lifecycle → HTTP status
Owned by Feature 08 §3 (status × moderation → HTTP code, robots and cache headers;
once-listed archived pages get 410, never-listed ones 404; demo listings `noindex`
always). This feature adds the sitemap and canonical rules on top.

### 5. Structured data and meta
- Listing: JSON-LD `Car` (schema.org) with `offers` (`Offer`: price, GBP, availability InStock / SoldOut), `mileageFromOdometer`, `vehicleModelDate`, `fuelType`, `brand`, `image`, and the seller as `AutoDealer`. Demo listings get no structured data.
- `BreadcrumbList` on listing and landing pages. `Organization` + `WebSite` (with `SearchAction`) on the home page.
- **Safe serialisation:** JSON-LD is produced by one helper, `jsonLd(obj)`, which escapes `<`, `>`, `&` and U+2028/2029 as `\u` sequences and is rendered with the CSP nonce (Feature 01 §11). Dealer-written fields (variant, description excerpts, dealer name) can therefore never close the `<script>` tag. Rejected: `JSON.stringify` into the template, which lets a variant of `</script><script>…` execute.
- Unique `<title>` / meta description templates per page type. Open Graph + Twitter cards use the cover image's `full` variant (Feature 06 §6), for good link previews in WhatsApp shares.

### 6. Sitemaps
- **Nightly at 02:30 Europe/London** (`default` queue, single beat): writes child sitemaps for listings (visible non-demo plus sold ≤ 30 days, with `lastmod` = `updated_at`), indexable landings and indexable dealers, each ≤ 50,000 URLs and ≤ 50 MB uncompressed, gzipped
- **Streamed:** rows are read with a server-side cursor in batches of 5,000 and written incrementally, so memory stays flat regardless of inventory size (within the 256 MB worker limit, Feature 01 §16)
- **Atomic publish:** child files are written under a new `sitemaps/{run_id}/` prefix, and `sitemap_index.xml` is replaced last. A crawler never sees an index pointing at half-written children. The previous run's files are deleted after 24 h.
- **Same origin:** served at `https://<site>/sitemaps/…` by the reverse proxy from the object-storage `images` bucket's `sitemaps/` prefix (Feature 06 §3), with `Cache-Control: public, max-age=3600`. Rejected: linking `img.<domain>` URLs from `robots.txt`, because a sitemap on a different host is only honoured with extra cross-host verification.
- Metrics: URLs per child type, run duration, `sitemap_last_success_timestamp` (Feature 15 alerts after 26 h)

### 7. robots.txt
- `Disallow: /api/`, `/account`, `/dealer`, `/admin`, `/dev`, and `/cars?*page=` beyond the first page is left to `noindex` (not disallowed, so crawlers can see the `noindex`)
- `Sitemap: https://<site>/sitemaps/sitemap_index.xml`
- Never disallows `/_next/` assets (crawlers need them to render)

### 8. Crawler access alongside bot protection
- Feature 14 §6's Cloudflare bot rules must not challenge **verified search-engine bots** (Cloudflare's verified-bot handling; behaviour on our plan: to verify). The app's per-IP limit (120 requests/min on search, Feature 07 §9) is far above a single crawler IP's normal rate. 429s to known crawler user agents are logged and counted (`crawler_rate_limited_total`), and a non-zero count is reviewed.
- Search Console is set up (property, sitemap submitted, coverage report watched) as a Feature 15 launch-checklist item

### 9. Performance budget (mobile, throttled, p75)
| Metric | Budget |
|---|---|
| LCP (detail, results, landings) | < 2.5 s |
| CLS | < 0.1 |
| INP | < 200 ms |
| JS shipped on the detail page | < 150 KB gzipped, to be re-checked against the framework floor Feature 03 slice 3.3 measures (the placeholder shell already loads ~160 KB; public shell budget = floor + 30 KB, Feature 03 §7 A1) |
| SSR origin TTFB p95 (cache miss) | < 600 ms |
| API p95: detail / search | < 150 ms / < 300 ms (Feature 08 §4, Feature 07 §7) |
| Edge cache hit ratio, detail + landing HTML | ≥ 60% |

Caching rules are owned where they're decided: public-HTML personalisation (Feature 03
§6), detail page headers and purge (Feature 08 §4–§5), search API edge rule (Feature 07
§7), immutable images (Feature 06 §6). This feature measures them against the budget.

### 10. Performance gates in CI
- **Deterministic gates, blocking on every PR:** JS bundle sizes per route from the `next build` output
- **Lighthouse CI** against the seeded stack (home, results, detail; mobile profile; median of 3 runs): **advisory on PRs** (posted as a check), **blocking in the nightly job**. Rejected: blocking PRs on single Lighthouse timing runs, which are noisy enough to fail random builds and get ignored.

### 11. Real-user monitoring
- The `web-vitals` library sends `{page_type, metric, value, rating, connection_type}` to `POST /api/v1/rum` with `sendBeacon`, sampled at 10%. **No cookies, no user or session id, no URL beyond the page type.** Body ≤ 2 KB, schema-validated, rate-limited 30/min per IP (Feature 04 §5).
- Stored as `WebVitalSample` rows (kept 14 days), and aggregated to p75 per page type per hour for the admin ops dashboard (Feature 14). Data appears within 5 minutes.
- **Consent:** whether identifier-free RUM needs PECR consent is **to verify** (legal review in Feature 15). Until confirmed, the beacon is sent only after analytics consent, behind the `rum_without_consent` flag (default off).

### 12. Observability
- Metrics: sitemap job (above), `crawler_rate_limited_total`, 404/410 response rates by page type, RUM ingestion count
- Search Console coverage and Core Web Vitals reports are reviewed weekly after launch (Feature 15 runbook)

---

## Key Decisions

**Index only curated landing pages, never arbitrary filter combinations.** Faceted
navigation can generate effectively infinite URLs. Letting crawlers into them wastes
crawl budget on near-duplicate pages and dilutes ranking. Landing pages are the
deliberate SEO surface. Everything else is `noindex, follow` with canonicals.

**410 for long-gone listings, not 404 or a redirect** (table owned by Feature 08 §3).
410 tells crawlers to drop the URL quickly. Redirecting every sold car to search is
treated as a soft 404 and confuses users.

**Demo inventory is invisible to search engines.** It exists to make the product feel
alive to humans during cold start (Feature 02). Indexing it would be misleading and
risks a quality penalty. That includes demo dealers' pages and landing counts.

**Sitemaps on the site's own origin, published atomically.** Small details that
decide whether search engines trust the sitemap at all. A half-written index or a
cross-host file is worse than none.

**Hysteresis on landing indexability.** Inventory moves daily in a small regional
beta. Without a gap between the "index" and "noindex" thresholds, pages would flap.

**Deterministic gates block; noisy gates inform.** Bundle size can't flake, so it
blocks. Lighthouse timing can, so it blocks only where repeated runs make it
reliable.

## Acceptance Criteria

**Indexing & canonicals**
- Every page type renders the correct robots meta, canonical and HTTP status (table-driven test, reusing Feature 08 §3's table for listings)
- A filter URL like `/cars?make=ford&fuel=diesel&price_max=8000` is `noindex, follow` with a canonical to `/cars/ford`
- Page 2 of `/cars/ford` is `noindex, follow` and self-canonical. A canonical never contains UTM parameters.
- The non-canonical host and a trailing-slash path 301 to the canonical URL
- A landing becomes indexable at 20 non-demo results, stays indexable at 17, and becomes `noindex` at 14. Demo listings don't count toward the threshold.
- A demo dealer's page and a dealer with no visible listings are `noindex`
- An unknown make or town slug returns 404

**Structured data**
- Listing JSON-LD validates in the Rich Results Test, and availability switches to SoldOut when sold
- A listing whose variant contains `</script><script>alert(1)</script>` renders valid JSON-LD and runs no script
- Demo listings have no structured data

**Sitemaps & robots**
- A sitemap index is generated nightly. It contains no demo, draft, archived, held, hidden or removed listings. No child file exceeds 50k URLs.
- Generating sitemaps for the 50k perf profile stays under the worker's 256 MB limit
- A failure halfway through a run leaves the previous `sitemap_index.xml` and its children intact
- Sitemaps are served from the site's own origin at `/sitemaps/`, and `robots.txt` references the index and disallows `/api/`, `/account`, `/dealer`, `/admin` and `/dev`
- `sitemap_last_success_timestamp` updates after each successful run

**Performance & RUM**
- Bundle-size budgets are enforced on every PR. Lighthouse CI budgets pass for home, results and detail pages on mobile in the nightly job.
- A single IP crawling 100 pages per minute is never rate-limited
- RUM beacons carry no cookie and no identifier, oversized bodies are rejected, and the 31st beacon in a minute from one IP returns 429
- RUM beacon data shows up in the admin dashboard within 5 minutes. With `rum_without_consent` off, no beacon is sent before analytics consent.

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: safe JSON-LD serialisation (§5)
- P0: same-origin, streamed, atomically published sitemaps (§6)
- P0: crawler access alongside Feature 14's bot rules (§8)
- P1: landing indexability with hysteresis and demo-free counts (§2)
- P1: canonical rules for pagination, tracking parameters, host and trailing slash (§3)
- P1: demo dealer pages `noindex` (§1)
- P1: TTFB and cache-hit-ratio budgets (§9)
- P1: deterministic vs advisory performance gates (§10)
- P1: bounded, identifier-free RUM with a consent gate pending legal review (§11)
- P1: sitemap and crawler metrics (§6, §12)
- P1: robots rules that keep `noindex` visible (§7)

**Ownership moves:** the listing lifecycle → HTTP status table moved to Feature 08 §3
(cited in §4). Caching headers are owned by Features 03, 06, 07 and 08; this feature
owns the budget they're measured against (§9).

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| Intra-day / delta sitemaps | Listings > 50k, or new listings taking more than 2 days to be indexed |
| Image sitemaps | Image search traffic becomes a measurable channel |
| Editorial content (reviews, buying guides) | Organic traffic plateaus on landing pages (report §3 lists editorial as an SEO driver) |
| More landing types (body type × town, fuel × town) | Search Console shows demand for those queries, and inventory supports ≥ 20 results |
| IndexNow / search-engine ping APIs | Indexing lag on new listings becomes a dealer complaint |
| Cookieless analytics product | Consent rate is low enough that analytics are unusable |

**Scale traps to avoid:** pre-rendering every filter permutation as a static page;
indexing faceted URLs; a separate SEO rendering service.
