# Feature 11 — Saved Searches & Email Alerts

**Status:** Not Started
**Priority:** Must-Have (the main re-engagement loop)
**Milestone:** M4 Engagement
**Effort:** 8h optimistic / 17h realistic / 26h pessimistic
*(raised from 6/12/18h after a scale review: a race-free watermark with per-search
de-duplication, chunked fan-out with a throughput budget, scanner-safe unsubscribe,
complaint/bounce handling, and erasure/retention are specified here. See "Scale
review" at the end.)*
**Depends on:** 04, 07, 09

## Description

A buyer saves a search, and we email them when new matching cars are listed or when
a saved car drops in price. Report §3 lists "saved searches + alerts" as a confirmed
feature and the "alerting/notification pipeline (saved search → email/push)" as a
notable technical feature. Car buying is a weeks-long process, so this loop is what
turns one visit into repeat visits. It is also our highest-volume email stream, so it
must protect the sending domain's reputation that lead and auth emails depend on.

---

## Scope

### 1. Saving a search
- "Save this search" on the results page stores the **normalised `SearchFilters`** (the contract owned by Feature 07 §3) with its `params_version` and `canonical_key`. The name is generated ("Ford Fiesta, under £10,000, within 25 miles of M1") and editable (≤ 80 chars).
- **Saving the same filters twice** (unique `(user_id, canonical_key)`) returns the existing search instead of creating a duplicate
- A postcode in the filters is geocoded once at save time (Feature 04 §7), and the point is stored with the search, so the batch never geocodes
- Max **20** saved searches per user (409 `saved_search_limit_reached`). Consumer accounts only (`current_consumer`, Feature 09 §1).
- Frequency per search: **Instant** (hourly batch), **Daily** (default, 07:00 UK time), or **Off**

### 2. Data model
| Table | Fields | Notes |
|---|---|---|
| `SavedSearch` | `id`, `user_id`, `name`, `filters` (JSONB), `params_version`, `canonical_key`, `geo_point`, `frequency`, `last_run_at`, `paused_reason` (null / `complaint` / `bounced`), `created_at`, `updated_at` | `last_run_at` is the watermark, written only by the alert job |
| `AlertDelivery` | `id`, `user_id`, `run_id`, `frequency`, `email_message_id`, `status`, `created_at` | One per email sent to a user per run |
| `AlertSentListing` | `saved_search_id`, `listing_id`, `alert_delivery_id`, `sent_at` | Unique `(saved_search_id, listing_id)`: a listing is alerted at most once per search, ever |
| `PriceDropNotice` | `user_id`, `listing_id`, `notified_price_pence`, `notified_at` | The last price we told this user about |

All `user_id` and `listing_id` FKs cascade (Feature 02 §9). `SavedSearch` is edited by
the user (rename, frequency) **without** an optimistic lock, so the alert job writing
`last_run_at` can never cause a 409. The user edits and the job write different
columns of a row where last-writer-wins per column is correct.

### 3. Matching job
- **Schedule** (single beat, Feature 01 §7, with the beat timezone set to `Europe/London`): Instant at :05 past every hour, Daily at 07:00 UK time. The 07:00 job runs at local time on both sides of a clock change.
- **Fan-out:** `plan_alert_run(frequency)` records the `run_started_at`, selects due users (verified email, alerts enabled, not paused, address not suppressed for `alert`, Feature 04 §6) in chunks of 200, and dispatches `process_alert_chunk(user_ids, run_id)` tasks on the `default` queue. Matching never runs on the `notifications` queue, so it can't delay lead emails (Feature 01 §7).
- **Per user, in one transaction:**
  1. For each due search: `SearchBackend.match_ids(filters, listed_after = last_run_at − 15 min, limit = 50)` (Feature 07 §4, the **same backend as the search page**), minus listings already in `AlertSentListing` for that search, keeping the first 10 (with "+N more" linking to the search). Demo listings are excluded by `match_ids`' visibility rules and an explicit `is_demo = false`.
  2. Daily runs also collect price drops (§4)
  3. If anything matched: insert `AlertSentListing` and `PriceDropNotice` rows, one `AlertDelivery`, and `send_email(…, category="alert", idempotency_key=f"alert:{alert_delivery_id}")` (Feature 04 §6)
  4. Set each processed search's `last_run_at = run_started_at` (the run's start time, not the commit time)
- **Why the overlap and the dedupe table:** a listing can get `listed_at = 06:59:59` in a transaction that commits at 07:00:02, after the run's query has taken its snapshot. With a plain `listed_at > last_run_at` filter, the next run would skip it forever. The 15-minute overlap re-reads that window, and `AlertSentListing` guarantees nobody is told about the same car twice.
- **Crash safety:** a crash before commit records nothing, and the chunk task retries. A crash after commit but before sending leaves a `queued` `EmailMessage`, which Feature 04 §6's sweeper re-dispatches. The idempotency key prevents a second copy.
- **Throughput budget:** 10,000 saved searches matched in under 15 minutes (~20 ms per `match_ids` on the 50k perf profile, 2 `default` workers). Sending is rate-limited at the provider's limit (Resend's per-second limit and batch API: to verify; start at 2/s). The Daily run's emails should be sent by 07:45.

