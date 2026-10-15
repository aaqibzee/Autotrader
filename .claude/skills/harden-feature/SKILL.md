---
name: harden-feature
description: Review one features/NN-*.md design doc the way a large-scale app would be reviewed (security, performance, testing, network, modern design conventions, scaling, observability, UX), rank every gap P0/P1/P2, then rewrite that doc to include the P0/P1 items with testable acceptance criteria, record P2s as deferred with revisit triggers, and fix knock-on references in FEATURES_PLAN.md and other feature docs. Use when the user says "harden feature N", "review feature N for scale", "find what's missing in feature N", "analyse feature N like a large-scale app", or "improve feature N with the review findings". Does NOT implement code, and does NOT write a brand-new feature doc.
---

# Harden feature

One skill, two phases, run back-to-back on **one** feature doc per run:

1. **Review**: find what the doc doesn't consider, judged against large-scale-app concerns, and rank each gap.
2. **Apply**: rewrite the doc so the P0/P1 gaps become concrete scope plus acceptance criteria, defer the P2s with explicit triggers, and keep the rest of the plan consistent.

The point is **not** to turn an MVP into a 600-system platform. The point is to catch
decisions that are **cheap now and expensive to retrofit** once later features depend on
them, and to state honestly what is deliberately deferred.

## Examples

```
/harden-feature 1                 # review + apply on features/01-*.md
/harden-feature search            # match by keyword in the filename/title
/harden-feature 7 review-only     # phase 1 only: findings in chat, no file edits
/harden-feature 5 apply           # phase 2 only, using findings already given earlier in this conversation
```

## 0. Locate inputs

- Target: `features/NN-*.md`, resolved by number or keyword (`Glob features/*.md`). If ambiguous, ask.
- Read **in full** before judging anything:
  - the target doc
  - `FEATURES_PLAN.md` (stack, milestones, effort table, risk table, Phase 2 backlog)
  - the source spec it was planned from (for Autotrader: `Documents/AutoTrader_UK_Technical_Due_Diligence.md`, or the PDF), including the sections the target cites
  - **every other feature doc that references the target, or that the target depends on** (`Grep` for `Feature NN`, `NN-`, and the feature's key nouns). Gaps often show up as a *later* doc assuming something this one never provides (e.g. Feature 14 rate-limits by IP while Feature 01 never defines how to read the real client IP behind Cloudflare).
- If the repo has code for this feature already, read it too and judge the doc against reality, not just against itself.

## 1. Phase 1 — Review

Walk the checklist below **against this feature's actual scope**. Skip questions that
genuinely don't apply, and don't pad. For each gap, record: what's missing, the concrete
failure it causes (a scenario, not "best practice"), and a recommended fix.

### Checklist

**Architecture & network**
- Where does this run, and who calls it: browser, SSR server, worker, third party? Are origins, cookies and CORS consistent with that?
- Behind a CDN/proxy: is the real client IP, scheme and host derived safely (trusted only from known proxy ranges)?
- Outbound calls: timeouts, retries (idempotent only, with backoff + jitter), circuit breaker, a typed "unavailable" path that the UI handles?
- Inbound: body size limits, request IDs, graceful shutdown, liveness vs readiness?
- Is the contract between frontend and backend generated or checked in CI, or hand-copied?
- Is there one standard error shape with stable machine-readable codes?

**Data & scaling**
- Indexes for every filter/sort this feature introduces? Query plans at realistic volume (seeded, then ×10)?
- N+1 risks in list endpoints? Pagination caps?
- Writes that could bump an optimistic-lock token (`updated_at`) from background work?
- Transactions vs side effects: can a job or email fire before its row is committed, or after a rollback? Can a must-not-lose side effect be lost silently?
- Queue isolation: can heavy work starve latency-sensitive work?
- Shared infra limits: DB connections, Redis eviction policy, memory/CPU on a shared VM?
- Migrations: zero-downtime safe (expand/contract, concurrent indexes)? Reversible?
- Single-instance assumptions (schedulers, locks) that break with two processes?

**Security & privacy**
- AuthZ: is every resource scoped to its tenant/owner through one helper, and is cross-tenant access tested (404, not 403)?
- Rate limits and abuse paths (scraping, spam, enumeration, cost-amplification on paid APIs)?
- Personal data: collected, logged, retained, exported, erased? Are logs redacted?
- Secrets, least-privilege roles, bucket and object visibility, security headers/CSP?
- Supply chain: lockfiles, dependency audit, secret scanning?
- Regulatory surface the spec flags (e.g. UK GDPR, PECR, FCA, PCI)?

**Testing**
- Does every acceptance criterion map to an automatable test?
- Are fixtures built through the **real write path**, not hand-set columns?
- Tests for failure modes: third-party timeout, retry/dedupe, concurrent edits, rollback, worker crash?
- Network blocked in tests by default? Parallel-safe?
- Frontend unit + E2E coverage where there's UI? Performance budgets measurable?

**Observability & operations**
- Errors tracked (with request/trace id) from the day this ships?
- Metrics or alerts for this feature's failure signals (queue depth, delivery failures, breaker open)?
- Can an operator answer "why did X happen to user Y" from logs or an audit trail?
- Runbook or recovery path if it breaks? Backups/restore if it owns data?

**Modern design conventions**
- IDs, pagination, idempotency keys, time zones (store UTC, display local), soft delete, versioned stored payloads, feature flags. Consistent with the rest of the plan?
- Module boundaries: does it reach into another module's models?
- Swappable backends where the spec says the vendor/engine will change?

**User experience**
- Loading / empty / error / offline / permission-denied / not-found states designed?
- Mobile-first, accessibility (keyboard, screen reader, contrast), locale formatting?
- What does the user see when a dependency is down? Never a raw 500 or an endless spinner.
- Honesty: does the UI ever show a fabricated or misleading value when data is missing?

### Ranking

| Rank | Rule |
|---|---|
| **P0** | Must be in *this* feature. Retrofitting later means touching many features or data already in production, **or** a later doc already assumes it exists. |
| **P1** | Should be in this feature because it's cheap now, but could be added later without wide rework. |
| **P2** | Real, but not justified at MVP scale. Record it with a **concrete trigger** for when to revisit (a metric threshold, an event, a phase). |

Also flag, separately:
- **Ownership moves**: a concern another feature currently owns but that belongs here (or the reverse). For example, error tracking or dependency audits sitting in a launch feature when every earlier feature needs them.
- **Scale traps to avoid**: things the source spec's real platform has that the MVP should explicitly *not* build (microservices, Kafka, Kubernetes, multi-region…), so nobody adds them by reflex.

### Present the findings

In chat, as plain text (no Artifact, no file), grouped by category, each as a row:
`# | Gap | Why it matters (concrete failure) | Pri`. End with the effort impact (the old
estimate and a realistic new one), plus the ownership moves.

- `review-only` → stop here and offer to apply.
- Otherwise continue straight to Phase 2 in the same run. **Exception:** if any finding
  changes a decision the user explicitly made earlier (stack, scope, a clarifying-question
  default), stop and ask before applying that one item. Apply the rest.

## 2. Phase 2 — Apply

### 2a. Rewrite the target doc

Keep the repo's doc shape (`Status / Priority / Milestone / Effort / Depends on`,
then `Description`, `Scope`, `Key Decisions`, `Acceptance Criteria`) and strengthen it:

