-- Runs once, when the Compose Postgres volume is first created.
-- Roles and grants live in roles.sql (mounted as 01-roles.sql) so they can be re-applied.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
