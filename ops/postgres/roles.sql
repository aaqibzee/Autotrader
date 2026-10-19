-- Least-privilege database roles (Feature 01 §6). Idempotent: safe to re-run on an
-- existing cluster and on every database that needs the grants.
--
-- Roles are cluster-wide, but GRANTs and default privileges are per-database, so this
-- file must be applied to *each* database (the dev DB, each pytest worker DB, staging,
-- production). It is applied by: the Compose init hook (fresh volumes only),
-- `make db-roles` (existing volumes), and backend/tests/conftest.py (test databases).
--
-- app_rw       DML only on app tables. Login users for the API/workers are granted it.
-- app_migrate  DDL; used only by Alembic during deploys.
-- app_ro       read-only, for ad-hoc analysis.

DO $$
DECLARE
	role_name text;
BEGIN
	FOREACH role_name IN ARRAY ARRAY['app_rw', 'app_migrate', 'app_ro'] LOOP
		IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
			BEGIN
				EXECUTE format('CREATE ROLE %I NOLOGIN', role_name);
			EXCEPTION
				-- Parallel test workers can race to create the same cluster-wide role.
				WHEN duplicate_object OR unique_violation THEN NULL;
			END;
		END IF;
	END LOOP;
END
$$;

-- Applied at login for users that inherit these roles via `ALTER ROLE <login> SET ...`
-- in the deploy runbook; the app additionally sets statement_timeout on every
-- connection (DB_STATEMENT_TIMEOUT_MS), which does not rely on login-role settings.
ALTER ROLE app_rw SET statement_timeout = '5s';
ALTER ROLE app_migrate SET statement_timeout = '0';

DO $$
BEGIN
	EXECUTE format(
		'GRANT CONNECT ON DATABASE %I TO app_rw, app_migrate, app_ro',
		current_database()
	);
	-- Objects created by whoever runs migrations here (the superuser locally,
	-- app_migrate in deployed environments) are readable/writable by app_rw.
	EXECUTE format(
		'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw',
		current_user
	);
	EXECUTE format(
		'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON TABLES TO app_ro',
		current_user
	);
	EXECUTE format(
		'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_rw',
		current_user
	);
	EXECUTE format(
		'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_ro',
		current_user
	);
END
$$;

GRANT USAGE ON SCHEMA public TO app_rw, app_migrate, app_ro;
GRANT CREATE ON SCHEMA public TO app_migrate;
-- PostgreSQL 15+ already revokes CREATE on public from PUBLIC; be explicit anyway.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_ro;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE app_migrate IN SCHEMA public
	GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE app_migrate IN SCHEMA public
	GRANT SELECT ON TABLES TO app_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE app_migrate IN SCHEMA public
	GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE app_migrate IN SCHEMA public
	GRANT USAGE, SELECT ON SEQUENCES TO app_ro;
