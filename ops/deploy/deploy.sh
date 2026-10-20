#!/usr/bin/env bash
# Deploy a git ref to the VM (Feature 01 §15). Run on the VM as a sudo-capable user:
#
#   sudo /opt/autotrader/current/ops/deploy/deploy.sh <git-ref>
#
# Layout:
#   /opt/autotrader/repo          bare-ish clone used only to export releases
#   /opt/autotrader/releases/<id> immutable release directories (last 5 kept)
#   /opt/autotrader/current       symlink to the live release (switched atomically)
#   /opt/autotrader/shared        state that survives releases (beat schedule)
#   /etc/autotrader/autotrader.env   runtime env (app_rw credentials), mode 600
#   /etc/autotrader/migrate.env      MIGRATE_DATABASE_URL (app_migrate), mode 600
#
# Migrations run *before* traffic switches and must be backward-compatible with the
# previous release (ops/runbooks/migrations.md), so a code rollback never needs a
# schema rollback.
set -euo pipefail

REF="${1:?usage: deploy.sh <git-ref>}"
ROOT=/opt/autotrader
REPO="$ROOT/repo"
RELEASES="$ROOT/releases"
CURRENT="$ROOT/current"
KEEP_RELEASES=5
READY_URL=http://127.0.0.1:8000/api/v1/health/ready
WEB_URL=http://127.0.0.1:3000/
READY_TIMEOUT_SECONDS=90
SERVICES=(autotrader-api autotrader-web autotrader-worker-notifications
  autotrader-worker-default autotrader-worker-images autotrader-beat)

log() { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

exec 9>/run/autotrader-deploy.lock
flock -n 9 || { log "another deploy is running"; exit 1; }

previous=""
if [[ -L "$CURRENT" ]]; then
  previous="$(readlink -f "$CURRENT")"
fi

# --- 1. Export the release ---------------------------------------------------
git -C "$REPO" fetch --quiet --prune origin
sha="$(git -C "$REPO" rev-parse --verify "origin/$REF^{commit}" 2>/dev/null \
  || git -C "$REPO" rev-parse --verify "$REF^{commit}")"
release="$RELEASES/$(date -u +%Y%m%d%H%M%S)-${sha:0:12}"
log "building $sha into $release"
mkdir -p "$release"
git -C "$REPO" archive "$sha" | tar -x -C "$release"
chown -R autotrader:autotrader "$release"

as_app() { sudo -u autotrader -H "$@"; }

# --- 2. Build (nothing live has changed yet; failure here is harmless) --------
as_app bash -c "cd '$release/backend' && uv sync --frozen --no-dev"
as_app bash -c "cd '$release/web' && npm ci --no-audit --no-fund \
  && NODE_OPTIONS=--max-old-space-size=1536 NEXT_TELEMETRY_DISABLED=1 npm run build \
  && cp -r .next/static .next/standalone/.next/static \
  && if [ -d public ]; then cp -r public .next/standalone/public; fi"

# --- 3. Migrate as the DDL role ---------------------------------------------
log "applying migrations"
as_app bash -c "set -a; . /etc/autotrader/migrate.env; set +a; \
  cd '$release/backend' && DATABASE_URL=\"\$MIGRATE_DATABASE_URL\" .venv/bin/alembic upgrade head"

# Reference data, not demo data: every environment needs it (Feature 02 §1). DML only,
# so it runs as the app role. Idempotent, never deletes, and serialised by an advisory
# lock, so a failed deploy can simply be re-run. The old release never reads new rows.
log "loading vehicle taxonomy"
as_app bash -c "set -a; . /etc/autotrader/autotrader.env; set +a; \
  cd '$release/backend' && .venv/bin/python -m scripts.load_taxonomy"

# --- 4. Units, switch, restart ------------------------------------------------
install -m 0644 "$release"/ops/systemd/autotrader-*.service "$release"/ops/systemd/autotrader.target \
  /etc/systemd/system/
systemctl daemon-reload

switch_to() {
  ln -sfn "$1" "$CURRENT.next"
  mv -Tf "$CURRENT.next" "$CURRENT"
  # Workers get SIGTERM (warm shutdown); acks_late re-delivers anything unfinished.
  systemctl restart "${SERVICES[@]}"
}

wait_healthy() {
  local deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
  until curl -fsS --max-time 3 "$READY_URL" >/dev/null 2>&1; do
    if ((SECONDS >= deadline)); then
      log "API not ready after ${READY_TIMEOUT_SECONDS}s"
      curl -sS --max-time 3 "$READY_URL" || true
      return 1
    fi
    sleep 2
  done
  # Smoke: the SSR home page renders and reaches the API.
  curl -fsS --max-time 10 "$WEB_URL" | grep -q 'Service readiness' || {
    log "web smoke check failed"
    return 1
  }
}

log "switching traffic"
switch_to "$release"
if ! wait_healthy; then
  if [[ -n "$previous" ]]; then
    log "ROLLING BACK to $previous"
    switch_to "$previous"
    wait_healthy || log "previous release is also unhealthy: investigate now"
  fi
  exit 1
fi

# --- 5. Prune -----------------------------------------------------------------
mapfile -t old < <(ls -1dt "$RELEASES"/*/ | tail -n +$((KEEP_RELEASES + 1)))
for dir in "${old[@]}"; do
  [[ "$(readlink -f "$dir")" == "$(readlink -f "$CURRENT")" ]] && continue
  rm -rf "$dir"
done
log "deployed $sha"
