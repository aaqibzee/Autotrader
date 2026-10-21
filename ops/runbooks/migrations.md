# Database Migrations

Apply schema changes through Alembic, never by hand-editing a production
database. For local development, run `make migrate` from the repository root.
That target runs `alembic upgrade head` from `backend/`.

## Safe change sequence

1. Back up the target database and confirm the backup can be read before a
   production migration.
2. Review the generated migration and test it against a disposable database.
   Prefer additive expansion: add nullable columns/tables/indexes first, deploy
   code that can use both old and new shapes, backfill in bounded batches, then
   remove old schema in a later release.
3. Use `CREATE INDEX CONCURRENTLY` for indexes on populated production tables;
   such statements must be outside a transaction block in Alembic.
4. Deploy compatible application code, apply migrations with the dedicated
   migration identity, then verify `/api/v1/health/ready` and application logs.
5. On application rollback, keep the expanded schema in place. Do not run
   `alembic downgrade` automatically as part of code rollback; schema contraction
   belongs in a later release after all code has stopped using the old shape.

The initial migration enables the required PostgreSQL extensions and creates the
feature-flag table. CI exercises upgrade, downgrade-to-base, upgrade again, and
`alembic check` against a disposable database. The dedicated per-worker test DB
is migrated before backend tests run; the developer database is never used by
pytest.

## Database roles

Production uses three separate identities: `app_rw` for application DML,
`app_migrate` for Alembic DDL, and `app_ro` for read-only operational queries.
Provision credentials through the secret manager, not this repository. The
`app_rw` login has `statement_timeout = '5s'`; `app_migrate` has no statement
timeout. Grant the application and migration logins membership in the matching
roles, and ensure Alembic connects as `app_migrate` so migrated objects are
owned by the migration role. Do not grant schema `CREATE` or table ownership to
`app_rw`.

Local Compose creates the roles and default privileges through
`ops/postgres/00-extensions.sql`. That script runs only when the Postgres data
volume is initialized; existing local volumes need the script applied once by
the local database superuser after the stack is available.
