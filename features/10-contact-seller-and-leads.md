# Feature 10 — Contact Seller & Dealer Lead Inbox

**Status:** Not Started
**Priority:** Must-Have (this is the moment of value for dealers)
**Milestone:** M4 Engagement
**Effort:** 7h optimistic / 15h realistic / 23h pessimistic
*(raised from 5/10/16h after a scale review: per-recipient delivery tracking on the
outbox pattern, read state and delivery state kept off the locked `Lead` row,
server-side spam timing, header-injection-safe emails, and retention/erasure are
specified here. See "Scale review" at the end.)*
**Depends on:** 04, 05, 08 (09 optional: signed-in users get prefilled forms)

## Description

The buyer contacts the dealer about a specific car, and the dealer sees and works
those enquiries. Report §3 lists "contact-seller / lead capture forms." For the
business, **leads are the product dealers would eventually pay for** (Phase 2
billing). Lead delivery therefore has to be reliable and measurable from the start:
every lead reaches every intended recipient, or someone is told it didn't.

---

## Scope

### 1. Buyer form
- "Contact dealer" opens a form (a sheet on mobile, built with Feature 03 §3's `useApiForm`):

  | Field | Rule |
  |---|---|
  | name | required, ≤ 80 chars, control characters and CR/LF stripped |
  | email | required, valid address, not on the bundled disposable-domain list |
  | phone | optional, UK number normalised to E.164 |
  | message | 10–2,000 chars, prefilled "Hi, is the {title} still available?", at most 2 URLs |
  | intent | quick picks: Is it available? / Book a test drive / Part exchange question / Finance question\* |
- Consent text with a link to the privacy notice, stating that the dealer receives these details
- Works signed out. Signed-in consumers get name and email prefilled, and the enquiry appears in their account under "My enquiries" (§7).
- Confirmation screen, plus a confirmation email to the buyer (§5)

\* *Finance question* only passes the question to the dealer. **The platform itself
provides no finance information, quotes or introductions** (FCA scope, report §6).

### 2. Submission pipeline — `POST /listings/{id}/leads`
1. **Form token:** opening the form fetches `GET /listings/{id}/lead-form-token`, an HMAC-signed `{listing_id, issued_at}` valid from **3 s to 2 h** after issue. Rejected: a client-side timer only, which any script skips.
2. **Spam checks**, failing silently: honeypot field filled, token missing, too fast or expired. These return the **same 202 as a real submission**, create nothing, and increment `leads_submitted_total{outcome="spam"}`.
3. **Rate limits** (Feature 04 §5; policy table in Feature 14 §6): 5 leads per IP per hour, 3 per email per listing per day, 20 per email per day. Over the limit → 429 with a friendly message (Feature 03 §3).
4. **Listing checks:**

   | Listing | Response |
   |---|---|
   | publicly visible (active/reserved) | accepted |
   | sold | 409 `listing_sold` with similar cars (`SearchBackend.similar`, Feature 07 §4) |
   | demo | 202 with `demo: true`; the UI shows "This is an example listing, so we couldn't send this to a dealer" plus similar real cars. **No lead, no email.** |
   | anything else (draft, archived, held, hidden, removed) | 404 |
5. Accepts `Idempotency-Key` (Feature 01 §5). A retried submit returns the stored response and creates nothing new.
6. In **one transaction:** insert the `Lead`, one `LeadDelivery` per recipient (§4), `stats.increment(listing_id, "leads")` (Feature 05 §6), and the email messages via `send_email` (Feature 04 §6). Sends happen only after commit.

### 3. Data model
| Table | Fields | Notes |
|---|---|---|
| `Lead` | `id` (UUIDv7), `listing_id` (FK cascade), `dealer_id` (denormalised for scoping), `user_id` (nullable), `name`, `email`, `phone`, `message`, `intent`, `status` (`new` / `contacted` / `closed_won` / `closed_lost`), `created_at`, `updated_at`, `anonymised_at` | `updated_at` is the optimistic-lock token for status edits. **No delivery or read columns** on this row. |
| `LeadDelivery` | `lead_id`, `recipient_user_id`, `email_message_id`, `status` (`pending` / `sent` / `delivered` / `bounced` / `failed`), `attempts`, `last_error`, `updated_at` | One per recipient. Written by workers and webhooks only. |
| `LeadReadState` | `lead_id`, `user_id`, `read_at` | Per member. Written when a member opens a lead. |
| `LeadNote` | `lead_id`, `author_user_id`, `body` (≤ 2,000), `created_at` | Append-only, dealer-internal |

Indexes: `Lead (dealer_id, created_at DESC, id)`, `Lead (dealer_id, status)`,
`Lead (listing_id)`, `Lead (user_id)`, `Lead (created_at) WHERE anonymised_at IS NULL`
(retention job), `LeadDelivery (status, updated_at) WHERE status = 'pending'` (sweeper).

### 4. Delivery: per-recipient outbox
- **Recipients:** every member of the dealer with `notify_new_leads = true` (Feature 04 §1). If that's nobody, the dealer's owners receive it anyway. A lead is never addressed to zero people.
- Each recipient's email is sent through `send_email(…, category="lead", idempotency_key=f"lead:{lead_id}:{user_id}")`. A retry, a sweeper re-dispatch or a redelivered task can't send a second copy.
- **Sweeper** (Feature 01 §7 pattern): a beat task every 5 minutes re-dispatches `LeadDelivery` rows still `pending` after 5 minutes. After 5 attempts (backoff spread over about an hour), the row becomes `failed`.
- Resend webhooks (Feature 04 §6) update `EmailMessage`. A hook mirrors bounces and deliveries onto `LeadDelivery`.
- **Lead delivery health** is derived: `delivery_failed` when every recipient's delivery is `failed` or `bounced`. It's shown as a flag in the dealer inbox ("We couldn't email this lead to your team — check your email settings"), and in Feature 14's lead-delivery-failures view.
- Target: p95 < 60 s from submit to provider acceptance.
- Delivery writes **never touch `Lead`**, so a dealer changing a lead's status is never interrupted by a 409 caused by a worker (the Yaqlo lesson, Feature 01 §5).

### 5. Emails
- **New lead (to dealer members):** `From: "{buyer name} via {site}" <leads@notify.<domain>>`, `Reply-To: {buyer email}`. Replying goes to the buyer directly. Contains the buyer's details, message, intent, the car summary and a link to the lead. Header values are built by the email library from validated, CR/LF-stripped inputs, never by string concatenation.
- **Confirmation (to the buyer):** the car summary and the dealer's contact details. It **does not include the buyer's message**. The email address isn't verified, so echoing free text would let anyone use our domain to send arbitrary text to any address. At most 3 confirmations per recipient address per day; beyond that the lead is still delivered to the dealer, without a confirmation.
- Templates follow Feature 04 §6 (HTML + text, snapshot-tested, no tracking pixels)

### 6. Dealer inbox (`/dealer/leads`)
- List: newest first, unread in bold (unread = no `LeadReadState` row for the current user), filter by status or listing, delivery flag. Page size 25, **≤ 4 queries** per page (`assert_max_queries`).
- Nav badge: `GET /dealer/leads/unread-count` (index-backed, cached 30 s per user, < 50 ms)
- Lead detail: buyer details, the car with its current status, message, `mailto:` / `tel:` actions, a status dropdown (`PATCH` with `updated_at`; 409 `stale_update` handled by Feature 03 §3), internal notes. Opening it upserts `LeadReadState`.
- All endpoints are dealer-scoped (`dealer_scoped` / `get_dealer_owned_or_404`, Feature 04 §9): `GET /dealer/leads`, `GET /dealer/leads/unread-count`, `GET/PATCH /dealer/leads/{id}`, `POST /dealer/leads/{id}/notes`
- Stock table counters: leads per listing via `ListingStats` (Feature 05 §6)

### 7. Consumer "My enquiries"
- `GET /me/leads` (`current_consumer`, Feature 09 §1): the user's own leads with the car's current state (Feature 09 §4's card states). Paginated, `private, no-store`.

### 8. Call clicks
- Phone reveals are handled by Feature 08 §6, which increments `ListingStats.call_clicks`. **Call clicks are counters, not `Lead` rows.** There is no personal data, and the inbox lists only form enquiries, so no inbox code has to cope with leads that have no name or email.

### 9. Privacy and retention
- **Lawful basis:** taking steps at the buyer's request. The privacy notice and dealer terms (Feature 15) state that the dealer receives the buyer's details and handles them as their own controller.
- **Personal-data handler** (Feature 09 §6): on erasure, `name` → "Deleted user", `email` and `phone` → null, `user_id` → null. The message stays for the dealer's records. On export, all of the user's leads.
- **Retention** *(moved here from Feature 15)*: leads older than 24 months are anonymised (`name`, `email`, `phone` cleared, `message` replaced with "[removed after 24 months]", `anonymised_at` set) by a nightly batch job (1,000 per batch, idempotent). The test creates leads **through the real submission path** (Yaqlo's retention lesson).
- Admins see delivery health and metadata. Access to lead content is logged (Feature 14).

### 10. Observability
- Metrics: `leads_submitted_total{outcome: accepted | spam | rate_limited | demo | sold}`, `lead_delivery_seconds` (submit → provider accepted), `lead_delivery_failed_total`
- Alert (configured in Feature 15): any `LeadDelivery` still `pending` after 15 minutes

---

## Key Decisions

**Email relay via `Reply-To`, not an in-app chat.** Dealers already live in their
inbox and DMS. A buyer-dealer chat (as in Yaqlo's job chat) is real complexity
(polling, read state, notifications) with an unclear benefit at MVP stage. The inbox
gives tracking, and email gives the conversation.

**Delivery and read state live in their own tables.** Rejected: `Lead.delivery_status`
and `Lead.first_viewed_at`. Both are written by someone other than the person editing
the lead (a worker, a webhook, another team member opening it), and each write would
bump `updated_at`. Yaqlo's chat panel did exactly this with read receipts, and it was
the main cause of spurious "someone else changed this" conflicts in production.

**Per-recipient delivery, not per-lead.** One member's mailbox bouncing must not hide
whether the others received the lead, and "delivered to someone" is the fact a dealer
needs. It also gives each recipient its own idempotency key.

**A lead is never lost silently.** It uses Feature 04 §6's email service and Feature
01 §7's outbox: the delivery rows are written with the lead in one transaction, sent
after commit, swept if stuck, and flagged if they finally fail. A lead lost silently is
the worst possible failure for dealer trust.

**The buyer confirmation doesn't echo the message.** It's a classic abuse of contact
forms: put a victim's address in the email field and spam in the message, and the
site's own domain delivers it. Leaving the text out costs the buyer nothing.

**Spam defence without CAPTCHA friction:** a honeypot field, a server-signed minimum
form-fill time, rate limits, disposable-email domain blocking, and link-count limits.
Silent acceptance gives bots no signal to adapt to. A CAPTCHA (e.g. Cloudflare
Turnstile) is added only if these prove insufficient.

**Leads on demo listings never reach a dealer.** The buyer sees an explanation plus
similar real cars.

## Acceptance Criteria

**Submission**
- A signed-out buyer submits an enquiry. The dealer's members receive the email within 60 s, and the lead appears in the inbox as `new`.
- Retrying a submit with the same `Idempotency-Key` creates one lead and one email per recipient
- A filled honeypot, a missing token, or a token used within 3 s returns the same 202 as a real submit, and creates no lead and no email
- The 6th lead from one IP in an hour, and the 4th from one email on one listing in a day, return 429 with a friendly message
- An enquiry on a sold listing returns 409 `listing_sold` with similar cars. A reserved listing is accepted. A held, hidden, removed or draft listing returns 404. A demo listing creates no lead and sends no email.
- A message with 3 URLs, or an email on a disposable domain, returns 422 on that field
- A buyer name containing CR/LF produces a well-formed `From` and `Reply-To` header with no injected header (raw MIME assertion)

**Delivery**
- If the submit transaction rolls back, no `Lead`, no `LeadDelivery` and no email exist
- A worker killed after commit but before sending: the sweeper delivers within 10 minutes, exactly one email per recipient
- After retries are exhausted, `LeadDelivery` is `failed`, and the lead shows the delivery flag to the dealer and in the admin console
- A bounce webhook for one recipient marks only that recipient's delivery `bounced`
- When every member has opted out of lead emails, the owners still receive them
- Replying to the lead email goes to the buyer's address
- The buyer confirmation contains no message text. The 4th confirmation to the same address in a day is not sent, and the lead is still delivered to the dealer.

**Inbox**
- Opening a lead writes `LeadReadState`, leaves `Lead.updated_at` unchanged, and leaves it unread for other members
- A delivery-status update by a worker doesn't cause a 409 on a dealer's status change made with the earlier token
- A status `PATCH` with a stale `updated_at` returns 409 `stale_update`
- Dealer B cannot list, view or update dealer A's leads (404, Feature 01 §14 harness)
- An inbox page runs in ≤ 4 queries. The unread-count endpoint responds in under 50 ms.
- "My enquiries" shows only the signed-in user's leads

**Privacy & counters**
- After the buyer deletes their account, the lead remains for the dealer as "Deleted user", with email and phone empty
- Leads older than 24 months (created through the real submit path) are anonymised by the retention job. Re-running it changes nothing.
- `GET /me/export` includes the user's leads
- A phone reveal increments `call_clicks` and creates no `Lead` row
- `leads_submitted_total`, `lead_delivery_seconds` and `lead_delivery_failed_total` appear on `/metrics`

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: delivery state in `LeadDelivery` and read state in `LeadReadState`, off the locked row (§3, §4, §6)
- P0: per-recipient outbox with idempotency keys, sweeper and failure flag (§4)
- P0: buyer confirmation without echoed text, plus a per-address cap (§5)
- P0: header-injection-safe email construction (§5)
- P0: server-signed form-fill timing (§2)
- P1: listing-state response table, including moderation states (§2)
- P1: never-zero recipients (§4)
- P1: call clicks as counters only, reconciled with Feature 08 §6 (§8)
- P1: erasure handler and 24-month anonymisation using real-path fixtures (§9)
- P1: inbox query budget and a cached unread count (§6)
- P1: field validation table (§1)
- P1: metrics and the stuck-delivery alert (§10)

**Ownership moves:** lead retention (24-month anonymisation) moves here from Feature 15
(§9). The phone-reveal endpoint is owned by Feature 08 §6, replacing this doc's
earlier `call-click` endpoint.

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| In-app buyer–dealer messaging | Dealers report losing threads in email, or Phase 2 billing needs on-platform response-time metrics |
| CAPTCHA (Cloudflare Turnstile) on the lead form | Spam leads exceed ~2% of accepted leads, or a spam wave gets past the existing checks |
| Lead routing rules (per-listing assignee, round robin) | Dealers with more than 5 staff ask for it |
| Dealer CRM/DMS lead export (ADF/XML, webhooks) | First dealer with a CRM integration requirement (Phase 2) |
| Email relay with masked addresses (`lead-123@…`) | Buyers complain about dealer follow-up spam, or response tracking is needed |
| Response-time analytics per dealer | Phase 2 dealer analytics |

**Scale traps to avoid:** a real-time chat system; a separate notification
microservice for lead emails.
