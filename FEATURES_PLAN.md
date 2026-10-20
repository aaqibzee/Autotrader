# Autotrader Clone — MVP Features Plan

Source: [`Documents/AutoTrader_UK_Technical_Due_Diligence.pdf`](Documents/AutoTrader_UK_Technical_Due_Diligence.pdf)
(technical due diligence of www.autotrader.co.uk, 29 Sep 2026). Section references
below (§2, §4, …) point into that report.

Status legend: `Not Started` | `Planning` | `In Progress` | `Done`

Every feature is built in slices following [`features/IMPLEMENTATION_PLAYBOOK.md`](features/IMPLEMENTATION_PLAYBOOK.md).
Each feature has its own design doc in `features/NN-*.md` holding the scope, data
model, endpoints, UI, key decisions and acceptance criteria. Build them in the
order listed. Each one assumes the features before it are done.

---

## 1. What this MVP is (and isn't)

**Goal:** a launchable, **dealer-led UK used-car marketplace beta**. Dealers list
stock. Consumers search it, view listings, save cars and searches, get email alerts,
value their own car, and contact the dealer. This is the "realistic MVP clone of the
core consumer-facing marketplace experience" scoped in report §4, not a copy of the
full platform. The report is explicit that full parity (600+ systems, a proprietary
valuation model, FCA-regulated finance) cannot be estimated in build hours.

**The two halves of the marketplace, and what each gets in the MVP:**

| Side | Who | MVP capability |
|---|---|---|
| **Supply** | Car dealers (B2B) | Dealer account with team members, manual stock CRUD with plate-lookup prefill, photo upload, lead inbox |
| **Demand** | Car buyers (B2C) | Search/filter by location, listing pages, saved cars, saved searches with email alerts, valuation of own car, contact dealer |
| **Platform** | Us | Admin approval of dealers, report-a-listing moderation, abuse/scrape protection, SEO surface |

**Explicitly out of scope for the MVP** (report §4 "Out of scope" and §6 risks;
see the Phase 2 backlog at the bottom):
- Automated dealer feed/DMS ingestion. Stock is entered manually, with optional CSV import in Phase 2.
- A proprietary ML valuation engine. Valuations come from a **third-party API behind an adapter**.
- Finance quotes or credit-broker introductions. These bring in **FCA consumer-credit regulation** (§6).
- Dealer subscription billing. Dealers use the platform free during the beta, which avoids PCI/Stripe scope (§6).
- Native iOS/Android apps. A mobile-first responsive web app comes first (§5 notes traffic is heavily mobile).
- Private (non-dealer) sellers, vehicle history checks, dealer reviews, editorial content.

**Default answers to the report's four clarifying questions (§7).** Change these here
first if any of them is wrong, because they shape the whole plan:
1. *Prototype or competitor?* A **launchable regional beta** with real dealers on seeded and demo data. Not a full-scale competitor.
2. *Dealer portal in scope?* **Yes, basic version.** Without supply there is no product (the §6 "cold-start" risk).
3. *Native apps?* **No.** Responsive web only.
4. *Billing or finance in scope?* **No** for both, in the MVP.

---

## 2. Tech Stack (reference for all features)

The real platform (report §2) is Java/Kotlin Spring Boot microservices on Kafka, run
on GKE behind Cloudflare. That architecture serves 600+ systems and around 60k deploys
a year. **The MVP deliberately does not copy it.** It keeps the platform's
*architectural properties that matter at MVP scale*, but runs as a modular monolith on
the stack already proven across Yaqlo, Duely and Suretly:

| Layer | Technology | Why (report reference) |
|---|---|---|
| Consumer + dealer web | **Next.js (React 19 + TypeScript, App Router)** + Tailwind CSS | §2: listing pages depend heavily on SEO, so they need **SSR**. A Vite SPA (the Yaqlo/Suretly frontend) would not get indexed well. Interactive tools (filters, valuation, dealer portal) render client-side. |
| Backend API | **FastAPI (Python 3.11+)**, modular monolith | One deployable with one module per domain (`dealers`, `listings`, `search`, `leads`, `alerts`, `valuations`, `admin`) replaces the microservices. Modules talk through service functions, not HTTP. |
| Async work | **Celery + Redis** | Stands in for Kafka at MVP scale: image processing, alert digests, sitemap generation, valuation lookups. |
| Database | **PostgreSQL** + SQLAlchemy 2.0 + Alembic | §2 notes the real platform uses SQL + MongoDB for highly variable vehicle specs. Here, **JSONB columns** hold the long-tail spec data next to typed, indexed columns for filterable attributes. |
| Search | **PostgreSQL** (indexed filters, facet counts, bounding-box + haversine distance) | §3 says the real platform uses Elasticsearch/Solr-class search. That is deferred until listings reach the hundreds of thousands. Search sits behind a `SearchBackend` interface so it can be swapped later. |
| Object storage | **S3-compatible** (SeaweedFS locally, R2/S3 in production) | Holds the listing photos (§3 image pipeline). |
| CDN / DNS / WAF | **Cloudflare** | Same edge layer the real platform uses (§2), and already in use for the other apps. |
| Email | **Resend** | Saved-search alerts, lead notifications, auth emails. |
| Auth | **FastAPI-Users** (cookie/session) | Two account types share one user table; see Feature 04 and Feature 09. |
| External data | **DVLA Vehicle Enquiry Service** + **DVSA MOT History API** (plate lookup), **postcodes.io** (UK postcode → lat/long), **third-party valuation API** (provider TBD, Feature 12) | Integrations: §4 flags these as the AI-velocity bottleneck. |

