# Autotrader

A dealer-led UK used-car marketplace, built as a modular monolith: FastAPI + SQLAlchemy +
Celery on PostgreSQL and Redis, S3-compatible object storage, and a Next.js App Router
web app. Plan and status: [FEATURES_PLAN.md](FEATURES_PLAN.md); per-feature design docs
in [features/](features/). The conventions every feature builds on (errors, IDs,
pagination, idempotency, job dispatch, logging) are in
[Feature 01](features/01-project-foundation.md).

## Prerequisites

- Docker Engine/Desktop with Compose v2
- GNU Make
- `uv` and Python 3.11 or 3.12
- Node.js 22 and npm

## Local development

```sh
cp .env.example .env
make install
make dev        # infra + API + web + Celery worker + Beat
```

`make dev` starts PostgreSQL, the two Redis roles (broker: `noeviction`; cache:
`allkeys-lru`) and S3-compatible storage (SeaweedFS), creates the bucket, then runs
the API, web app, worker and Beat. On a memory-constrained machine run `make infra` and
then only the targets you need (`make api`, `make web`, `make worker`, `make beat`).

```sh
make migrate    # alembic upgrade head
make db-roles   # re-apply least-privilege DB roles to an existing volume
make api-types  # re-export OpenAPI and regenerate web/lib/api/schema.d.ts
make logs       # follow container logs
make down       # stop containers (data volumes are kept)
```

Local URLs:

- Web: <http://127.0.0.1:3000> (the home page shows API readiness)
- API docs: <http://127.0.0.1:8000/docs>
- Liveness: <http://127.0.0.1:8000/api/v1/health/live>
- Readiness (DB + migrations, both Redis roles, storage): <http://127.0.0.1:8000/api/v1/health/ready>
- S3 API: <http://127.0.0.1:9000>

Use `127.0.0.1`, not `localhost`, in URLs; `localhost` can resolve to IPv6 first and hang.

## Tests and checks

```sh
make check       # backend lint/types/boundaries, backend tests + coverage, web checks
make test        # backend: pytest -n auto, coverage gate 85% on app/core, services, modules
make web-check   # typecheck, oxlint, vitest + 100% gate on lib/format, fetch boundary
pre-commit install
```

Backend tests need the Compose services running. Each xdist worker gets its own
migrated database (`<db>_test_gwN`); the dev database is never touched; outbound
network access is blocked except to local infrastructure. To run tests against a
separate stack, `.env.test` holds alternate ports:
`docker compose -p autotrader-test --env-file .env.test up -d --wait`.

## Operations

- [Deploy and rollback](ops/deploy/deploy.sh): release directories, migrate as `app_migrate`, atomic switch, ready-wait, automatic rollback
- [systemd units](ops/systemd/) with the per-service memory/CPU budget
- [Reverse proxy](ops/nginx/autotrader.conf) and [network notes](ops/runbooks/network-proxy.md)
- [Secrets handling and rotation](ops/runbooks/secrets.md)
- [Migrations and rollback](ops/runbooks/migrations.md)
- [Local resources](ops/runbooks/local-development.md)

`.env.example` contains local-only placeholders; the API refuses to boot with any of
them when `ENVIRONMENT` is `staging` or `production`.
