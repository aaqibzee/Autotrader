# Feature 14 — Trust, Safety & Admin Console

**Status:** Not Started
**Priority:** Must-Have
**Milestone:** M5 Launch
**Effort:** 9h optimistic / 18h realistic / 28h pessimistic
*(raised from 6/12/20h after a scale review: a single-writer moderation service that
never bumps lock tokens, reversible suspension, abuse-resistant report thresholds, a
DB-enforced append-only audit log, encrypted admin MFA and the consolidated
rate-limit policy table. See "Scale review" at the end.)*
**Depends on:** 04, 05, 06, 08, 10, 12

## Description

The minimum safety layer a public car marketplace can't launch without, plus the
internal console to operate it. Report §6: "a public car marketplace is a high-value
scraping target (competitors, data brokers)", and report §3 lists fraud/spam
detection as an implied backend feature. The real platform's defences are tuned
against real attackers. This MVP version is **manual review plus sensible automated
limits**. It's cheap to build and closes the obvious holes. It plugs into hooks
earlier features already expose (Feature 04 §4 login hook, Feature 05 §2 moderation
hook, Feature 02 §5 visibility), so no earlier feature's code is patched.

---

## Scope

### 1. Admin accounts and access
- Admins are created only by CLI (`create_admin --email`), never through the API. `account_type = admin` (Feature 04 §1).
- **TOTP MFA**, via Feature 04 §4's `post_password_check` hook. Enrolment at first sign-in. The TOTP secret is **encrypted at rest** (Fernet, key `MFA_ENCRYPTION_KEY` from the server `.env`, Feature 01 §2). 10 single-use recovery codes, stored hashed. Admin sessions: 30 min idle, 12 h absolute (Feature 04 §2).
- Every `/admin` page and `/api/v1/admin/*` endpoint returns **404** to non-admins, consumers, dealers and anonymous users alike. A route-table test covers every admin route (same harness style as Feature 01 §14).
- Admin sign-ins and failures are `AuthEvent`s (Feature 04 §10)

### 2. Admin audit log
- `AdminAction(id, actor_user_id, action, target_type, target_id, reason, details JSONB, request_id, created_at)` is written **in the same transaction** as the action, by an `@admin_action(...)` decorator that every mutating admin endpoint must use. A route-table test fails if one doesn't.
- **Append-only at the database:** the `app_rw` role (Feature 01 §6) has `INSERT` and `SELECT` on `admin_action`, and `UPDATE`/`DELETE` are revoked. Even an application bug can't rewrite history.
- Listing actions also write `ListingAuditEvent` (Feature 05 §7) with `actor_type = admin`. Opening a lead's contents in the console is logged as `lead_viewed`.
- Cursor-paginated (Feature 01 §5). Retained 24 months.

