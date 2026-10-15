# Feature 15 — Launch Readiness

**Status:** Not Started
**Priority:** Must-Have (gate before any real dealer or buyer is invited)
**Milestone:** M5 Launch
**Effort:** 9h optimistic / 18h realistic / 28h pessimistic
*(raised from 8/16/24h after a scale review: a concrete alert-rule table covering every
failure signal features 01–14 emit, encrypted off-provider backups with stated RPO/RTO,
per-dependency runbooks, ICO/ROPA compliance items and a go/no-go checklist. Retention
jobs and branded error pages moved out to their owning features, which offsets part of
the increase. See "Scale review" at the end.)*
**Depends on:** 01–14

## Description

Everything between "features work" and "safe to put in front of the public":
legal pages, cookie consent, a check that every state is designed, an accessibility
and responsive pass, production alerting, backups and recovery, runbooks, and the
consolidated QA pass. Report §4 warns that edge-case states are "easy to
underestimate; large surface area (search, alerts, dealer CRUD all need these)."
This feature mostly **verifies and operates** what features 01–14 built. It defines
no new product behaviour.

---

## Scope

### 1. Legal and compliance (UK)
- **Privacy notice** (UK GDPR): what we collect (accounts, leads, saved searches, saved valuations, reports, analytics), lawful bases, the retention periods from §2, processors (Resend, Cloudflare, the error-tracking/telemetry backend, the valuation provider, Google for sign-in, the object-storage provider, the VM host), international transfers where a processor is outside the UK (to verify per processor), rights and how to exercise them (Feature 09 §6 export and delete). It states what erasure keeps: anonymised enquiries (Feature 10 §9), the email suppression entry (Feature 04 §6), and backups until they expire (§7).
- **Record of processing activities** (UK GDPR Art. 30) and a short DPIA screening, kept in `Documents/privacy/`
- **ICO data protection fee:** register, or document why it doesn't apply (tier and exemptions: to verify)
- **Cookie policy and consent banner** (PECR): strictly necessary cookies (session, CSRF) need no consent. Analytics loads **only after opt-in**, with equal-prominence Accept / Reject and a footer link to change the choice later. The choice is stored with a **policy version**; changing the policy re-prompts. Whether identifier-free RUM needs consent is decided here by legal review (Feature 13 §11, flag `rum_without_consent`).
- **Terms of use** (buyers) and **dealer terms**: listing accuracy obligations, our right to hold, hide or remove listings (Feature 14 §4), beta/no-fee terms, consumer-law obligations stay with the dealer, and the dealer acts as controller of the lead data they receive (Feature 10 §9)
- **FCA copy check:** no page invites or quotes credit, shows APRs or monthly finance prices, or introduces a broker (report §6). An automated scan of rendered public pages and email templates for the finance word list shared with Feature 14 §4's hold rules runs in CI. Dealer descriptions are covered by those hold rules.
- Google OAuth consent-screen verification is complete (Feature 09 §2). `/.well-known/security.txt` is live (Feature 14 §8).

### 2. Retention: verify, don't build
Each job is built and tested (through the real write path) by its owning feature.
Here, each one is confirmed running in production and listed in the privacy notice:

| Data | Retention | Owner |
|---|---|---|
| View-dedupe keys | 24 h | Feature 08 §7 |
| RUM samples | 14 days | Feature 13 §11 |
| `EmailMessage` log | 90 days | Feature 04 §6 |
| Alert delivery logs | 90 days | Feature 11 §7 |
| Provider valuation cache | 90 days | Feature 12 §2 |
| `AuthEvent` | 12 months | Feature 04 §10 |
| Listing reports | 12 months | Feature 14 §5 |
| Leads (anonymised) | 24 months | Feature 10 §9 |
| `AdminAction` | 24 months | Feature 14 §2 |
| `ListingAuditEvent` | listing life + 24 months | Feature 05 §7 |
| Database backups | 14 days | §7 |

### 3. Edge, error and empty states audit
Walk every page and list against a checklist: loading skeleton, empty state with
next action, error state with retry, offline/slow network, rate-limited, dependency
unavailable, permission denied, not found, and very long content (titles,
descriptions, 20 photos, 7-digit prices). The global error boundary and branded 404,
410 and 500 pages are built in Feature 03 §4; here, confirm every route uses them and
that error responses are never cached.

### 4. Responsive and accessibility pass
- Test matrix: iOS Safari (latest 2), Android Chrome, desktop Chrome, Safari, Firefox, Edge, at widths of 320, 375, 414, 768, 1024 and 1440
- WCAG 2.2 AA spot-audit beyond Feature 03 §9's automated checks: keyboard paths through search, the detail page, contact and dealer listing creation; screen-reader labels on filters and the gallery; contrast

### 5. Production alert rules
Error tracking, tracing and metrics are set up in Feature 01 §12. Here, the rules that
page someone are configured, each test-fired once in staging:

