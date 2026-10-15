# Feature 09 — Consumer Accounts & Saved Cars

**Status:** Not Started
**Priority:** Must-Have
**Milestone:** M4 Engagement
**Effort:** 6h optimistic / 12h realistic / 18h pessimistic
*(raised from 4/8/12h after a scale review: a personal-data registry that makes
erasure and export cover every feature's tables, safe Google account linking, and
idempotent saves with correct counters. See "Scale review" at the end.)*
**Depends on:** 04, 08

## Description

The lightweight consumer half of the two-account model (report §2: "low friction").
Browsing, searching, viewing and contacting dealers never require an account.
An account unlocks **saved cars** (here) and **saved searches + alerts** (Feature 11),
the features that bring buyers back. This feature also owns the **UK GDPR
right-of-access and right-to-erasure paths** for every account type.

---

## Scope

### 1. Consumer sign-up and sign-in
- Email + password on the Feature 04 core with `account_type=consumer`: same session strategy (Feature 04 §2), password rules (§3), enumeration-safe responses (§4), and rate limits (§5)
- Email verification is required before any alert email is sent (Feature 11). Saving cars works immediately.
- Dependency `current_consumer`. A dealer or admin session gets 403 `consumer_account_required`, with a message explaining that a separate consumer account is needed.

### 2. Google sign-in (consumers only)
- OpenID Connect authorization-code flow with **PKCE**, `state` and `nonce`, and a same-origin callback (`/api/v1/auth/google/callback`). The ID token is verified (signature, `aud`, `iss`, expiry, `nonce`).
- `OAuthAccount(user_id, provider, subject, email_at_link, created_at)`, unique `(provider, subject)`. **Accounts are matched by Google's `sub`, not by email**, so a Google user who changes their address still reaches the same account.
- Linking rules for a first-time Google sign-in:

  | Existing account with that email | Outcome |
  |---|---|
  | none | Create a consumer account, `is_verified = true` |
  | verified consumer | Link the Google account |
  | **unverified** consumer with a password | Link, **clear the password and revoke its sessions** (pre-hijack defence: someone else may have registered that address) |
  | dealer or admin | 409 `email_has_dealer_account`; nothing linked |
- A token with `email_verified = false` is rejected
- Production use needs a Google OAuth consent screen and app verification (requirements and timeline: to verify), done before launch (Feature 15 checklist)

### 3. Contextual sign-in (pending action)
- Tapping the save heart while signed out opens a sign-in sheet. The intended action is kept in `sessionStorage` (`{type: "save", listing_id}`) and carried through the OAuth `state`. Once sign-in completes, it runs automatically, without the user tapping again.
- Return paths use only **same-origin relative `next` values** (Feature 03 §3). Anything else falls back to the home page, so there's no open redirect.

### 4. Saved cars
- `SavedListing(user_id, listing_id FK ON DELETE CASCADE, created_at, price_at_save_pence)`, primary key `(user_id, listing_id)`. **Cap: 500 per user** (409 `saved_limit_reached`).
- `PUT /me/saved-listings/{listing_id}` runs `INSERT … ON CONFLICT DO NOTHING RETURNING`, and `stats.increment(listing_id, "saves", +1)` (Feature 05 §6) **only when a row was inserted**. `DELETE` decrements only when a row was actually deleted. Double taps and concurrent requests can't double-count. Only publicly visible listings can be newly saved (404 otherwise).
- `GET /me/saved-listings` (paginated, newest first): batch-loaded cards in **≤ 4 queries**
- `GET /me/saved-listing-ids`: the id set (≤ 500) for heart state on cards and the detail page, fetched once per session by the client island (Feature 03 §6). `Cache-Control: private, no-store`.
- `/account/saved` states per card:

  | Listing state | Card |
  |---|---|
  | active / reserved | normal, plus "**Price dropped £X since you saved**" when the current price is below `price_at_save_pence` |
  | sold (≤ 30 days) | greyed with a "Sold" badge; opens the sold page; no contact |
  | sold > 30 days, archived, `held`, `hidden`, `removed` | "No longer available": title and cover only, no link, a remove button |