### 4. Price-drop alerts (saved cars)
- Source: `ListingPriceChange` (Feature 05 §3) for listings in users' `SavedListing` (Feature 09 §4), only when price-drop alerts are enabled (Feature 09 §5) and the listing is publicly visible and not demo
- **Rule:** notify when the current price is at least **£100 and 1%** below the last price this user was told about (`PriceDropNotice.notified_price_pence`, or `price_at_save_pence` the first time), and no more than once per listing per user every **7 days**. A dealer cutting £50 a day doesn't produce a daily email, and each email reports a meaningful drop.
- Included in that user's next Daily email (bundled with their search matches)

### 5. Email content
- One email per user per run, bundling all due searches (and price drops on Daily), so users don't get a flood
- Car cards: `card` image variant (Feature 06 §6, immutable URL), title, price, key facts, distance from the search's postcode; absolute links to the detail page with UTM tags
- Plain-text alternative part. **No tracking pixels or per-recipient click tracking.**
- Built on Feature 04 §6's templates, sent from `notify.<domain>`

### 6. Unsubscribe and sender reputation
- `List-Unsubscribe` (an HTTPS URL plus a `mailto:`) and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058) on every alert email. Required by Gmail/Yahoo bulk-sender rules, and PECR-friendly.
- Unsubscribe tokens: `HMAC(secret, user_id | target | purpose)`, where `target` is a saved-search id or `all`. No expiry, so links in old emails keep working. Signed-out access.
- **`GET /alerts/unsubscribe?token=…` never changes state.** It shows a page naming the search, with an "Unsubscribe" button. Rejected: unsubscribing on GET, because corporate mail scanners and link previewers follow every link in an email and would unsubscribe people who never clicked. The **one-click `POST`** (from the button, or from the mail client via `List-Unsubscribe-Post`) is what changes state.
- **Complaints** ("marked as spam") arrive through Feature 04 §6's `email_complaint` hook and switch off **all** that user's alerts (`paused_reason = complaint`). A hard bounce suppresses the address (Feature 04 §6) and pauses its searches (`bounced`). The account page explains why and how to resume.
- Reputation targets watched in Feature 15's alerts: spam-complaint rate < 0.1% and bounce rate < 2% of alert sends

### 7. Lifecycle, privacy and retention
- Stored filters are upgraded on read through Feature 07 §3's version upgraders. A search that references an inactive make or model keeps working (Feature 02 §1).
- **Personal-data handler** (Feature 09 §6): erasure deletes `SavedSearch`, `AlertDelivery`, `AlertSentListing` and `PriceDropNotice` rows. Export includes the saved searches (name, filters, frequency) and the last 90 days of alert deliveries.
- **Retention** *(moved here from Feature 15)*: `AlertDelivery` and `AlertSentListing` rows older than 90 days are deleted nightly in batches. Older listings can't re-match anyway, because the watermark has moved past them. The retention test builds its rows through a real alert run, not hand-set fixtures.

### 8. UI
- `/account/searches`: list, rename, change frequency, "view results" (opens `/cars?…` from the stored filters), delete, and a paused-state banner with a resume action
- Email preferences in account settings (Feature 09 §5)
- The unsubscribe confirmation page and an "unsubscribed" page that offers a link to manage alerts

