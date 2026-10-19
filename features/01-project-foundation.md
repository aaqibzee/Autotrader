# Feature 01 — Project Foundation

**Status:** Done (2026-10-19). See "Implementation notes" at the end for deviations and what still needs a real VM/CI run.
**Priority:** Must-Have (prerequisite for everything else)
**Milestone:** M1 Foundation
**Effort:** 8h optimistic / 16h realistic / 24h pessimistic
*(raised from report §4's 3/6/10h "Scaffolding/setup" after a scale review. The
extra hours cover conventions that every later feature would otherwise rebuild
slightly differently. See "Scale review" at the end.)*
**Depends on:** none

## Description

The repo, tooling, environments and **cross-cutting conventions** every later
feature builds on: a FastAPI modular monolith, a Next.js web app,
Postgres/Redis/S3-compatible storage in docker-compose, CI, observability, and the shared building
blocks (HTTP client, error format, job dispatch, test factories) that features 02–15
assume exist. No product behaviour ships here. This feature exists so that features
02–15 never have to make a structural decision. A decision that is cheap now and
expensive once 14 features depend on it belongs here.

---

## Scope

### 1. Repo layout
```
Autotrader/
  backend/                FastAPI app (uv-managed, uv.lock committed)
    app/
      api/v1/endpoints/   one module per domain (health first)
      core/               config, celery_app, security, logging, http_client,
                          errors, rate_limit, client_ip, feature_flags, telemetry
      db/                 base (TimestampMixin, naming_convention), sync + async sessions
      models/             SQLAlchemy models
      services/           business logic shared by endpoints and tasks
      tasks/              Celery tasks
      modules/            domain packages: dealers, listings, search, leads,
                          alerts, valuations, admin (grow as features land)
    alembic/
    tests/                (factories/, helpers/, contract/)
  web/                    Next.js 15 App Router + TypeScript (strict) + Tailwind
    lib/api/              generated OpenAPI types + typed fetch client
    lib/format/           en-GB formatting helpers
    e2e/                  Playwright
  ops/                    docker/, k6/, runbooks/
  Documents/              due-diligence report + future specs
  features/               these design docs
  docker-compose.yml      postgres:16, redis:7 (x2 logical roles), seaweedfs (S3)
  .env.example
  .pre-commit-config.yaml
```

### 2. Environments & config
- Three environments: **local**, **staging**, **production**, selected by `ENVIRONMENT`. Staging may share the production VM but has its own database, Redis DB indexes, bucket, subdomain and `.env`.
- pydantic-settings loads the repo-root `.env` **by absolute path** (uvicorn, celery and pytest all have different working directories, a lesson learned in Yaqlo)
- **The app refuses to boot outside `local`** if any secret still holds its `.env.example` placeholder (`SECRET_KEY`, S3 keys, DB password)
- Production secrets live only in the server-side `.env` (mode 600, owned by the service user) and are never committed. The `.env.example` lists every key with a comment. Rotation procedure documented in `ops/runbooks/secrets.md`.
- **Feature flags:** a minimal `FeatureFlag` table plus a settings override (`FLAG_<NAME>=on`), read through `flags.is_enabled(name)`, cached for 30 s. Feature 12's "Value my car" flag is the first user. No third-party service.

### 3. Network topology (decided here, relied on by 04, 06, 08, 13, 14)
```
Browser ──HTTPS──▶ Cloudflare ──▶ VM: Caddy/nginx
                                     ├─ /            → Next.js (SSR)
                                     ├─ /api/*       → FastAPI
                                     └─ img.<domain> → object storage (CDN-cached, Feature 06)
Next.js SSR ──http://127.0.0.1:8000──▶ FastAPI   (internal, never via Cloudflare)
```
- **Same origin for web and API** (`/api/*` on the main domain), not an `api.` subdomain. Session cookies are first-party, `SameSite=Lax`, `Secure`, `HttpOnly`, with no `Domain` attribute. There are **no CORS rules in production**, because there are no cross-origin calls. (CORS is enabled only for local dev ports.)
- **SSR → API calls** go to the internal URL and forward the incoming request's `Cookie`, `X-Request-ID` and real client IP headers (see below). They have a 3 s timeout, and failures render the page's error state instead of hanging.
- **Real client IP:** `core/client_ip.py` trusts `CF-Connecting-IP` **only** when the TCP peer is the local reverse proxy *and* the proxy received the request from a Cloudflare IP range (ranges are refreshed weekly by a beat task, with a bundled fallback list). Otherwise it uses the direct peer. **Every** rate limiter, audit log and view-dedupe (features 04, 08, 10, 12, 14) uses `get_client_ip(request)`, never `request.client.host`.
- The origin VM accepts HTTP(S) only from Cloudflare IP ranges (firewall rule), so attackers can't bypass Cloudflare by hitting the IP directly.

