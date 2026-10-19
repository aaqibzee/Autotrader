# Secrets Handling

`.env.example` is for local development only. Its credentials are intentionally
marked as placeholders and must never be reused on staging or production.

## Provisioning

1. Create the service-owned environment file on the host using the deployment
   account's secret manager or a secure interactive editor. Do not pass secret
   values as command-line arguments, commit them, or paste them into CI logs.
2. Generate independent random values for `SECRET_KEY`, database credentials
   (one login per role: the runtime user granted `app_rw`, and a separate
   `app_migrate` login kept only in `/etc/autotrader/migrate.env`), and the
   object-storage access key/secret (`S3_ACCESS_KEY`/`S3_SECRET_KEY`). For
   example, `openssl rand -hex 32` is suitable for random secret material.
3. Set `ENVIRONMENT=staging` or `ENVIRONMENT=production`, the matching database
   and Redis URLs, and environment-specific bucket/observability credentials.
   Never point staging at production data or reuse its bucket.
4. Restrict the file to the service account (`chown <service-user>:<service-group>`)
   and mode `0600` (`chmod 600`). Keep backups encrypted and access-controlled.
5. Verify that the file is excluded by Git (`.env` is ignored) and that the
   service manager loads it without printing its contents.

The backend rejects known `.env.example` credentials and common placeholder
markers when `ENVIRONMENT` is `staging` or `production`. The check runs during
settings construction, so a bad service environment fails before the API or
worker starts. Keep this guard in CI and retain the deployment-side validation
as an independent check.

## Rotation

1. Generate a replacement secret and record the change in the restricted
   operations log without recording the value.
2. For database or object-storage credentials, provision the replacement
   principal first, update the service environment, restart/reload the affected
   services, and verify readiness plus a read/write smoke check.
3. Revoke the old credential only after the new credential is confirmed in use.
   For `SECRET_KEY`, plan for existing signed sessions to become invalid.
4. Remove the old value from deployment secrets and encrypted backups according
   to the organization's retention policy. Investigate and rotate immediately
   if a value may have been exposed; deleting the file alone is not remediation.

Never give the application an admin object-storage identity. In deployed
environments the R2/S3 token is scoped to that environment's buckets only.
Locally, `ops/object-storage/start.sh` generates two identities from `.env`: the
`S3_ROOT_*` admin (used only by the bucket init container) and the `S3_*` app key,
which is limited to `S3_BUCKET`. Changing `S3_BUCKET` re-scopes the app key
automatically on the next `make infra`.