# Local Development Resources

The local Compose stack is for development, not production hardening. PostgreSQL
uses the official PostgreSQL 16 image with `pg_stat_statements` preloaded and a
250 ms slow-query log threshold. The extension initialization SQL runs only when
the data volume is first created. If an existing volume predates the init file,
create the extensions with a local superuser or discard the local volume only
when its data is no longer needed.

For an existing local volume, connect to the `autotrader` database as its local
superuser and run `CREATE EXTENSION IF NOT EXISTS pg_stat_statements;`,
`CREATE EXTENSION IF NOT EXISTS pg_trgm;`, and
`CREATE EXTENSION IF NOT EXISTS citext;`.

The broker and cache are separate Redis 7 containers. Broker Redis uses
`noeviction`; cache Redis uses `allkeys-lru`. Each has a local 256 MB max-memory
budget. The broker limit is a development guardrail, not a claim that queued work
is durable: persistence is disabled locally and the broker must not be treated as
the system of record.

Object storage is **SeaweedFS** (`chrislusf/seaweedfs`, pinned), an S3-compatible
stand-in for R2/S3. It replaced MinIO in October 2026: MinIO's community project
was archived and its images can no longer be pulled from Docker Hub or quay.io.
It starts with a persistent volume on `S3_PORT` (default 9000). `make infra` runs
an idempotent initializer that creates the private `autotrader-uploads` bucket.
The app's key is scoped to that bucket only (read/write/list); the admin identity
is used only by the initializer. Credentials and ports can be changed in `.env`.

Least-privilege roles (`app_rw`, `app_migrate`, `app_ro`) come from
`ops/postgres/roles.sql`. Compose applies it only when the volume is first
created; on an existing volume run `make db-roles` (idempotent). The test suite
applies it to each per-worker test database itself.

The services do not impose Docker CPU/memory quotas: Docker Desktop's global
resource settings govern them. For a constrained machine, start dependencies
with `make infra` and then start only what is needed (`make api`, `make web`, or
`make worker`) rather than `make dev`, which starts API, web, worker, and Beat.
The production per-service resource budgets from Feature 01 are deployment
requirements, not local Compose limits; production services are not deployed by
this Compose file.