### 5. Account settings
- Name; **email change** (verification sent to the new address, a notice sent to the old one, and the old address stays the login until the new one is verified); password change (revokes other sessions, Feature 04 §2); connected Google account (unlinking is refused with 409 `password_required` if no password is set)
- Email preferences: a master switch for all alerts, and price-drop alerts on/off (read by Feature 11)
- "My enquiries" (Feature 10), "Saved searches" (Feature 11)
- Delete account and download my data (§6)

### 6. Personal-data registry: erasure and export (all account types)
- `core/personal_data.py`: each module registers a `PersonalDataHandler(name, export(user_id) -> dict, erase(user_id))`. **The registry, not this feature, knows which tables hold personal data**, so a later feature that adds a user-linked table must register a handler.
- **Introspection test:** every table with a foreign key to `user.id`, or a column listed as holding an email address, must have a registered handler or an explicit, commented exemption. A new table without one fails CI.
- Handlers known at this point:

  | Owner | Data | On erasure |
  |---|---|---|
  | 04, 09 | `AccessToken` (04 §2), `OAuthAccount` (§2) | deleted |
  | 04 | `AuthEvent` | `user_id` set null; `ip`/`user_agent` cleared |
  | 04 | `EmailMessage` | `to_email` replaced by a hash; `user_id` null |
  | 04 | `EmailSuppression` | **kept** (stops us emailing an address that bounced or complained); stated in the privacy notice |
  | 04 | `DealerMember` | removed; **409 `last_owner`** if the user is a dealer's last owner (ownership must be transferred first) |
  | 09 | `SavedListing` | deleted (`saves` counters decremented) |
  | 10, 11, 12 | leads, saved searches/alert logs, saved valuations | registered by those features |