### 4. Backend application skeleton
- FastAPI app with an `/api/v1` router. URL versioning policy: additive changes stay in v1, and breaking changes require v2 alongside v1 for at least one release.
- **Health endpoints split:**
  - `GET /api/v1/health/live`: process is up, no dependency checks (used by the process supervisor for restarts)
  - `GET /api/v1/health/ready`: DB `SELECT 1`, both Redis roles, storage bucket reachable, Alembic revision = head. Returns 503 naming the failing dependency (used by uptime checks and the deploy script).
- **Graceful shutdown:** uvicorn `--timeout-graceful-shutdown 20`, Celery warm shutdown, and the deploy script waits for `/ready` before switching traffic
- **Baseline middleware, in order:** request-ID (accept an inbound `X-Request-ID` or generate a UUIDv7) → client IP resolution → trusted-host check → body size limit (1 MB JSON. Image uploads bypass the API via presigned URLs, Feature 06) → security headers (HSTS, `X-Content-Type-Options`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`; CSP is set on the web side) → Origin/Referer check on state-changing cookie requests (CSRF defence-in-depth, used by Feature 04)
- **Threadpool:** sync endpoints run in AnyIO's threadpool. Its size is explicitly set (`THREADPOOL_SIZE`, default 40) and matched to the DB pool size (see §6), so request threads never queue waiting for a connection.

### 5. API conventions
- **Error format: RFC 9457 Problem Details** for every non-2xx response:
  `{"type", "title", "status", "detail", "code", "request_id", "errors"?: [{field, code, message}]}`.
  `code` is a stable machine-readable string (`dealer_not_approved`, `page_limit_exceeded`, `stale_update`). It's registered in `core/errors.py` as an enum so codes are discoverable and never typo'd. Unhandled exceptions return a generic 500 problem with the request id, never a stack trace.
- **IDs:** UUIDv7 primary keys for all new tables. They sort by time, which keeps B-tree inserts local on large tables like `Listing` and `Lead`, and don't leak counts like sequential ints would.
- **Pagination:** list endpoints return `{items, page, page_size, total}`. High-volume feeds that are only appended to (alerts, admin logs) use cursor pagination (`next_cursor`). `page_size` is capped at 100.
- **Idempotency:** POSTs with side effects that a client might retry (lead submit, publish, invite) accept an `Idempotency-Key` header. The response is stored in Redis for 24 h and replayed on retry.
- **Optimistic locking:** editable entities carry `updated_at` as the lock token. A mismatch returns 409 `stale_update` with the current representation. **Rule:** background writes (counters, stats, computed indicators) go to separate tables, never to the locked row. Yaqlo was hit by this twice.
- **Time:** stored as `timestamptz` in UTC everywhere. Converted to `Europe/London` only for display and for scheduled jobs that are defined in UK time (Feature 11's 07:00 digest).
- **Soft delete:** user-facing entities use `archived_at` (nullable) and are never hard-deleted except through GDPR erasure paths (Feature 09 §6's personal-data registry)
- **Contract:** the API's OpenAPI schema is exported in CI, and `openapi-typescript` generates `web/lib/api/schema.d.ts`. CI fails if the committed types are out of date. The web app never hand-writes API types.

### 6. Data layer
- SQLAlchemy 2.0 **sync** session for app code, plus an **async** session only for FastAPI-Users (Feature 04)
- **Constraint `naming_convention`** on the metadata (`ix_%(column_0_label)s`, `uq_%(table_name)s_%(column_0_name)s`, `fk_…`, `pk_…`, `ck_…`) so Alembic can reliably alter or drop constraints later
- **Initial migration enables extensions:** `pg_trgm` (Feature 07 keyword search), `pg_stat_statements` (slow-query visibility), `citext` (case-insensitive emails, Feature 04)
- **Connection budget** (Postgres `max_connections` = 100 on the shared VM):

  | Process | Pool | Max overflow |
  |---|---|---|
  | API (sync) | 10 | 5 |
  | API (async, auth only) | 3 | 2 |
  | Each Celery worker process | 2 | 0 |
  | Reserved (migrations, admin, psql) | 10 | |

  `pool_pre_ping=True`, `pool_recycle=1800`, and a server-side `statement_timeout` of **5 s for the app role** and 0 for the migration role. If the process count grows past this budget, PgBouncer (transaction mode) goes in front, and the doc records that trigger.
- **Database roles (least privilege):** `app_rw` (DML only on app tables), `app_migrate` (DDL, used only by Alembic in deploys), `app_ro` (read-only, for ad-hoc analysis)
- **Zero-downtime migration rules** (`ops/runbooks/migrations.md`): expand → deploy → backfill (batched, in a Celery task if large) → contract in a later release. No column rename or type change in one step. `CREATE INDEX CONCURRENTLY` for indexes on tables that already exist in production.
- `TimestampMixin` (`created_at`, `updated_at` with `server_default=now()`, `onupdate=now()`). Its docstring explains the lock-token rule.

### 7. Background jobs (Celery)
- **Rule: enqueue only after the transaction commits.** `dispatch(task, *args)` registers the send through a SQLAlchemy `after_commit` hook on the current session. If the transaction rolls back, nothing is sent. Calling `.delay()` directly inside request or service code is **forbidden** (enforced by a lint rule, see §10). This prevents both "the task ran before its row existed" and "the task ran for a change that was rolled back."
- For side effects that **must not be lost** (lead emails, Feature 10), the job is backed by a status row written in the same transaction (e.g. one `LeadDelivery` row per recipient with `status = pending`, Feature 10 §4, kept off the locked `Lead` row). A beat sweeper re-enqueues anything still `pending` after 5 minutes. This is a lightweight outbox that needs no Kafka.
- **Queues and workers separated by workload:**

  | Queue | Work | Worker |
  |---|---|---|
  | `notifications` | lead emails, alerts, auth emails | concurrency 2, always on |
  | `images` | resize/strip EXIF (Feature 06) | concurrency 1, CPU-bound, isolated so it can't starve email |
  | `default` | lookups, indicators, sitemaps, sweeps | concurrency 2 |

- **Exactly one Beat process**, guaranteed by a Redis lock with a heartbeat. A second beat started by mistake exits instead of double-scheduling. Every beat task is idempotent regardless.
- Task defaults: `acks_late=True`, `task_reject_on_worker_lost=True`, a soft/hard time limit per task, retries with exponential backoff and jitter, and the result backend disabled unless a task needs it
- **Celery runs eagerly in unit tests, not in integration tests.** A small set of integration tests run against a real worker to catch serialisation and on-commit bugs that eager mode hides.

### 8. Redis — separated by role
| Role | Instance / DB | `maxmemory-policy` | Contents |
|---|---|---|---|
| **Broker** | Redis DB 0 (separate instance in production) | `noeviction` | Celery queues, which must never be silently evicted |
| **Cache & ephemeral** | Redis DB 1 | `allkeys-lru` | Response/facet caches, idempotency keys, rate-limit counters, view dedupe |

A cache eviction policy on the broker would silently drop queued jobs under memory
pressure, so the two are never shared. The cache helper `cache.get_or_set(key, ttl,
fn)` namespaces keys by module and includes a schema version, so a deploy that
changes a cached shape doesn't read old entries.

### 9. Outbound HTTP (shared client)
`core/http_client.py` provides one configured `httpx` client per integration
(DVLA, MOT, postcodes.io, valuation, Resend), with:
- **Timeouts:** connect 2 s, read 4 s, total 6 s by default, overridable per integration
- **Retries** only on idempotent requests and transient failures (connect errors, 502/503/504, 429 honouring `Retry-After`): max 2, exponential backoff with jitter
- **Circuit breaker** per integration: open after 5 consecutive failures, half-open after 30 s. Callers get a typed `IntegrationUnavailable` exception, which features translate into their "lookup unavailable, enter manually" states.
- Outbound `X-Request-ID` propagation, connection pooling with keep-alive, and a User-Agent identifying the app
- Structured log line per call (integration, endpoint, status, latency) **with redaction** (§11), plus metrics (§12)
- **In tests every integration is stubbed by default**, and any un-stubbed outbound call fails the test (respx / a socket-blocking fixture)

### 10. Code quality & module boundaries
- **Pre-commit hooks:** ruff (lint + format), pyright (basic, on `app/`), prettier + ESLint/oxlint for web, gitleaks, end-of-file/whitespace fixers
- **import-linter contracts in CI:** `modules.*` may import other modules' `services` only, never their `models` or `tasks`. `api` may not import `tasks`. `core` imports nothing from `modules`. This enforces the "a later split stays possible" promise mechanically.
- A custom ruff rule or grep check that bans direct `.delay(` / `.apply_async(` outside `core/jobs.py` (enforces §7)
- `web/`: TypeScript `strict`, `noUncheckedIndexedAccess`, and ESLint rules banning raw `fetch` outside `lib/api`

### 11. Security baseline
- **Secret scanning:** gitleaks in pre-commit **and** CI (CI is the backstop when hooks are skipped)
- **Dependency hygiene:** committed lockfiles (`uv.lock`, `package-lock.json`), Renovate/Dependabot weekly with grouped minor updates, and `pip-audit` + `npm audit --audit-level=high` in CI, failing on high/critical (moved here from Feature 14)
- **Log redaction:** a structlog processor masks emails (`j***@g***.com`), UK phone numbers, VRMs (`AB12 ***`), postcodes beyond the outward code, tokens and `Authorization`/`Cookie` headers. A test asserts that a request carrying each kind of personal data produces log lines without it. (UK GDPR: logs are retained and shipped to third parties, so they must not become a personal-data store.)
- **Object storage:** buckets are private by default. Public read is only through the CDN path for processed image variants (Feature 06). The object-storage admin identity is never given to the app, and no default credential survives outside local. Each environment has its own buckets (a private `uploads` bucket and a public-read `images` bucket, Feature 06 §3) and its own access key with bucket-scoped permissions.
- **Web CSP:** set from Next.js middleware with a per-request nonce. `default-src 'self'`, `img-src 'self' img.<domain> data: blob:` (`blob:` for upload previews), `connect-src 'self'` plus the error-tracking ingest host and the uploads-bucket host (direct presigned uploads, Feature 06 §3), and `frame-ancestors 'none'`.

### 12. Observability
- **Structured JSON logs** (structlog): every line carries `request_id`, `trace_id`, `route`, `user_id` (opaque id, never email), `status`, `duration_ms`. Celery task logs carry the originating `request_id`.
- **Error tracking: Sentry** (or equivalent) for API, Celery and web (server + client), with source maps uploaded in CI, environment tags, and personal-data scrubbing on. *(Moved here from Feature 15, so features 02–14 report errors from the day they're built.)*
- **Tracing: OpenTelemetry** instrumentation for FastAPI, SQLAlchemy, httpx, Celery and Redis, with context propagated **web SSR → API → Celery task → outbound HTTP**. Sampled at 10% in production and 100% for errors, exported over OTLP to a free-tier backend (selected during implementation) or to Sentry performance.
- **Metrics:** a Prometheus `/metrics` endpoint (internal only, blocked at the proxy) exposing request rate, latency histograms per route, DB pool usage, Celery queue depth per queue, task duration and failure counts, and integration latency and circuit-breaker state
- **Slow queries:** `pg_stat_statements` plus `log_min_duration_statement = 250ms`. A weekly top-10 slow-queries report goes into the admin ops dashboard (Feature 14).

### 13. Web (Next.js) skeleton
- App Router, `output: "standalone"` for a small production bundle, `next/font` (self-hosted, no layout shift)
- `lib/api/`: a typed client generated from the OpenAPI schema (§5). Server components call the internal API URL with forwarded headers (§3). Client components call the same-origin `/api/v1/...`. Both parse Problem Details into a typed `ApiError`.
- **en-GB formatting helpers** (`lib/format/`): `formatPrice(pence)` → `£12,495` (no pence when whole pounds), `formatMileage(n)` → `42,150 miles`, `formatDate` → `14/10/2026`, relative times ("listed 3 days ago"), all in Europe/London. No component formats money, distance or dates itself.
- Root `error.tsx`, `not-found.tsx` and `loading.tsx` conventions, styled in Feature 03
- A home page that renders the `/health/ready` status (a temporary placeholder for Feature 03)

### 14. Testing foundation
- **Backend:** `conftest.py` creates and migrates a dedicated `<db>_test` database (`127.0.0.1`, not `localhost`, to avoid the IPv6 hang seen on this machine) and **blocks all network access** except the DB, Redis and object storage.
  - **pytest-xdist** with one database per worker (`<db>_test_gw0…`), so the suite stays fast as it grows
  - **factory_boy factories** for every model, built through the **real service functions** where a service owns the write path (Yaqlo's `raw_ics_data` lesson: hand-built fixtures masked a column the real writer never set)
  - **Query-count assertion helper** (`with assert_max_queries(5): …`), mandatory in tests for every list endpoint, to catch N+1 queries
  - **Migration tests:** upgrade → downgrade → upgrade round trip, plus `alembic check` (no model change without a migration)
  - **Contract tests:** the OpenAPI schema snapshot and the generated-types freshness check (§5)
  - **Tenant-isolation harness:** a parametrised fixture that walks the route table and calls each dealer-scoped route as a different dealer (used from Feature 04 onward)
- **Web:** Vitest + Testing Library for components and helpers (`lib/format` at 100%)
- **E2E:** Playwright against the local stack, smoke-testing that the home page loads and health is ready. Every test uses the fixture `page` or explicitly closes manually created contexts (Yaqlo lesson: leaked contexts caused flaky stuck pages).
- **Coverage gate:** backend ≥ 80% line coverage on `app/services` and `app/modules`, enforced in CI. It doesn't block on UI components.

### 15. CI/CD (GitHub Actions)
| Job | Steps | Blocks merge? |
|---|---|---|
| `backend` | uv sync (frozen) → ruff → pyright → import-linter → `.delay` ban check → pytest -n auto (Postgres + Redis services) → coverage gate → `alembic check` | Yes |
| `web` | npm ci → typecheck → lint → vitest → OpenAPI-types freshness → `next build` | Yes |
| `e2e` | compose up → seed minimal → Playwright smoke | Yes (smoke only) |
| `security` | gitleaks → pip-audit → npm audit (high+) | Yes |
| `deps` | Renovate PRs (weekly, grouped) | — |

Deploys are a manual script (same shape as the other apps' `oracle-deploy` flow):
build → `app_migrate` runs Alembic → restart services → wait for `/health/ready`
→ smoke-check → done. On a failed ready check, the previous release is restored
(the release directory is kept). Migrations must be backward-compatible with the
previous release (§6), so code rollback never needs a schema rollback.

### 16. Local dev & resource limits
- `docker compose up -d`: Postgres 16 (with `pg_stat_statements` preloaded), Redis broker + cache, SeaweedFS (S3-compatible) with a bucket-scoped app identity, plus an init container that creates the bucket
- `make dev` / `just dev` starts the API, web, worker(s) and beat. `make seed` runs Feature 02's seed.
- **Production containers and services get memory and CPU limits** (systemd `MemoryMax`/`CPUQuota` or compose `deploy.resources`). Starting budget on the shared VM: API 512 MB, web 512 MB, image worker 768 MB, other workers 256 MB each, beat 128 MB. This is the Autotrader app's share of a VM it shares with Yaqlo, Duely, Scout and Suretly. One runaway image job must not take the other apps down.
- **Maintenance page:** the reverse proxy serves a static branded 503 page with `Retry-After` while the app is unavailable (deploy, migration, crash), instead of a raw 502

---

## Key Decisions

**Modular monolith, not microservices.** Report §2 describes Spring Boot microservices
on Kafka. That shape exists to let hundreds of engineers deploy independently. A solo
developer pays all of its cost (network calls, distributed transactions, schema
registry) and gets none of the benefit. The scale-relevant properties are kept
instead: enforced module boundaries (§10), a commit-safe job dispatcher with an outbox
for critical side effects (§7), and swappable backends (search, valuation). Those
leave an extraction path open without paying for distribution now.

**Next.js instead of Vite.** The other apps use a Vite SPA. Here, search-indexed
listing pages are the primary acquisition channel (§2: "car listings are heavily
search-indexed"), so server rendering is a requirement.

**Same origin for web and API.** A separate `api.` subdomain would mean CORS with
credentials, cookie `Domain` scoping, and SSR cookie forwarding across sites, for no
benefit at this scale. One origin makes the session cookie first-party and removes
CORS from production entirely.

**Real client IP is a foundation concern, not a rate-limiter detail.** Behind
Cloudflare, `request.client.host` is a Cloudflare edge IP. Any per-IP limit built on
it either blocks everyone at once or limits no one. Trusting `CF-Connecting-IP`
unconditionally is equally wrong, because anyone hitting the origin directly could
spoof it. Hence the "only from Cloudflare ranges" rule plus the origin firewall.

**No job is sent before its transaction commits.** This is the specific failure that
Kafka-plus-outbox solves at scale. At MVP scale, `after_commit` dispatch plus a status
row and a sweeper cover the same guarantee with what already exists.

**Broker and cache never share an eviction policy.** Using `allkeys-lru` for caching
on the same Redis that holds Celery queues means memory pressure silently deletes
pending jobs: lost lead emails with no error anywhere.

**Error tracking and dependency auditing start in Feature 01, not Feature 14/15.**
Fourteen features built without error tracking means fourteen features' worth of
silent failures discovered at launch.

**Use `127.0.0.1`, not `localhost`, in `DATABASE_URL`.** This avoids the IPv6
resolution hang previously seen with pytest on this machine.

## Acceptance Criteria

**Runs**
- `docker compose up -d` followed by `make dev`: the home page shows "API: ready"
- `GET /health/live` returns 200 with the DB stopped. `GET /health/ready` returns 503 naming `db`. Restarting the DB brings `/ready` back to 200 without restarting the API.
- Booting with `ENVIRONMENT=production` and any placeholder secret exits non-zero with a message naming the key

**Network & conventions**
- A request through the proxy with a spoofed `CF-Connecting-IP` from a non-Cloudflare peer resolves to the real peer IP. The same header from a Cloudflare range is honoured (unit test with both cases).
- An unhandled exception returns an RFC 9457 body with a `request_id` and no stack trace. A validation error lists each field in `errors[]`.
- Retrying a POST with the same `Idempotency-Key` returns the stored response and doesn't repeat the side effect
- An outbound call to a stubbed integration that times out raises `IntegrationUnavailable` within the configured budget. Five consecutive failures open the breaker.

**Jobs**
- A service that dispatches a task and then rolls back sends **no** task (integration test with a real worker)
- A task dispatched in a committed transaction is received only after the row is visible to the worker
- Starting a second beat process causes it to exit with a "lock held" message
- Flooding the `images` queue does not delay a `notifications` task by more than 5 s

**Data**
- The initial migration enables `pg_trgm`, `pg_stat_statements` and `citext`. `alembic upgrade head → downgrade base → upgrade head` succeeds, and `alembic check` reports no drift.
- The `app_rw` role cannot run DDL (test attempts `CREATE TABLE` and expects a permission error)
- A query exceeding 5 s under `app_rw` is cancelled with a clean 503 Problem response

**Security & observability**
- A test request containing an email, UK phone number, VRM and full postcode produces logs where all four are masked
- A committed fake AWS key fails the `security` CI job
- A deliberately thrown error in the API, a Celery task and a web server component each appear in error tracking with the same `request_id` / `trace_id` chain
- `/metrics` returns Prometheus data internally and 404 through the public proxy

**Testing & CI**
- `uv run pytest -n auto` passes on parallel per-worker databases and never touches the dev DB
- A test that makes an un-stubbed outbound HTTP call fails
- A list-endpoint test exceeding its `assert_max_queries` budget fails
- Changing a response schema without regenerating `schema.d.ts` fails the `web` job
- Importing `modules.leads.models` from `modules.listings` fails import-linter
- All CI jobs are green on a fresh clone

---

## Scale review — what was added, and what was deliberately deferred

This doc was revised after a review against large-scale concerns (security,
performance, testing, network, design conventions, scaling, UX). Items were ranked
**P0** (must be in Feature 01, since retrofitting touches every feature), **P1**
(should be in Feature 01 because it's cheap now), and **P2** (record now, build
later).

**Added (P0/P1), with their sections:** same-origin topology (§3), real client IP
behind Cloudflare (§3), after-commit job dispatch + outbox sweeper (§7), shared HTTP
client with timeouts/retries/breaker (§9), OpenAPI → TS contract (§5), RFC 9457 errors
(§5), constraint naming convention (§6), Postgres extensions (§6), broker/cache Redis
split (§8), Sentry from day one (§12), secret scanning + dependency audit in CI (§11),
log redaction (§11), frontend + E2E test harnesses (§14), liveness/readiness split +
graceful shutdown (§4), import-linter boundaries (§10), UUIDv7/pagination/idempotency/
time/soft-delete conventions (§5), queue separation + single beat (§7), connection
budget + statement timeout (§6), zero-downtime migration rules + `alembic check` (§6),
staging environment (§2), container resource limits (§16), least-privilege DB roles
and bucket policy (§6, §11), test factories (§14), N+1 query-count guard (§14),
migration round-trip + xdist (§14), OpenTelemetry tracing + metrics (§12), en-GB
formatting helpers (§13), pre-commit + type checking (§10), feature flags (§2), CSP
(§11), maintenance page (§16).

**Deferred (P2), not built in this feature:**
| Item | Trigger to revisit |
|---|---|
| Hardened production container images (non-root, distroless, image vulnerability scanning) | Moving from systemd services on the VM to containerised production deploys |
| k6 load-test scenarios | Written in Feature 07 (search budgets) and run in Feature 15. The `ops/k6/` folder exists from here. |
| PgBouncer | The process count exceeds the §6 connection budget |
| Postgres read replica + read/write session routing | Sustained primary CPU above 60% from read traffic |
| Search engine (OpenSearch) | Feature 07 p95 budget breached at real volume (Phase 2) |
| Blue/green or canary deploys | More than one app instance, or a deploy-caused incident |
| Multi-region / Kubernetes | Not foreseeable at MVP scale. The report's real platform needs it (§2), but this MVP doesn't. |

---

## Implementation notes (2026-10-19)

**Deviations from the plan above, and why**
- **Object storage is SeaweedFS locally/CI, not MinIO.** MinIO's community project was archived and its images are no longer pullable from Docker Hub or quay.io, so a fresh CI runner could not start the stack. SeaweedFS (pinned `3.97`) speaks the same S3 API; its declarative identities keep the bucket-scoped app key rule (verified: the app key can head/put/presign-upload its bucket and cannot create others). Settings are now vendor-neutral `S3_*`. Production remains R2/S3.
- **`statement_timeout` is set per connection** (`DB_STATEMENT_TIMEOUT_MS`, default 5000) as well as on the `app_rw` role. A role's `ALTER ROLE ... SET` only applies to the login role, never via `SET ROLE`, so relying on it alone left the 5 s cap unenforced.
- **Roles/grants live in `ops/postgres/roles.sql`**, idempotent and applied by Compose init, `make db-roles`, and the test harness (grants are per-database, so every per-worker test DB needs them).
- **Log redaction masks to tokens** (`[redacted-email]`, `[redacted-vrm]`...) rather than partial masks like `j***@g***.com`: a partial mask still leaks enough to re-identify on a small dataset.
- **Idempotency keys are scoped to the caller** (session cookie, else client IP), so one client can never be replayed another's stored response. Reusing a key with a different body is 422; a duplicate while the original is in flight is 409 + `Retry-After`; 5xx is not stored; Redis down fails open with a warning.
- **The coverage gate includes `app/core`** (85%; 89% at completion). Gating only `app/services`/`app/modules` measured nothing, since both are still empty.
- **Route templates for logs/metrics are rebuilt from the matched route** (`metrics.route_template_for`): FastAPI >= 0.13x mounts included routers lazily and `scope['route'].path` drops the `/api/v1` prefix.

**Bugs found and fixed while completing this feature**
- CI could never have passed: an invalid `ruff format --quote-style` flag; `check_web_fetch.mjs` could not resolve `typescript`; oxlint failed on generated `next-env.d.ts`; `minio/mc` unpullable.
- `/health/ready` ran blocking DB/Redis/S3 I/O on the event loop, with no S3 timeout (a hung bucket hung the probe). It now runs checks concurrently off-loop with per-check timeouts, names every failing dependency, and caches the verdict for 1 s against probe floods.
- Celery workers never initialised logging/Sentry/OTel, so **worker logs printed personal data unredacted** (reproduced, then covered by a subprocess test). Stdlib loggers (Celery, uvicorn, SQLAlchemy) also bypassed redaction; uvicorn's access log printed raw query strings. All now go through one redacting JSON pipeline with a templated `http_request` access line.
- nginx `proxy_intercept_errors` replaced the API's own 503 problem+json with the HTML maintenance page.
- The OpenAPI post-processor dropped the `ProblemDetails` schema, so every error response was `unknown` in the generated web types.
- `formatPrice` rendered 50p as `£12,495.5`.
- Feature-flag names: `is_enabled()` normalises before querying, but nothing stopped a row being stored unnormalised (it would silently never turn on). A CHECK constraint now enforces the normalised form (migration `d4dbde7c7413`).

**Acceptance criteria: how each was verified**
| Criterion | Evidence |
|---|---|
| Live/ready split, 503 names dependency, recovers without restart | tests + real stack (`pool_pre_ping`) |
| Placeholder secret refuses boot, naming the key | parametrised test, one per secret |
| Spoofed `CF-Connecting-IP` ignored | tests |
| RFC 9457 errors, validation `errors[]` | tests |
| Idempotency replay | 8 tests on real Redis |
| Integration timeout -> `IntegrationUnavailable`; breaker opens at 5 | tests |
| Rollback sends no task; committed task sees its row | **real in-thread worker + real broker + Postgres** |
| Second beat exits "lock held" | test; real beat booted |
| Extensions, migration round trip, `alembic check` | run locally, in CI |
| `app_rw` cannot DDL; >5 s query -> clean 503 | tests on real Postgres |
| PII masked in logs (email, phone, VRM, postcode) | tests + real uvicorn run (0 raw occurrences) |
| `/metrics` internal only | test; nginx returns 404 |
| Parallel per-worker DBs, network blocked, N+1 guard | tests |
| Stale `schema.d.ts` / import-linter violation fail CI | CI steps; import probe run locally |

**Not yet verifiable from a dev machine; check on first real run**
- "All CI jobs green on a fresh clone": nothing is committed or pushed yet.
- `images` flood does not delay `notifications` by > 5 s: guaranteed structurally (separate queues + separate systemd workers), not load-tested.
- Same `request_id` chain visible in a real Sentry project: tags are wired (API, worker, web `onRequestError`); needs a DSN.
- `ops/deploy/deploy.sh` (release dirs, migrate, atomic switch, ready-wait, rollback) and `ops/systemd/*` (memory/CPU limits): shellcheck and `systemd-analyze verify` clean, but never executed on the VM.
- Web source-map upload runs only when CI provides `SENTRY_AUTH_TOKEN`/`SENTRY_ORG`/`SENTRY_PROJECT`.