- **Scope → numbered subsections** (`### 1. …`, `### 2. …`) so other docs can cite `Feature NN §k`.
- Every P0/P1 becomes **concrete scope**: names, numbers, defaults and limits, not "add rate limiting". Write "120 req/min per `get_client_ip()`, 429 with `Retry-After`". Use tables for budgets (connections, memory, latency, queues).
- **Key Decisions**: add an entry only for non-obvious choices, stating the alternative rejected and the failure it prevents. Keep any existing decisions that still hold.
- **Acceptance Criteria**: every added item gets **at least one testable check**. Group them by area once there are more than ~8. Prefer checks that prove the failure mode can't happen ("a rolled-back transaction sends no task") over checks that only prove the feature exists.
- **Effort**: update optimistic/realistic/pessimistic, and say in one line why it changed.
- Append a closing section **"Scale review — what was added, and what was deliberately deferred"**:
  - the added P0/P1 items, each with the `§` where it now lives
  - a **Deferred (P2)** table: `Item | Trigger to revisit`
  - the scale traps to avoid, if any were found

Rewrite the whole file (Write) rather than patching dozens of fragments. Preserve every
existing correct detail, and don't drop scope silently. If something is removed or moved,
it must show up in the knock-on edits below.

### 2b. Knock-on edits elsewhere

- **FEATURES_PLAN.md**: update this feature's effort cell, the **total build** line and range, the overall budget line (build + QA), and milestone text if it changed. If the change is large, add one bullet under "Why this order" explaining it.
- **Ownership moves**: in the doc that used to own the concern, replace the old item with a pointer ("set up in Feature 01 §12; here, configure production alert rules") so nothing is defined twice or orphaned.
- **References**: in docs that depend on what this feature now provides, point at the new section (e.g. rate limits keyed by `get_client_ip()` from Feature 01 §3).
- Use exact-match replacements, and assert each old string exists before replacing. If one doesn't match, read that file and fix it by hand. Never skip it silently.

### 2c. Verify before reporting

- Every `features/…md` link in FEATURES_PLAN.md resolves to a file.
- The effort table's realistic hours sum to the stated total.
- `Grep` all docs for anything now stale: the old effort figure, a concern described as owned by two features, a section reference that no longer exists.
- Re-read the rewritten doc once, end to end, for internal contradictions (e.g. a timeout in one section differing from another, a decision contradicting a criterion).

## 3. Report

Keep it short, in chat:
- a table of what the doc now specifies, by area, with `§` references
- the acceptance-criteria count, before → after
- the effort change, plus the new plan total
- every other file touched and what changed in it
- the deferred P2s (names only), plus any item held back because it needs the user's decision

Don't commit or push unless asked. Autotrader isn't a git repo yet. If it is by the time
this runs, follow the user's standing preference of committing directly to the working
branch, and only when asked.

## Lessons to check against (from the sibling apps)

These failures already happened in Yaqlo/Suretly. Every review should check whether the
target feature could repeat them:
- **Optimistic-lock token bumped by background writes** (counters, read receipts, retries rewriting the row). Fix: separate stats tables, or a guarded update.
- **Reader/writer assumption mismatch**: a query filter assumes a column the only real writer never populates, masked by a fixture that set it by hand. Fix: build fixtures through the real write path, and test against the writer.
- **Tests leaking real `.delay()` calls** into a local broker. Fix: eager or stubbed tasks in unit tests, plus a dispatch helper.
- **Tests hitting the network.** Fix: block sockets by default.
- **`localhost` resolving to IPv6** and hanging pytest. Fix: `127.0.0.1` in DB URLs.
- **Leaked Playwright contexts** causing flaky stuck pages. Fix: use the fixture `page`, or close manual contexts.
- **Prod migrations not applied on redeploy.** Fix: the deploy script checks `alembic current` against heads.
- **A memory-constrained shared VM** running several apps. Fix: per-service resource limits, and isolate CPU-heavy queues.