- `DELETE /me` requires a password re-entry, or a sign-in within the last 10 minutes for Google-only accounts. It runs every eraser **and** deletes the `User` row **in one transaction**: an eraser that fails leaves everything intact. A confirmation email goes to the captured address afterwards (via `dispatch()`).
- Backups keep erased data until they expire (14 days, Feature 15). The privacy notice says so.
- `GET /me/export`: JSON from every handler's `export()`, as a download (`Content-Disposition: attachment`, `private, no-store`). Synchronous at MVP data sizes. Rate limit: 3 per day per user.
- An erased user can register again with the same email (it's a new account).

### 7. UI
- Sign-in / sign-up sheet and pages (email + password, "Continue with Google")
- `/account` (settings, §5), `/account/saved` (§4)
- Delete-account flow: explains what is deleted, what is kept (anonymised enquiries, the email suppression entry, backups for 14 days), re-auth, confirmation

---

## Key Decisions

**No guest favourites in localStorage.** Merging anonymous saves into an account on
sign-up adds edge cases (conflicts, multiple devices) for little benefit when the
contextual sign-in prompt already restores the intended action.

**Google OAuth from day one** for consumers (not dealers). Consumer conversion is
very sensitive to sign-up friction. Dealers are fewer, higher-intent, and pass
manual approval anyway.

**Accounts are matched on Google `sub`, and unverified password accounts lose their
password on link.** Rejected: matching on email alone, which breaks when a Google
address changes. Rejected also: linking while leaving the old password in place.
Someone who pre-registered the victim's address would keep a working password into
the victim's account.

**Erasure is a registry with an introspection test, not a list in this doc.** Six
later features add user-linked tables. A hand-maintained erasure function would miss
one, and the miss would only surface during a real erasure request, as a compliance
failure. The test makes "forgot to handle personal data" a CI failure.

**Consumer and dealer accounts can't share an email in the MVP.** One login has one
account type. A dealer who also wants to save cars personally uses a different email.
Supporting both on one login is a Phase 2 nicety that would complicate every
dependency check in Feature 04.

**Counters move only on real inserts and deletes.** `saves` is shown to dealers. If a
double-tap or retry could add two, the number would drift away from the truth.

## Acceptance Criteria

**Sign-in & Google**
- A Google ID token with `email_verified = false`, a wrong `nonce`, or a mismatched `state` is rejected and no account is created or linked
- First Google sign-in for an email with an unverified password account links it, clears the password and revokes that account's existing sessions
- Google sign-in for an email belonging to a dealer returns 409 `email_has_dealer_account` and links nothing
- A Google account whose email changed signs into the same user (matched on `sub`)
- Consumer registration obeys Feature 04's rate limits and enumeration-safe responses (the Feature 04 tests, parametrised for consumers)

**Pending action**
- A signed-out user taps save, signs in with Google, and the car is saved with no further tap
- A `next` pointing at another host is ignored and the user lands on the home page

**Saved cars**
- Two concurrent PUTs for the same car create one row and raise `saves` by exactly 1. Two DELETEs lower it by exactly 1. No error toast either way.
- The 501st save returns 409 `saved_limit_reached`
- The saved page shows the price-drop badge when the current price is below `price_at_save_pence`
- A sold saved car shows a "Sold" badge and can't reach a contact form. A removed, hidden or long-archived car shows "No longer available" with no link.
- `GET /me/saved-listing-ids` carries `Cache-Control: private, no-store`. `GET /me/saved-listings` runs in ≤ 4 queries.
- A dealer session saving a car gets 403 `consumer_account_required`. A consumer session calling any `/dealer/*` route gets 403.

**Account settings**
- An email change takes effect only after the new address is verified. The old address receives a notice.
- Unlinking Google from an account with no password returns 409 `password_required`

**Erasure & export**
- The introspection test fails when a table with an FK to `user.id` is added without a handler or exemption
- Deleting an account requires recent authentication. It removes the user, saved cars, sessions and OAuth links. Their leads remain for the dealer with name and email replaced by "Deleted user". Their `EmailMessage` rows no longer contain the address.
- If any eraser raises, the account and all its data remain unchanged
- A dealer's last owner can't delete their account (409 `last_owner`)
- `GET /me/export` contains a section for every registered handler. The 4th export in a day returns 429.
- An erased user's email can be used to register a new account

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: personal-data registry with an FK introspection test and an all-or-nothing erasure (§6)
- P0: Google OIDC with PKCE, state and nonce; matching on `sub`; pre-hijack-safe linking rules (§2)
- P0: same-origin-only `next` for the pending action (§3)
- P1: idempotent saves with counters that move only on real changes (§4)
- P1: 500-save cap (§4)
- P1: complete saved-card states, including moderation and archive (§4)
- P1: `private, no-store` id set (§4)
- P1: re-auth before deletion (§6)
- P1: email-change flow (§5)
- P1: Google unlink guard (§5)
- P1: export rate limit (§6)
- P1: `current_consumer` dependency (§1)

**Ownership moves:** none taken. This feature now *provides* the personal-data
registry that features 04, 10, 11 and 12 register with. The erasure of dealer users
goes through it too (with Feature 04's last-owner rule).

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| One login with both consumer and dealer roles | Dealer staff repeatedly ask to save cars on their work login |
| Apple / Microsoft sign-in | Sign-up analytics show drop-off on iOS without a non-Google social option |
| Passkeys | Browser support and user demand justify a second credential type |
| Asynchronous export (emailed link) | An export takes more than 5 s, or a user's data exceeds ~5 MB |
| Guest favourites merged on sign-up | Data shows many signed-out saves abandoned at the sign-in sheet |
| Self-service ownership transfer for dealers | More than a handful of support requests to transfer ownership |

**Scale traps to avoid:** a separate consumer identity provider or CIAM product for a
two-account-type MVP.
