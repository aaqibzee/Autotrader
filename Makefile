.PHONY: db-roles dev infra api backend web worker beat install migrate api-types test backend-check web-check check logs down

dev: infra
	$(MAKE) --jobs=4 api web worker beat

infra:
	docker compose up -d --wait postgres redis-broker redis-cache object-storage
	docker compose run --rm object-storage-init

api:
	@cd backend && uv sync && uv run uvicorn app.main:app --reload --no-access-log --host 127.0.0.1 --port 8000

backend: api

web:
	@cd web && npm run dev -- --hostname 127.0.0.1

worker:
	@cd backend && uv run celery -A app.core.celery_app:celery_app worker --loglevel=info --pool=solo

beat:
	@cd backend && uv run celery -A app.core.celery_app:celery_app beat --loglevel=info

install:
	@cd backend && uv sync --frozen
	@cd web && npm ci

# Re-apply least-privilege roles/grants to an existing volume (init scripts only run on a fresh one).
db-roles:
	docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /opt/autotrader/roles.sql'

migrate:
	@cd backend && uv run alembic upgrade head

api-types:
	uv run --directory backend python -m scripts.export_openapi
	npm --prefix web run api:types

test:
	@cd backend && uv run pytest -n auto --cov=app/core --cov=app/services --cov=app/modules --cov-report=term-missing:skip-covered --cov-fail-under=85

backend-check:
	@cd backend && uv run ruff check app tests
	@cd backend && uv run ruff format --check app tests
	@cd backend && uv run pyright app
	@cd backend && uv run lint-imports --no-cache --no-logo
	@python ops/ci/check_celery_dispatch.py

web-check:
	@cd web && npm run typecheck && npm run lint && npm run test:coverage
	@node ops/ci/check_web_fetch.mjs
	@node ops/ci/check_web_boundaries.mjs

check: backend-check test web-check

logs:
	docker compose logs --follow

down:
	docker compose down