| Signal | Threshold | Source |
|---|---|---|
| New error-tracking issue / error-rate spike | new issue; 5xx rate > 2% for 5 min | Feature 01 §12 |
| `/health/ready` failing (uptime check) | 2 consecutive failures | §6 |
| Queue depth | `notifications` > 100 for 10 min; `images` > 200 for 10 min | Feature 01 §7, Feature 06 §4 |
| Circuit breaker open | > 10 min for any integration | Feature 01 §9 |
| Lead delivery stuck | any `LeadDelivery` pending > 15 min | Feature 10 §10 |
| Alert run missing | Daily not succeeded in 26 h; Instant in 3 h | Feature 11 §9 |
| Sitemap run missing | no success in 26 h | Feature 13 §6 |
| Email reputation | bounce rate > 2% or complaints > 0.1% (7-day) | Feature 04 §6, Feature 11 §6 |
| Valuation budget | ≥ 80% of monthly calls used | Feature 12 §3 |
| Rating distribution off | > 60% of real listings in one extreme band | Feature 12 §9 |
| Held listing waiting | oldest held > 24 h | Feature 14 §4 |
| Rate limiter failing open | `rate_limiter_unavailable_total` increasing | Feature 04 §5 |
| CDN purge failures | > 10 in an hour | Feature 08 §5 |
| Backup failure / disk | nightly backup missing; disk > 80% | §7 |

Alerts go to email and phone. The runbook (§8) for each signal is linked from the
alert text.

### 6. Uptime checks
- External uptime checker (vendor chosen during this feature; free-tier limits to verify) on `/`, `/cars` and `/api/v1/health/ready`, every minute, from at least 2 locations
- The proxy's maintenance page (Feature 01 §16) is what users see during deploys and outages

### 7. Backups and recovery
- **Targets:** RPO 24 h, RTO 4 h for the database
- Nightly `pg_dump` (custom format), **encrypted** (age, key held outside the VM in the password manager), uploaded to object storage at **a different provider from the VM**, so losing the VM's provider doesn't lose both. 14 daily copies kept.
- **Restore drill** before launch, then quarterly: restore into a fresh database, boot the app against it, run the smoke checks, record the time in the runbook. A backup that has never been restored is not a backup.
- `images` bucket versioning on, with noncurrent versions expired after 30 days (protects against accidental deletes). The `uploads` bucket isn't versioned (raw uploads are deliberately short-lived, Feature 06 §3).
- Redis is not backed up. The broker's work is recoverable through the outbox sweepers (Feature 01 §7, Feature 04 §6, Feature 10 §4), and the cache is disposable.
- The production `.env` is stored in the password manager, and the rotation procedure is in Feature 01 §2's runbook.