**Hosting note:** the shared Oracle VM already runs Yaqlo, Duely, Scout and Suretly on
2 OCPU / 12 GB. The MVP can launch there, but one image-processing worker plus an SSR
Next.js server is the heaviest workload on that box so far. Do the free-tier resize
(4 OCPU / 24 GB) before launch.

---

## 3. Feature list (build order)

| # | Feature | Priority | Milestone | Realistic effort | Status |
|---|---|---|---|---|---|
| 01 | [Project Foundation](features/01-project-foundation.md) | Must-Have | M1 Foundation | 16h | Done |
| 02 | [Vehicle Taxonomy & Seed Inventory](features/02-vehicle-taxonomy-and-seed-data.md) | Must-Have | M1 Foundation | 13h | Implemented, nightly scale run pending ([slices](features/02-vehicle-taxonomy-and-seed-data.slices.md)) |
| 03 | [Design System & App Shell](features/03-design-system-and-app-shell.md) | Must-Have | M1 Foundation | 13h | Not Started |
| 04 | [Auth Core & Dealer Accounts](features/04-auth-core-and-dealer-accounts.md) | Must-Have | M2 Supply | 16h | Not Started |
| 05 | [Dealer Stock Management](features/05-dealer-stock-management.md) | Must-Have | M2 Supply | 19h | Not Started |
| 06 | [Listing Image Pipeline](features/06-listing-image-pipeline.md) | Must-Have | M2 Supply | 12h | Not Started |
| 07 | [Search & Browse](features/07-search-and-browse.md) | Must-Have | M3 Discovery | 26h | Not Started |
| 08 | [Listing Detail Page](features/08-listing-detail-page.md) | Must-Have | M3 Discovery | 11h | Not Started |
| 09 | [Consumer Accounts & Saved Cars](features/09-consumer-accounts-and-saved-cars.md) | Must-Have | M4 Engagement | 12h | Not Started |
| 10 | [Contact Seller & Dealer Lead Inbox](features/10-contact-seller-and-leads.md) | Must-Have | M4 Engagement | 15h | Not Started |
| 11 | [Saved Searches & Email Alerts](features/11-saved-searches-and-alerts.md) | Must-Have | M4 Engagement | 17h | Not Started |
| 12 | [Valuations & Price Indicator](features/12-valuations-and-price-indicator.md) | Must-Have | M4 Engagement | 20h | Not Started |
| 13 | [SEO & Performance](features/13-seo-and-performance.md) | Must-Have | M5 Launch | 14h | Not Started |
| 14 | [Trust, Safety & Admin Console](features/14-trust-safety-and-admin.md) | Must-Have | M5 Launch | 18h | Not Started |
| 15 | [Launch Readiness](features/15-launch-readiness.md) | Must-Have | M5 Launch | 18h | Not Started |
| | **Total build** | | | **~240h realistic** (range ~118–372h) | |

**Why this order:**
- **Supply before demand.** Search (07) is meaningless without stock. Features 04–06
  let a real dealer, or the seed script, create listings before any consumer page
  exists.
- **Seed data early (02).** Every later feature is developed and demoed against
  ~5,000 realistic listings. Developing against an empty database hides the
  performance and filter-combination problems that §4 says are "trivial to get
  working, hard to get good."
- **Consumer accounts (09) come after discovery (07–08).** Browsing, viewing and
  enquiring all work without an account. Accounts only unlock saved cars and saved
  searches, so they don't block the core loop.
- **Foundation is deliberately heavier than the report's 6h scaffolding.** After a
  scale review, Feature 01 now owns the cross-cutting conventions (network topology,
  real client IP, commit-safe job dispatch, shared HTTP client, error format, Redis
  roles, observability, test harnesses). Each one would otherwise be rebuilt, slightly
  differently, inside the features that need it. This adds +10h up front.
