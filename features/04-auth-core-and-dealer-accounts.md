# Feature 04 — Auth Core & Dealer Accounts

**Status:** Not Started
**Priority:** Must-Have
**Milestone:** M2 Supply
**Effort:** 8h optimistic / 16h realistic / 25h pessimistic
*(raised from 5/10/16h after a scale review: this is the first feature that sends
email, rate-limits, geocodes and issues sessions, so the shared email service, the
rate-limiter primitive, the geocoding service and session revocation are built here
once, for features 07–14 to reuse. See "Scale review" at the end.)*
**Depends on:** 01, 02, 03

## Description

Shared authentication infrastructure, plus the **dealer (B2B) account surface**: a
dealership signs up, gets approved by an admin, and adds team members. Report §2
infers that the real platform runs "two separate auth systems: a lightweight
consumer account … and a more permissioned dealer/business account system
(multi-user per dealership, role-based access)." This feature builds the shared core
and the dealer half. Feature 09 adds the consumer half on the same core, and Feature
14 adds admin MFA.

---

## Scope

### 1. Data model
| Table | Key fields |
|---|---|
| `User` | FastAPI-Users base (`email` citext unique, `hashed_password`, `is_active`, `is_verified`), `account_type` (`consumer` / `dealer` / `admin`, CHECK), `full_name`, `security_stamp` |
| `Dealer` | extends the core table from Feature 02 §2 (`name`, `slug`, `postcode`, lat/long, `region_code`, `status`, `is_demo`) with `trading_address`, `phone` (E.164), `website`, `companies_house_number` (optional, 8 chars), `fca_number` (optional, display only), `geo_precision` (`full` / `district`), `approved_at`, `approved_by`, `logo_image_id` (Feature 06 §9), `opening_hours` (JSONB, validated: 7 days × open/close `HH:MM` or closed) |
| `DealerMember` | `dealer_id` (FK, `ON DELETE CASCADE` per Feature 02 §9), `user_id` (unique: one dealer per user), `role` (`owner` / `staff`), `notify_new_leads` (bool, default true, used by Feature 10) |
| `DealerInvite` | `dealer_id` (FK cascade), `email` (citext), `role`, `token_hash` (SHA-256, unique), `expires_at`, `accepted_at`, `revoked_at`, `invited_by` |
| `AccessToken` | (registered with Feature 09 §6's personal-data registry, as are `AuthEvent`, `EmailMessage` and `DealerMember`) `token` (random 256-bit, stored hashed), `user_id`, `created_at`, `last_seen_at`, `expires_at`, `user_agent` (≤ 200 chars) |
| `AuthEvent` | §10 |
| `EmailMessage`, `EmailSuppression` | §6 |

### 2. Sessions and cookies
- FastAPI-Users **database token strategy** (`AccessToken` table), not JWT: sessions must be revocable (password change, member removal, dealer suspension in Feature 14).
- Cookie `__Host-session`: `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, no `Domain` (same-origin topology, Feature 01 §3)
- Lifetimes:

  | Account type | Idle timeout | Absolute lifetime |
  |---|---|---|
  | consumer, dealer | 14 days | 30 days |
  | admin | 30 min | 12 h (MFA in Feature 14) |

- `last_seen_at` is written **at most once per hour** per token, not on every request (no write amplification on browsing).
- Revocation helpers: `revoke_user_sessions(user_id, except_token=None)`, `revoke_dealer_sessions(dealer_id)`. Password change and reset revoke all *other* sessions. The `security_stamp` rotates on the same events.
- `GET /users/me` returns `{id, email, full_name, account_type, is_verified, dealer?: {id, name, slug, status, role}}` with `Cache-Control: private, no-store`.

### 3. Passwords
- Minimum 10 characters, maximum 128. No composition rules. Rejected if on a bundled list of the 100,000 most common passwords (no network call).
- **Argon2id** (pwdlib) at `m = 19 MiB, t = 2, p = 1` (OWASP's minimum recommended profile). **At most 4 hashes run concurrently per API process** (semaphore), so a login burst can't exceed ~80 MB of hashing memory inside the API's 512 MB limit on the shared VM (Feature 01 §16). Parameters are stored in the hash, so they can be raised later with rehash-on-login.
- Login always runs one hash, even for an unknown email, so response timing doesn't reveal which emails exist.

### 4. Registration, verification and recovery
- `POST /auth/dealer/register` creates `User(account_type=dealer)`, `Dealer(status=pending)` and `DealerMember(role=owner)` **in one transaction on the async session** that FastAPI-Users uses. Rejected: the user on the async session and the dealer rows on the sync session (Feature 01 §6), which would be two transactions and could leave a user with no dealership. `dispatch()` (Feature 01 §7) hooks the async session's underlying sync session, so the verification email still goes after commit.
- **Enumeration-safe responses:** registering with an email that already exists returns the same `202 {"status": "check_email"}` as a new registration. Nothing is created, and the existing owner gets a "someone tried to register with your email" message with sign-in and reset links. Forgot-password always returns 202. Login errors are always "Email or password is incorrect."
- **Email verification:** token valid 48 h, single use. A dealer's application appears in Feature 14's approval queue only once the email is verified.
- **Password reset:** token valid 1 h, single use, invalidated by any later reset request or password change.
- `POST /auth/login`, `POST /auth/logout`, `POST /auth/verify-email/request|confirm`, `POST /auth/forgot-password`, `POST /auth/reset-password`.
- **Extension point for Feature 14:** the login pipeline calls `post_password_check(user)`, which Feature 14 uses to require TOTP for admins before issuing a session.

### 5. Rate limiting (primitive owned here; policies per feature)
- `core/rate_limit.py`: `limit(name, key, rate, window)` as a FastAPI dependency. It uses a sliding-window counter (two fixed windows, weighted) in the **cache** Redis role (Feature 01 §8).
- Keys come from `get_client_ip(request)` (Feature 01 §3), the user id, or an HMAC of the submitted email. **IPv6 addresses are bucketed by /64**, because one client controls a whole /64.
- Over the limit: 429 Problem `rate_limited` with `Retry-After` (rendered by Feature 03 §3).
- **Fails open** if the cache Redis is unavailable (logs, increments `rate_limiter_unavailable_total`, alerted in Feature 15). Rejected: fail-closed, which would turn a cache outage into a full login outage.
- Auth policies:

  | Endpoint | Limit |
  |---|---|
  | register (dealer and, in Feature 09, consumer) | 8 / hour per IP |
  | login | 20 / 15 min per IP; 5 failures / 15 min per (email, IP); 30 failures / hour per email |
  | forgot-password | 5 / hour per IP; 3 / hour per email |
  | verify-email request | 3 / hour per user |
  | team invites | 50 / day per dealer |

  The full policy table for the platform lives in Feature 14 §6.

### 6. Transactional email service (first sender here; reused by 09, 10, 11, 14)
- `core/email.py`: `send_email(template, to, context, category, idempotency_key, user_id=None)` writes an `EmailMessage` row and calls `dispatch()` (Feature 01 §7), so a rolled-back transaction sends nothing. The task runs on the `notifications` queue and calls Resend through Feature 01 §9's shared client.
- **`EmailMessage`**: `id`, `category` (`auth` / `lead` / `alert` / `admin`), `template`, `to_email`, `user_id`, `idempotency_key` (unique), `status` (`queued` / `sent` / `delivered` / `bounced` / `complained` / `failed` / `suppressed`), `provider_message_id`, `attempts`, `last_error`, `created_at`, `sent_at`. It has no optimistic lock, and it's the only table delivery webhooks write to. Retention: 90 days (purge job owned here).
- **Outbox sweeper:** a beat task re-dispatches `EmailMessage` rows still `queued` after 10 minutes (Feature 01 §7 pattern), so a dispatch lost between commit and broker publish still sends. Feature 10's lead deliveries and Feature 11's alerts rely on it.
- **Idempotency:** the task skips any message already `sent`. The Resend request carries the same idempotency key (Resend's `Idempotency-Key` header support and window: to verify), so a crash between "provider accepted" and "row updated" doesn't produce a second email.
- **Suppression:** `EmailSuppression(email, reason: hard_bounce | complaint | manual, created_at)`. A hard bounce suppresses every category. A complaint suppresses `alert` only (password resets must still arrive) and fires an `email_complaint` hook, which Feature 11 uses to switch off that user's alerts. A suppressed send is recorded as `suppressed` without a provider call.
- **Delivery webhook:** `POST /api/v1/webhooks/resend`. The signature is verified (Resend signs webhooks Svix-style: to verify), events are deduplicated by event id, and the endpoint is exempt from the Origin check but keeps the 1 MB body limit.
- **Templates:** Jinja2 HTML + plain-text pairs in `backend/app/templates/email/`, one shared layout, absolute links from `PUBLIC_BASE_URL`, no tracking pixels. Each template has a snapshot test.
- **Domain setup** (runbook `ops/runbooks/email.md`): sending subdomain `notify.<domain>`, SPF and DKIM records from Resend, DMARC at `p=none` with reporting for two weeks, then `p=quarantine`.
- In tests the provider is stubbed (Feature 01 §9). A `mail_outbox` fixture captures sends for assertions.

### 7. Postcode geocoding service (first user here; extended by Feature 07)
- `modules/geo/services.py`: `geocode_postcode(postcode) -> GeoPoint(lat, lng, precision, outward_code, region_code)` calls postcodes.io through Feature 01 §9's client (postcodes.io rate limits and terms: to verify).
- Results are cached for 30 days in the cache Redis (`geo:pc:v1:{normalised}`). Postcodes don't move.
- **Unavailable path:** on `IntegrationUnavailable` the service returns the outward-code centroid from Feature 02 §8's bundled CSV with `precision=district`. Dealer registration then succeeds with `Dealer.geo_precision = district`, and a `regeocode_dealer` task retries with backoff for up to 24 h.
- An unknown postcode (postcodes.io 404, or an outward code not in the CSV) returns 422 `postcode_not_found` on the field, before any write.

### 8. Dealer profile and team
- `GET/PATCH /dealer/profile`: owner only for PATCH, optimistic lock on `updated_at`. Validation: phone normalised to E.164 (UK numbers), website `https://` only, Companies House number `^[A-Z0-9]{8}$`, name ≤ 100 chars.
- **Changing the postcode** re-geocodes and calls `listings.relocate_dealer_listings(dealer_id)` (Feature 05 §8), which moves active listings' coordinates through Feature 02 §5's `system_update()`, so no dealer's open edit is invalidated.
- `slug` is generated from name + town (with a `-2` suffix on collision) and becomes immutable at approval (dealer pages are SEO URLs, Feature 13).
- `GET /dealer/team`, `POST /dealer/team/invites` (owner; `Idempotency-Key`), `POST /dealer/team/invites/{id}/resend|revoke`, `PATCH /dealer/team/{member_id}` (owner; change role), `DELETE /dealer/team/{member_id}` (owner), `POST /dealer/invites/{token}/accept`
- **Invites:** token stored hashed, valid 7 days, single use. A resend revokes the previous token. Max 20 pending invites and 25 members per dealer. Accepting requires signing in, or registering through the invite, with the invited email (registration through the invite marks the email verified, since the link proved it). An email that already belongs to a consumer account gets 409 `email_has_consumer_account` (Feature 09's one-type-per-email rule). A member of another dealer gets 409 `already_member_of_another_dealer`.
- **Last-owner protection** runs under `SELECT … FOR UPDATE` on the dealer's owner rows, so two owners removing or demoting each other at the same moment can't leave zero owners.
- **Removing a member** deletes the membership and revokes all their sessions immediately.

### 9. Authorisation dependencies and tenancy
- `current_user`: any authenticated user
- `current_dealer_member`: a dealer account with a membership. Returns `(user, dealer, role)`. **Rejects with 403 `dealer_suspended` if `dealer.status = suspended`**, so Feature 14's suspension only has to flip the status and call `revoke_dealer_sessions()`. Login for a member of a suspended dealer also returns 403 `dealer_suspended`, with no session issued.
- `require_dealer_owner`
- **`require_approved_dealer`**: guards every write that makes something publicly visible (publishing a listing). Returns 403 `dealer_not_approved`.
- **Tenancy:** every dealer-scoped query goes through `dealer_scoped(query, dealer_id)`, and single-resource loads through `get_dealer_owned_or_404(model, id, dealer_id)`. There are no hand-written `WHERE dealer_id = …` clauses (grep check in CI). Cross-tenant access returns 404, not 403, so the response doesn't confirm the resource exists. Feature 01 §14's tenant-isolation harness walks every `/dealer/*` route.
- Dealer routes live under `/api/v1/dealer/*`. A consumer session never satisfies `current_dealer_member` (403 `dealer_account_required`).

### 10. Auth audit trail
- `AuthEvent`: `user_id` (nullable), `email_hmac` (for failures on unknown emails, so no raw email is stored), `event` (`login_succeeded`, `login_failed`, `logout`, `password_changed`, `password_reset_requested`, `password_reset_completed`, `email_verified`, `invite_sent`, `invite_accepted`, `member_removed`, `role_changed`, `sessions_revoked`), `ip` (from `get_client_ip()`), `user_agent` (≤ 200 chars), `created_at`
- Cursor-paginated (Feature 01 §5), viewable by admins in Feature 14. It answers "why can't dealer user Y sign in?" without reading logs.
- Retention: 12 months, then deleted (purge job owned here, listed in Feature 15's privacy notice)

### 11. UI (`/dealer/*` and auth pages)
- Sign-up wizard: account → dealership details (postcode lookup) → "check your email" → (after verifying) "awaiting approval" screen
- Pending-approval state: the dealer can build draft stock (Feature 05) but can't publish. A banner explains this (Feature 03 §5).
- Team page: list members, invite by email, resend or revoke an invite, change a role, remove a member
- Profile/settings page: dealership details, logo, opening hours
- Sign-in, forgot-password and reset pages. An expired session sends the user to sign-in with a safe `next` (Feature 03 §3).

---

## Key Decisions

**One `User` table, an `account_type` column, separate dealer membership.** "Two
separate auth systems" (§2 of the report) is a product separation, not a need for two
identity stores. One user table keeps password reset, verification and rate limiting
in one place. The separation is enforced in the **dependencies** (§9).

**Database-backed sessions, not JWTs.** Rejected: stateless JWT cookies. They can't be
revoked before expiry, and this plan needs revocation in three places: password
change, member removal and dealer suspension. One indexed lookup per request is cheap
at this scale.

**Dealer approval is manual in the MVP.** Report §6 lists fraud as a standing threat
to a public car marketplace, and fake dealers are the cheapest attack. An admin
(Feature 14) reviews each new, email-verified dealer. Drafts are allowed while
pending so onboarding isn't blocked.

**Registration runs in one async transaction.** The async/sync session split exists
only because FastAPI-Users requires async. Splitting one business operation across
the two would quietly break "all three rows or none."

**The email service is a foundation of this feature, not of Feature 10.** Auth emails
are the first sends. Building suppression, webhooks and idempotency here means lead
emails (10) and alerts (11) inherit them, instead of three slightly different senders
damaging one domain's reputation.

**Argon2 is tuned for a shared, memory-limited VM.** Library-default Argon2 profiles use
64 MB or more per hash. Ten concurrent logins would then push the API past its memory
limit, and the result looks like a random crash. The parameters and the semaphore
bound that.

**Rate limiting fails open.** A cache outage should degrade abuse protection, not take
sign-in down for everyone. The failure is alerted, so it isn't silent.

**Invite tokens are stored hashed** and expire after 7 days. Accepting requires
proving the invited email.

## Acceptance Criteria

**Registration & recovery**
- Dealer registration with an error injected after the `Dealer` insert leaves no `User`, `Dealer` or `DealerMember` row and sends no email
- An invalid postcode returns 422 on the postcode field before anything is written. A postcodes.io timeout still registers the dealer with `geo_precision = district` and queues a re-geocode task.
- Two concurrent registrations with the same email (any casing) result in exactly one account
- Registering with an existing email returns the same status and body as a new email, creates nothing, and sends the existing user a notice
- Forgot-password for an unknown email returns 202 and sends nothing. A reset token fails after 1 hour and on second use.
- An unverified dealer does not appear in the approval queue

**Sessions & credentials**
- The session cookie is named `__Host-session` and is `Secure`, `HttpOnly`, `SameSite=Lax`, with no `Domain`
- Changing or resetting the password revokes every other session for that user; the current one keeps working
- A token idle for more than 14 days, or older than 30 days, is rejected with 401
- A 9-character password, and a password on the common-password list, are rejected with field errors
- At most 4 password hashes run concurrently per process (unit test with a blocking hasher)
- `GET /users/me` responses carry `Cache-Control: private, no-store`

**Rate limiting**
- The 6th failed login for the same email and IP within 15 minutes returns 429 with `Retry-After`
- With the cache Redis stopped, login still works and `rate_limiter_unavailable_total` increases
- Two IPv6 addresses in the same /64 share one rate-limit bucket

**Email**
- A rolled-back transaction that called `send_email` sends nothing
- Calling `send_email` twice with the same idempotency key makes one provider call
- A hard-bounce webhook suppresses the address, and the next send is recorded as `suppressed` with no provider call. A complaint suppresses `alert` emails only and fires the `email_complaint` hook.
- An `EmailMessage` left `queued` with no task (dispatch lost) is sent exactly once by the sweeper within 15 minutes
- A webhook with an invalid signature returns 401 and changes nothing. Replaying a valid event id is a no-op.
- Every template renders both HTML and plain text with absolute links (snapshot tests)

**Dealer team & tenancy**
- A pending dealer can create drafts, and publishing returns 403 `dealer_not_approved`
- A staff member cannot invite, remove members, change roles, or edit the dealer profile (403)
- The last owner cannot be removed or demoted, including when two owners try to remove each other concurrently (exactly one succeeds)
- The database holds no raw invite token. A token fails after 7 days, after use, and after a resend.
- Accepting an invite while signed in with a different email returns 403. An email that belongs to a consumer account returns 409 `email_has_consumer_account`.
- A removed member's next request returns 401
- A member of a suspended dealer gets 403 `dealer_suspended` at login and on every `/dealer/*` route
- Every `/dealer/*` endpoint, called by a member of dealer B against dealer A's resources, returns 404 (Feature 01 §14 harness)
- A consumer session calling any `/dealer/*` endpoint gets 403
- Changing the dealer's postcode moves its active listings' coordinates without changing their `updated_at`

**Audit**
- Each `AuthEvent` type is written with the IP from `get_client_ip()`. A failed login for an unknown email stores only `email_hmac`.

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: registration as one async-session transaction with after-commit email (§4)
- P0: transactional email service with an `EmailMessage` log, outbox sweeper, idempotency, suppression, a signed delivery webhook and domain authentication (§6)
- P0: rate-limiter primitive (Redis cache role, `get_client_ip()`, IPv6 /64, Problem 429, fail-open) (§5)
- P0: revocable DB-backed sessions with defined lifetimes and revocation helpers (§2)
- P0: suspended-dealer rejection in `current_dealer_member` and at login (§9)
- P0: geocoding service with cache and an offline district fallback (§7)
- P1: Argon2id tuned for the VM, with a concurrency bound (§3)
- P1: enumeration-safe registration, login and recovery (§4)
- P1: token lifetimes for verification, reset and invites (§4, §8)
- P1: last-owner race protection (§8)
- P1: invite edge cases (§8)
- P1: dealer relocation without bumping lock tokens (§8)
- P1: `AuthEvent` audit trail with retention (§10)
- P1: profile field validation (§8)
- P1: `get_dealer_owned_or_404` plus a grep check (§9)

**Ownership moves:** none taken from other features. This feature now *provides* the
email service (used by 09, 10, 11, 14), the rate-limiter primitive (policies in each
feature, consolidated in Feature 14 §6) and the geocoding service (extended by Feature
07). The postcode integration therefore first lands here rather than in Feature 07.

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| MFA for dealer users | First dealer account takeover, or a dealer-group customer asks for it |
| Dealer SSO (Google Workspace / Microsoft) | Dealer groups with more than 25 staff onboard |
| "Active sessions" page for users | Support requests about unknown sign-ins |
| Breached-password check via HIBP k-anonymity API | An account takeover from credential stuffing that the common-password list didn't catch |
| Automated Companies House verification | Manual approvals exceed ~100 a month (see Feature 14) |
| Separate sending subdomains per stream (auth vs alerts) | Alert volume reaches Gmail/Yahoo bulk-sender thresholds (5,000/day) or alert complaints affect auth deliverability |
| Dealer-group (multi-site) accounts | The first dealer group with more than one site signs up |

**Scale traps to avoid:** a separate identity service or a second user store per
account type; a third-party auth platform introduced only for the dealer side.