### 8. Runbooks (`ops/runbooks/`)
- **Deploy and rollback** (Feature 01 §15, same shape as the other apps' oracle-deploy flow). The deploy script **fails unless `alembic current` equals the heads** after migrating (Yaqlo lesson: unapplied migrations caused a production 500).
- **Per-dependency outage:** DVLA/MOT, postcodes.io, valuation provider, Resend, Cloudflare purge, Redis (broker and cache), Postgres. Each lists what users see (from the owning feature's unavailable path) and what the operator does.
- **Operational procedures:** "dealer says they're missing leads" (Feature 10 §4 delivery rows), erasure and access requests (Feature 09 §6), switching demo stock off for a region (Feature 02 §9), suspending a dealer (Feature 14 §3), restore (§7), secrets rotation
- Weekly post-launch review: Search Console coverage and Core Web Vitals (Feature 13 §12), slow-query report (Feature 01 §12), zero-result searches (Feature 07 §12)

### 9. Capacity and the launch environment
- The **free-tier VM resize (4 OCPU / 24 GB)** from FEATURES_PLAN's hosting note is done before launch
- Feature 07 §11's k6 `search_mix` passes on **staging**, with every service staying inside its Feature 01 §16 memory limit. **Load tests never run against the shared production VM**, which hosts four other apps.
- Process count is checked against Feature 01 §6's connection budget

### 10. Consolidated QA pass (report §5)
- ~60–90 manual test cases compiled from every feature's acceptance criteria, run end-to-end
- Regression pass, cross-browser/mobile matrix (§4), integration tests against provider sandboxes (DVLA, MOT, valuation, Resend), the auth/tenant-isolation and admin-404 suites, the OWASP checklist (Feature 14 §8), and the search load test (§9)

### 11. Go/no-go checklist
Signed off before any real dealer or buyer is invited:
- [ ] Every alert in §5 test-fired and received; uptime checks live
- [ ] Restore drill done and timed within the RTO
- [ ] `ENVIRONMENT=production` boots with no placeholder secret (Feature 01 §2); `alembic current` = heads
- [ ] SPF, DKIM and DMARC verified for `notify.<domain>` (Feature 04 §6)
- [ ] Cloudflare rules in place, with verified crawlers not challenged (Feature 14 §6, Feature 13 §8); origin firewall allows only Cloudflare (Feature 01 §3)
- [ ] Search Console property verified and sitemap submitted (Feature 13 §8)
- [ ] Feature flags in their launch state; `value_my_car` on only with a real provider contract (Feature 12 §4)
- [ ] Demo stock limited to the intended regions, with labels visible (Feature 02 §9, Feature 08 §3)
- [ ] Legal pages live; ICO fee registered or documented; ROPA written; Google OAuth verified
- [ ] A real dealer completes sign-up → approval → listing, and receives a real test lead in their inbox
- [ ] All manual test cases pass, or have tickets with an explicit launch/no-launch decision

---

## Key Decisions

**Analytics is opt-in only.** PECR requires consent for non-essential cookies. The
banner gives Reject the same prominence as Accept. Launch metrics that don't need
cookies (server-side counts: listings, leads, alert sends) cover the business
dashboard either way. Whether identifier-free RUM is exempt is a legal question
answered here, not assumed (Feature 13 §11).

**Every alert has a threshold, an owner and a runbook.** "Alert on queue depth" with no
number is never configured. The table maps each failure signal the features emit to a
concrete rule.

**Backups are encrypted and stored with a different provider.** A backup on the same
provider as the VM shares its failure modes. An unencrypted dump in a bucket is a
personal-data breach waiting for one leaked key.

**Restore is tested, not assumed.** Restore time is recorded in the runbook and
compared with the RTO.

**Load tests run on staging, never on the shared VM.** A 30 requests/s soak on the
production box would degrade Yaqlo, Duely, Scout and Suretly to prove Autotrader works.

**Launch is regional.** Report §6: no amount of code fixes two-sided cold start.
Launching in one region with real dealers plus labelled demo stock elsewhere is a
go-to-market decision this feature's checklist enforces (demo stock scoped by region).

## Acceptance Criteria

**Legal & privacy**
- Privacy, cookie, terms and dealer-terms pages are live and linked from the footer and sign-up forms
- The privacy notice lists every processor and every retention period in §2 (review against the table)
- The ROPA exists, and ICO fee registration is complete or its non-applicability is documented
- No analytics request fires before consent (verified in a network log). Rejecting persists across visits. Bumping the policy version re-prompts.
- The CI finance-wording scan finds no matches in rendered public pages or email templates
- Every retention job in §2 has run successfully in staging within the last 48 hours

**States & accessibility**
- Every page in the audit checklist has a designed loading, empty, error, rate-limited and unavailable state (checklist complete with screenshots)
- No horizontal scroll at 320px on any public page. Keyboard-only users can complete search → detail → contact, and dealer listing creation.

**Operations**
- Every rule in §5 has been test-fired in staging and reached email and phone
- A deliberately thrown API error appears in error tracking with a request id. Stopping beat triggers the alert-run and sitemap alerts (tested with shortened windows).
- Stopping the API triggers an uptime alert within 3 minutes, and users see the maintenance page
- The restore drill completes into a fresh database, the app boots and passes smoke checks, and the time recorded is within the 4 h RTO
- A backup file can't be read without the encryption key
- The deploy script fails when `alembic current` doesn't equal the heads

**Capacity & launch**
- The VM is resized, and the k6 `search_mix` scenario passes on staging with no service exceeding its memory limit
- All manual test cases pass, or have tickets with an explicit launch/no-launch decision
- A real dealer completes sign-up → approval → listing → receives a real test lead
- The go/no-go checklist (§11) is fully signed off

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: concrete production alert table covering every signal from features 01–14 (§5)
- P0: encrypted, off-provider backups with RPO/RTO and a timed drill (§7)
- P0: deploy fails on unapplied migrations (§8)
- P0: load tests on staging only (§9)
- P0: ICO fee and ROPA (§1)
- P1: retention verification table (§2)
- P1: consent versioning (§1)
- P1: automated FCA wording scan (§1)
- P1: per-dependency outage runbooks and operational procedures (§8)
- P1: uptime checks from 2 locations (§6)
- P1: VM resize and connection budget as launch gates (§9)
- P1: concrete go/no-go checklist (§11)
- P1: rate-limited and unavailable states added to the audit (§3)

**Ownership moves:** retention jobs moved out to their owning features (Feature 08 §7,
10 §9, 11 §7; others defined at source in 04, 05, 12, 13, 14). This feature verifies
them (§2). Branded error pages moved to Feature 03 §4 (audited here, §3). Error
tracking had already moved to Feature 01 §12.

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| Point-in-time recovery (WAL archiving) | Real paying dealers (Phase 2 billing), or lead volume where losing up to 24 h is unacceptable |
| External penetration test | Before Phase 2 billing or private sellers, or after any security incident |
| Public status page | More than ~50 active dealers, or the first multi-hour outage |
| On-call rotation / paging tool | A second person operating the platform |
| Cookieless analytics product (no consent banner needed) | Consent rates make opt-in analytics unusable |
| Chaos / failure-injection drills beyond the restore drill | Multiple app instances (see Feature 01's blue/green P2) |

**Scale traps to avoid:** a multi-region disaster-recovery setup; an enterprise
observability stack on a shared free-tier VM; 24/7 on-call before there are
customers to justify it.
