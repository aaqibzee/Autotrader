# Database roles and migration operations

Alembic reads `DATABASE_URL` from the repository-root environment configuration. Keep credentials
out of `alembic.ini`, migration files, and source control. Run migrations with the dedicated
`app_migrate` role; the API must connect as `app_rw` instead.

## PostgreSQL role setup

Have a database administrator create the login roles and set their passwords through an interactive
or secret-manager workflow, not in a checked-in SQL file:

```sql
CREATE ROLE app_rw LOGIN;
CREATE ROLE app_migrate LOGIN;
CREATE ROLE app_ro LOGIN;

GRANT CONNECT ON DATABASE <database_name> TO app_rw, app_migrate, app_ro;
GRANT USAGE ON SCHEMA public TO app_rw, app_ro;
GRANT USAGE, CREATE ON SCHEMA public TO app_migrate;
REVOKE CREATE ON SCHEMA public FROM app_rw, app_ro;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE app_migrate IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE app_migrate IN SCHEMA public
    GRANT SELECT ON TABLES TO app_ro;

ALTER ROLE app_rw SET statement_timeout = '5s';
ALTER ROLE app_ro SET statement_timeout = '5s';
ALTER ROLE app_migrate SET statement_timeout = '0';
```

Replace `<database_name>` with the target database name before executing. Set each login password
separately with `\password` in `psql` or through the deployment secret manager. `app_rw` gets
table DML only; it must not own the schema or tables and must not receive DDL privileges. Run
Alembic only as `app_migrate`, whose credentials belong only to the deployment process. Role-level
timeouts apply to new connections, so recycle or restart application pools after changing them.

On PostgreSQL installations where `pg_stat_statements` is not already available, a DBA must add
`pg_stat_statements` to `shared_preload_libraries` and restart PostgreSQL before the initial
migration. The migration uses `CREATE EXTENSION IF NOT EXISTS`; it does not alter server-wide
configuration or create roles. If the migration role cannot install extensions, have the DBA
pre-create the three extensions in the target database, then run the migration as `app_migrate`.

## Migration safety

Use expand → deploy → backfill → contract for schema changes. Do not combine a column rename or
type change into one release. Build indexes on populated production tables concurrently in a
separate migration transaction. The initial migration's downgrade drops only the application
table; it deliberately retains the extensions because they may be shared by other database
objects or applications.