### 3. Dealer approval and management
- **Approval queue:** dealers with `status = pending` **and a verified email** (Feature 04 §4), oldest first, with the details submitted in Feature 04 (company number, address, phone, website), quick links to Companies House search and Google Maps, and the dealer's `AuthEvent` history
- Actions:

  | Action | Effect |
  |---|---|
  | Approve | `status = approved`, `approved_at/by`; slug frozen (Feature 04 §8); approval email; publishing works immediately |
  | Reject | `status = rejected` (a value added to Feature 02 §2's CHECK); reason emailed; drafts kept, can't publish |
  | Request info | email with the admin's free-text question; stays `pending` |
  | Suspend | `status = suspended`; `revoke_dealer_sessions()` (Feature 04 §2); **every publicly visible listing → moderation `hidden` with flag reason `dealer_suspended`** |
  | Unsuspend | `status = approved`; **only** listings hidden for `dealer_suspended` return to `clear` |
- Suspension keeps the dealer's own listing states (reserved stays reserved), so unsuspending restores exactly what was live. Rejected: "unpublish all listings", which loses that state and fights the dealer's lifecycle (Feature 05 §1). With the 500-listing cap (Feature 05 §2), suspension completes in one request.
- Dealer view: stock (read-only), lead delivery health (Feature 10 §4), recent `AuthEvent`s, `AdminAction` history

### 4. Moderation service (the only writer of `moderation_status`)
- `modules/admin/moderation.py` owns `Listing.moderation_status` (Feature 02 §3). Every write goes through `system_update()` (Feature 02 §5), so **moderation never bumps a dealer's lock token**, then calls `visibility.on_change()`. The resulting `ListingVisibilityChanged` event triggers Feature 08 §5's CDN purge.
- Transitions:

  | From → To | Cause |
  |---|---|
  | `clear` → `held` | an automated check fails (below) at publish or on a material edit |
  | `clear` → `hidden` | report threshold (§5), admin hide, or dealer suspension (§3) |
  | `held`/`hidden` → `clear` | admin release (sets `listed_at` if first visible, Feature 02 §5) or unsuspend |
  | any → `removed` | admin takedown. **Final**: variants deleted and purged (Feature 06 §7), dealer emailed with the reason, republish blocked (Feature 05 §1) |
- `ModerationFlag(listing_id, source: check | report | admin | suspension, reason_code, details, created_at, resolved_at, resolved_by, resolution)` records why. Feature 05 §10's "Under review" badge and the admin queue read it.
- **`moderation.evaluate(listing, trigger)`** implements Feature 05 §2's hook. It must take < 50 ms, so it makes no provider calls (`expected_value()` uses only cached provider data and comparables). Each failed check creates a flag and returns `held`:
  - price outside 30%–200% of `valuations.expected_value()` (Feature 12 §6), when the expected value is known. "Too good to be true" is the classic scam pattern.
  - a normalised VRM already active on **another** dealer's listing (Feature 02 §7 index)
  - a description containing a UK phone number, an email address, a URL, external-payment wording ("bank transfer", "deposit to secure"), or finance wording (APR, "monthly payments", "finance available"; the FCA list is maintained with Feature 15). The phrase lists live in config.
  - **probation:** the first 5 listings of a dealer approved less than 30 days ago
- A subscriber emails the dealer when a listing is held or hidden, with the reason
- **Review SLA:** held listings reviewed within one working day. Metric `moderation_oldest_held_seconds`, alerted after 24 h (Feature 15).

### 5. Report a listing (public)
- "Report this listing" (Feature 08 §2): reason (`scam` / `wrong_details` / `already_sold` / `offensive` / `other`) plus an optional note (≤ 500 chars). Works signed in or out.
- `ListingReport(listing_id, reporter_user_id, reporter_hash, reason, note, created_at)`. `reporter_hash = HMAC(secret, client IP /24 for IPv4 or /64 for IPv6)`; no raw IP is stored. Retained 12 months, and registered with Feature 09 §6's personal-data registry.
- Rate limits: 5 reports per day per IP, one per listing per reporter. Reports by members of the listing's own dealer are ignored.
- **Auto-hide** (only for `scam` and `offensive`): within 24 h, **3 distinct reporters including at least one verified signed-in account, or 5 distinct anonymous reporters** → `hidden`, a flag, the dealer notified and the item placed at the top of the queue. Rejected: "any 3 reporters", which a competitor can meet with three phone hotspots to knock a rival's stock offline. Other reasons only queue for review.
- Reports queue: grouped by listing, sorted by distinct-reporter count. Actions: dismiss, hide, take down (reason sent to the dealer), suspend dealer.

### 6. Abuse limits — consolidated rate-limit policy (primitive: Feature 04 §5)
All app limits use Feature 04 §5's limiter, keyed by `get_client_ip()` (Feature 01 §3),
never `request.client.host`, and return 429 with `Retry-After`. **This table is the
single list of policies.** Each value is decided in its owning feature:

| Surface | Limit | Owner |
|---|---|---|
| register / login / forgot-password / verify | see table | Feature 04 §5 |
| search results / count | 120 / 60 per min per IP | Feature 07 §9 |
| detail API | 300 per min per IP | Feature 08 §4 |
| phone reveal | 20 per hour per IP | Feature 08 §6 |
| view beacon | 60 per min per IP | Feature 08 §7 |
| lead submit | 5/h per IP; 3/day per email per listing; 20/day per email | Feature 10 §2 |
| valuation | 5/day per IP signed out; 20/day per account; global daily cap | Feature 12 §5 |
| plate lookup (dealer) | 200/day, 30/min per dealer | Feature 05 §5 |
| image upload URLs | 300/h per dealer | Feature 06 §2 |
| data export | 3/day per user | Feature 09 §6 |
| RUM beacon | 30/min per IP | Feature 13 §11 |
| listing reports | 5/day per IP | §5 |

- **Cloudflare** (configuration documented in `ops/cloudflare.md`): WAF managed rules, bot protection on `/cars` and `/api/v1/search*`, and a challenge for low-score clients on deep pagination, **with verified search-engine bots allowed** (Feature 13 §8). Which bot features (Bot Fight Mode vs Super Bot Fight Mode, bot scores, edge rate-limiting rules) are available on our plan is **to verify**. The app-level limits above don't depend on them.
- Search page-depth cap (50 pages, Feature 07 §9). No bulk listing API exposed publicly. Phone reveal on tap (Feature 08 §6). No email addresses in public HTML. `robots.txt` is owned by Feature 13 §7.

### 7. Admin console screens (`/admin`, `AdminLayout` from Feature 03 §5)
- Approvals queue (§3), dealer management (§3), moderation queue of held listings with their flags (§4), reports queue (§5)
- **Listing search:** by id, normalised VRM, dealer or title, with the listing's audit history (Feature 05 §7) and moderation actions
- **Lead delivery failures** (Feature 10 §4: leads whose every recipient delivery failed or bounced). Metadata only; opening the content is logged (§2).
- **Ops dashboard:** listings by status, new dealers/consumers/leads per day, alert emails sent (Feature 11 §9), search p95 and the top zero-result searches (Feature 07 §12), web-vitals p75 (Feature 13 §11), the weekly top-10 slow queries (Feature 01 §12), queue depths, valuation budget used (Feature 12 §3), email bounce and complaint rates (Feature 04 §6), oldest held listing (§4)
- Dashboard queries are cached for 5 minutes, each under 500 ms. List endpoints are cursor-paginated and `assert_max_queries`-guarded.

### 8. Security basics (report §5 OWASP pass, owned here with Feature 15)
- **Verify, don't redefine,** the Feature 01 baseline: security headers and CSP (Feature 01 §4, §11), dependency audits and secret scanning (Feature 01 §11), log redaction (Feature 01 §11). *(The CSP and header definitions previously duplicated here are owned by Feature 01.)*
- An OWASP checklist run before launch, with each item pointing at its control:

  | Risk | Control |
  |---|---|
  | broken access control | tenant harness (Feature 01 §14), admin 404 harness (§1) |
  | injection | ORM only; CI grep for raw SQL string formatting |
  | XSS | plain-text descriptions (Feature 08 §2), safe JSON-LD (Feature 13 §5), CSP |
  | CSRF | Origin check (Feature 01 §4) |
  | open redirect | same-origin `next` (Feature 03 §3) |
  | SSRF | no server-side fetch of user-supplied URLs (a dealer's website is stored, never fetched) |
  | file upload | Feature 06 §2–§4 |
  | brute force / enumeration | Feature 04 §3–§5 |
- `/.well-known/security.txt` with a contact address and an expiry date

### 9. Observability
- Metrics: held-queue size, `moderation_oldest_held_seconds`, reports and auto-hides per day, admin actions per day, 429s by policy name

---

## Key Decisions

**Hold for review, don't auto-reject.** False positives on real dealers are expensive
during the cold-start phase, when every dealer matters. Automated checks route to a
human. They never silently block.

**One writer for moderation, through `system_update()`.** Moderation is a background
and admin concern. If it bumped `updated_at`, every hold, report and suspension would
throw away a dealer's in-progress edit with a 409, which is the Yaqlo failure again.

**Suspension hides, it doesn't unpublish.** The dealer's own lifecycle state is theirs.
A suspension is an overlay that can be lifted cleanly.

**Report thresholds assume a motivated competitor.** Auto-hide is powerful, so it needs
either a verified account among the reporters or a larger anonymous crowd, and it
applies only to scam and offensive reports.

**Manual dealer approval is the main fraud control.** Most marketplace scams need a
seller account, and checking a company's existence at sign-up is the cheapest,
highest-leverage control available. It doesn't scale past a few hundred sign-ups a
month. Revisit with automated Companies House API checks when it stops scaling.

**The audit log is append-only at the database, not by convention.** It's needed for
dealer disputes ("why was my listing removed?") and is basic hygiene for any
privileged tooling. Revoked grants make it true even if the code has a bug.

**One rate-limit policy table.** Limits are decided by the features that know the
surface, but listed in one place, so an operator can see the whole abuse posture and
no surface is left unlimited by accident.

## Acceptance Criteria

**Admin access & audit**
- Non-admin sessions (consumer, dealer, anonymous) get 404 on every `/admin` page and `/api/v1/admin/*` route (route-table test). Admin sign-in requires TOTP. A recovery code works once.
- The stored TOTP secret is not readable without `MFA_ENCRYPTION_KEY`
- Every mutating admin endpoint produces an `AdminAction` row in the same transaction (route-table test). An `UPDATE` or `DELETE` on `admin_action` as `app_rw` fails with a permission error.
- Opening a lead's content in the console writes a `lead_viewed` action

**Dealers**
- An unverified pending dealer doesn't appear in the approval queue
- Approving a dealer lets them publish immediately. Rejecting sets `rejected` and emails them the reason.
- Suspending a dealer hides all their visible listings and revokes their sessions within one request, and their next request gets 403 `dealer_suspended`. Unsuspending restores exactly those listings, with reserved ones still reserved.

**Moderation**
- Moderation changes never change `Listing.updated_at`. A dealer edit with the pre-hold token still succeeds.
- A listing priced at 25% of its expected value is held for review, not visible, with a `price_outlier` flag
- A VRM already active at another dealer triggers a hold. The same dealer's duplicate doesn't.
- Descriptions containing a phone number, an email, a URL, "bank transfer" or "APR" are held with the matching reason
- A newly approved dealer's first 5 listings are held. The 6th isn't.
- `moderation.evaluate` makes no provider calls and completes in under 50 ms on the 50k perf profile
- Releasing a held listing sets `listed_at` and purges its URLs (Feature 08 §5). A takedown makes the page 410, deletes its image variants, and blocks republishing.

**Reports**
- 3 `scam` reports within 24 h from distinct reporters including one verified account hide the listing. 3 anonymous reporters don't, 5 do. A single user reporting 3 times does not.
- `wrong_details` reports never auto-hide
- Reports from the listing's own dealer's members are ignored. The 6th report from one IP in a day returns 429.
- `ListingReport` stores no raw IP, and reports are erased with the reporter's account

**Limits & security**
- The search rate limit returns 429 with `Retry-After`, and one human browsing normally never hits it (k6 human-pace scenario)
- Every policy in the §6 table has a test that triggers its 429
- Security headers are present on all HTML responses (Feature 01 header test, re-run against production config)
- `/.well-known/security.txt` is served with a contact and an expiry
- Each ops-dashboard query responds in under 500 ms on the 50k perf profile

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: moderation service as the single writer of `moderation_status`, via `system_update()`, with a transition table and `ModerationFlag` (§4)
- P0: `moderation.evaluate` implementing Feature 05 §2's hook, with no provider calls (§4)
- P0: reversible suspension as a hidden overlay (§3)
- P0: abuse-resistant auto-hide thresholds (§5)
- P0: DB-enforced append-only `AdminAction` with a mandatory decorator (§2)
- P0: encrypted TOTP secrets and hashed recovery codes (§1)
- P0: admin 404 route harness (§1)
- P0: `rejected` dealer status (§3; knock-on to Feature 02 §2)
- P1: consolidated rate-limit policy table (§6)
- P1: held-listing SLA metric (§4)
- P1: finance wording in the hold list (§4)
- P1: lead-content access logging (§2)
- P1: dashboard query budget (§7)
- P1: OWASP checklist mapped to controls (§8)
- P1: `security.txt` (§8)
- P1: Cloudflare plan features marked to verify (§6)
- P1: reporter privacy (§5)

**Ownership moves:** CSP and security-header definitions are removed from here (owned
by Feature 01 §4/§11; verified here). `robots.txt` is owned by Feature 13 §7. The
rate-limiter primitive is owned by Feature 04 §5; this feature owns the consolidated
policy table.

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| Automated Companies House API checks at sign-up | Manual approvals exceed ~100 a month |
| Re-authentication (fresh TOTP) before destructive admin actions | More than 2 admins, or any admin-account incident |
| Admin IP allowlist / access via Cloudflare Access | More than 2 admins, or admin access from shared networks |
| ML / rules-engine fraud scoring | Confirmed scam listings exceed ~1 a week despite holds |
| Cloudflare configuration as code (Terraform) | More than ~10 Cloudflare rules, or a second environment needing the same rules |
| Dealer appeal workflow in-app | More than a handful of takedown disputes a month |
| Image moderation | See Feature 06 P2 |

**Scale traps to avoid:** a separate trust-and-safety service or rules engine; ML fraud
models without labelled fraud data; CAPTCHAs on browsing.