- **Integrations are spread out, not batched.** The plate lookup lands in 05,
  postcodes in 04 (dealer address, with an offline fallback) and are extended in 07
  (search), and the valuation API in 12. Resend also lands in 04, as the shared email
  service that 09–11 and 14 reuse. §4 flags third-party integrations
  as the slowest part of AI-assisted development, so each one gets its own buffer.
- **Every feature was scale-reviewed (02–15 after 01), raising the build from ~180h
  to ~240h.** Each doc now ends with a "Scale review" section. The increase is mostly
  decisions that would be expensive to retrofit once later features depend on them:
  one listing-visibility predicate and lock-safe system writes (02), the shared email
  service, rate limiter and geocoder (04), listing events and the moderation hook
  (05), the `SearchParams`/`SearchBackend` contract (07), CDN purge (08), the
  personal-data registry (09), per-recipient lead delivery (10), race-free alert
  matching (11), a valuation cost budget (12), and the alert/backup/runbook gate (15).

---

## 4. Milestones

| Milestone | Features | Exit criteria (demoable outcome) |
|---|---|---|
| **M1 Foundation** | 01–03 | `docker compose up`, then the web app renders the app shell against an API holding 5,000 seeded listings |
| **M2 Supply** | 04–06 | A dealer can register, be approved, invite a colleague, look up a plate, create a listing with photos, publish it, and mark it sold |
| **M3 Discovery** | 07–08 | A signed-out visitor on a phone finds a car by postcode + make/model/price filters and opens its SSR detail page |
| **M4 Engagement** | 09–12 | A consumer saves a car and a search, gets an alert email for a new match, values their own car by plate, and sends an enquiry the dealer sees in their inbox |
| **M5 Launch** | 13–15 | Sitemaps and structured data are live, the admin console can approve dealers and take down reported listings, legal pages and cookie consent are in place, and the QA pass is complete |

---

## 5. QA plan (report §5)

QA runs **per feature** (each feature doc's acceptance criteria become its tests) plus
one consolidated pass in Feature 15:

| Area | Estimate | Owning features |
|---|---|---|
| Manual test cases | ~60–90 cases | All, compiled in 15 |
| Functional/regression pass | 12–20h | 15 |
| Cross-browser & responsive/mobile | 8–14h | 03, 15 |
| Integration testing (DVLA/MOT, postcodes, valuation, Resend) | 10–18h | 05, 07, 11, 12 |
| Auth & access control: **dealer A must never see or edit dealer B's stock or leads** | 8–14h | 04, 05, 10 |
| Security basics (OWASP pass) | 6–10h | 14, 15 |
| Load/performance (search under seeded volume) | 8–16h | 07, 13 |
| **Total** | **~50–90h** | |

**Overall MVP budget: ~240h build + ~50–90h QA ≈ 290–330h, about 7–8 weeks for
one full-time, AI-assisted developer** (the same assumptions as report §7).

---

## 6. Risks carried into the MVP (report §6) and how this plan handles each

| Risk | Mitigation in this plan |
|---|---|
| Two-sided cold start | A dealer-led launch in **one region**. Seeded demo inventory is clearly marked and switched off per region as real dealers arrive (02). Dealer onboarding is free during the beta. |
| Valuation quality depends on licensed data | A valuation adapter with a stub provider (12). The price indicator falls back to on-platform comparables with a minimum sample size and shows **"No rating"** rather than a fabricated one. |
| FCA regulation | No finance features in the MVP. Nothing on the site invites credit or introduces a broker (15 checks the copy). |
| PCI scope | No payments in the MVP. |
| Scraping / fraud | Page-depth caps, rate limits, Cloudflare bot protection, dealer approval and report-a-listing (14). |
| SEO at scale | SSR, canonical rules for filter permutations, nightly sitemaps and handling of sold or stale listings (13). |
| Messy dealer feeds | Out of scope for the MVP. Manual entry with a plate-lookup prefill keeps data clean. CSV import is the first Phase 2 item. |

---

## 7. Phase 2 backlog (post-MVP, not yet designed)

Rough order, reflecting what a growing dealer base will ask for first:
1. **Dealer CSV stock import**, then feed/DMS integrations (the §3 ingestion pipeline)
2. **Dealer subscriptions & billing** (Stripe, plan-based listing limits; reuse the Yaqlo plan-gating pattern)
3. **Dealer analytics**: views, saves and leads per listing, with pricing suggestions (§3 "Retailer" platform)
4. **Part-exchange flow**: value your car, then browse with that budget (§3)
5. **Dealer reviews & ratings**
6. **Vehicle history check** (HPI-style, via a provider)
7. **Search engine migration** to OpenSearch/Elasticsearch when Postgres facet queries exceed the latency budget
8. **Private seller listings**, with payments and much more fraud exposure
9. **Finance calculator / broker introductions**, only once FCA permissions are resolved
10. **Native apps**