### 9. Observability
- Metrics: `alert_run_duration_seconds{frequency}`, `alerts_sent_total{frequency}`, `alert_run_last_success_timestamp{frequency}` (Feature 15 alerts if Daily hasn't succeeded within 26 h, or Instant within 3 h), `alert_unsubscribes_total`
- One summary log line per run: users processed, searches matched, emails queued, duration

---

## Key Decisions

**One backend or nothing.** If the alert matcher had its own filter logic, it would
drift from the search page, and users would get alerts for cars the site won't show
them (or the reverse). Yaqlo's CLAUDE.md documents exactly this class of
silent-composition bug. Matching goes through `SearchBackend.match_ids` (Feature 07
§4), and the contract suite asserts identical sets.

**`params` is versioned** using Feature 07 §3's `params_version` and upgrade functions
(owned there). Filters will change (a new fuel type, a renamed body type). A saved
search must never silently match nothing after a deploy.

**Overlap window plus de-duplication, not an exact watermark.** Rejected: `listed_at >
last_run_at` alone. Commit order isn't timestamp order, so some listings would fall
between runs and never be alerted, with no error anywhere. Re-reading a 15-minute
window and recording what was sent makes the job correct under concurrency and
retries.

**Unsubscribe never happens on GET.** Link scanners would unsubscribe real users
silently. The one-click POST standard exists for exactly this.

**Matching runs on `default`; sending runs on `notifications`.** A slow alert run
should make alerts late, not lead emails late.

**No push notifications in the MVP.** Web push has poor iOS uptake and adds
permission-prompt UX. Email first. Push arrives with native apps (Phase 2).

**Demo listings never trigger alerts.** Alerting a user about an example car they
can't buy would destroy trust in the whole alert channel.

## Acceptance Criteria

**Saving**
- Saving, renaming, changing frequency and deleting all round-trip correctly. The 21st save returns 409 `saved_search_limit_reached`.
- Saving the same filters twice (in a different parameter order) returns the existing search and creates no duplicate
- A user with an unverified email can save searches but receives no alert emails

**Matching**
- A listing that becomes visible after `last_run_at` and matches appears in the next run. A non-matching or demo listing never does.
- A listing held for review at publish and released later is alerted in the run after its release (`listed_at` watermark)
- A listing whose transaction commits just after a run's query, with `listed_at` before the run started, is included in the next run exactly once
- For any random `SearchFilters`, the matcher's id set (minus the time filter) equals the search endpoint's (Feature 07 contract suite)
- Two due searches for one user produce one email. A Daily run with search matches and a price drop produces one email.
- A worker killed after selection but before commit: the next attempt sends exactly one email. A worker killed after commit but before sending: Feature 04's sweeper sends exactly one email.
- The Daily job fires at 07:00 Europe/London on the days before and after both clock changes
- A stored search at an older `params_version` still matches after an upgrade (Feature 07 fixtures)
- 10,000 saved searches complete matching within 15 minutes on staging with the 50k perf profile

**Price drops**
- A drop of at least £100 and at least 1% on a saved car appears in the next Daily email. A £50 drop doesn't.
- A second drop within 7 days of a notification produces no email. A further qualifying drop after 7 days does, measured from the last notified price.
- With price-drop alerts switched off, no price-drop content is sent

**Unsubscribe & reputation**
- `GET` on an unsubscribe link changes nothing and shows a confirmation page. The `POST` and the `List-Unsubscribe-Post` one-click request disable only the intended search (or all, for `all`), without signing in.
- A tampered token returns 400 and changes nothing
- A complaint webhook pauses all of that user's alerts. A hard bounce pauses their searches, and the next run skips them.
- Every alert email has `List-Unsubscribe`, `List-Unsubscribe-Post` and a plain-text part, and no tracking pixel

**Privacy & observability**
- Erasing a user deletes their saved searches and alert logs. `GET /me/export` includes their saved searches.
- Alert logs older than 90 days (created by a real alert run in the test) are deleted by the retention job
- `alert_run_last_success_timestamp` is updated for each frequency after a successful run

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: race-free matching with a 15-minute overlap, `AlertSentListing` de-duplication and the watermark set to run start (§3)
- P0: crash safety via the email outbox sweeper and idempotency keys (§3; knock-on to Feature 04 §6)
- P0: unsubscribe that never changes state on GET, plus RFC 8058 one-click (§6)
- P0: complaint and bounce handling that pauses alerts (§6)
- P0: erasure handler and 90-day retention (moved from Feature 15) (§7)
- P1: chunked fan-out on `default`, with a throughput and send-rate budget (§3)
- P1: DST-safe 07:00 schedule (§3)
- P1: price-drop repeat rule against the last notified price (§4)
- P1: canonical-key de-duplication of saved searches (§1)
- P1: geocode once at save time (§1)
- P1: no lock token on `SavedSearch` (§2)
- P1: run heartbeat and send metrics (§9)

**Ownership moves:** `SearchParams` versioning moved to Feature 07 §3 (cited here).
Alert-log retention moves here from Feature 15 (§7).

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| Web/native push notifications | Native apps (Phase 2 item 10) |
| Provider batch-send API | More than 5,000 alert emails per Daily run, or the run's send phase exceeds 45 minutes |
| Auto-pausing alerts for inactive users (no visit in 6 months) | Alert complaint rate approaches 0.1%, or the list grows mostly inactive |
| Real-time ("as soon as listed") alerts | Users ask for faster than hourly, and the hourly run is comfortably within budget |
| Separate sending subdomain for alerts | See Feature 04's P2: Gmail/Yahoo bulk thresholds, or alerts affecting auth deliverability |
| Per-search alert analytics (opens/clicks) | A consent-compliant measurement approach is agreed (no tracking pixels in the MVP) |

**Scale traps to avoid:** a streaming percolator (matching each new listing against
every saved search in real time) at MVP volume; a separate notification platform.
