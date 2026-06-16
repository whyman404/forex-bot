# ============================================================================
# Makefile — Forex Bot Platform
# ============================================================================
# One-shot orchestration for local dev. Wraps docker compose + helpers.
# Usage: `make` shows help. `make up` starts everything.
# ============================================================================

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

COMPOSE_FILE := infra/docker-compose.yml
COMPOSE_OVERRIDE := infra/docker-compose.override.yml
COMPOSE := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) --project-directory .
COMPOSE_PROD := docker compose -f $(COMPOSE_FILE) --project-directory .

# Colors
YELLOW := \033[1;33m
GREEN  := \033[1;32m
CYAN   := \033[1;36m
RED    := \033[1;31m
NC     := \033[0m

.PHONY: help
help: ## Show this help
	@printf "$(CYAN)Forex Bot Platform — make targets$(NC)\n\n"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## / {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf "\n$(YELLOW)Quick start:$(NC)\n"
	@printf "  ./scripts/dev.sh        # one-shot setup + start\n"
	@printf "  make up                 # start services\n"
	@printf "  make logs               # follow logs\n"
	@printf "  open http://localhost:3000\n\n"

.PHONY: up
up: ## Start all services (dev mode with hot reload)
	@printf "$(CYAN)>> docker compose up -d$(NC)\n"
	@$(COMPOSE) up -d --remove-orphans
	@$(MAKE) ps

.PHONY: up-prod
up-prod: ## Start all services in prod-like mode (no override)
	@printf "$(CYAN)>> docker compose up -d (prod-like)$(NC)\n"
	@$(COMPOSE_PROD) up -d --remove-orphans

.PHONY: down
down: ## Stop and remove containers
	@printf "$(CYAN)>> docker compose down$(NC)\n"
	@$(COMPOSE) down

.PHONY: restart
restart: ## Restart all services
	@printf "$(CYAN)>> restart$(NC)\n"
	@$(COMPOSE) restart

.PHONY: ps
ps: ## Show service status
	@$(COMPOSE) ps

.PHONY: logs
logs: ## Tail logs from all services
	@$(COMPOSE) logs -f --tail=100

.PHONY: logs-backend
logs-backend: ## Tail backend logs only
	@$(COMPOSE) logs -f --tail=200 backend

.PHONY: logs-frontend
logs-frontend: ## Tail frontend logs only
	@$(COMPOSE) logs -f --tail=200 frontend

.PHONY: logs-engine
logs-engine: ## Tail trading-engine logs only
	@$(COMPOSE) logs -f --tail=200 trading-engine-worker

.PHONY: build
build: ## Build all images
	@$(COMPOSE) build --pull

.PHONY: rebuild
rebuild: ## Force rebuild without cache
	@$(COMPOSE) build --no-cache --pull

.PHONY: migrate
migrate: ## Run Alembic migrations against the running DB
	@printf "$(CYAN)>> alembic upgrade head$(NC)\n"
	@$(COMPOSE) exec -T backend alembic upgrade head

.PHONY: migrate-create
migrate-create: ## Create a new migration (use MSG="message")
	@if [ -z "$(MSG)" ]; then printf "$(RED)Usage: make migrate-create MSG=\"add users table\"$(NC)\n"; exit 1; fi
	@$(COMPOSE) exec -T backend alembic revision --autogenerate -m "$(MSG)"

.PHONY: seed
seed: ## Seed dev database (admin user + sample strategies)
	@printf "$(CYAN)>> seeding dev DB$(NC)\n"
	@$(COMPOSE) exec -T backend python -m app.scripts.seed || \
		$(COMPOSE) exec -T backend python -c "import asyncio; print('seed script not yet wired — skipping')"

.PHONY: shell-backend
shell-backend: ## Open shell in backend container
	@$(COMPOSE) exec backend /bin/bash

.PHONY: shell-frontend
shell-frontend: ## Open shell in frontend container
	@$(COMPOSE) exec frontend /bin/sh

.PHONY: shell-db
shell-db: ## Open psql shell
	@$(COMPOSE) exec postgres psql -U forexbot -d forexbot

.PHONY: shell-redis
shell-redis: ## Open redis-cli
	@$(COMPOSE) exec redis redis-cli

.PHONY: test
test: ## Run all test suites
	@printf "$(CYAN)>> backend tests$(NC)\n"
	@$(COMPOSE) exec -T backend pytest -q
	@printf "$(CYAN)>> frontend tests$(NC)\n"
	@$(COMPOSE) exec -T frontend pnpm test
	@printf "$(CYAN)>> trading-engine tests$(NC)\n"
	@$(COMPOSE) exec -T trading-engine-worker pytest -q

.PHONY: test-backend
test-backend: ## Run backend tests
	@$(COMPOSE) exec -T backend pytest -q --cov=app --cov-report=term-missing

.PHONY: test-frontend
test-frontend: ## Run frontend tests
	@$(COMPOSE) exec -T frontend pnpm test

.PHONY: test-engine
test-engine: ## Run trading-engine tests
	@$(COMPOSE) exec -T trading-engine-worker pytest -q

.PHONY: lint
lint: ## Lint everything
	@printf "$(CYAN)>> backend lint (ruff)$(NC)\n"
	@$(COMPOSE) exec -T backend ruff check app
	@printf "$(CYAN)>> backend types (mypy)$(NC)\n"
	@$(COMPOSE) exec -T backend mypy app || true
	@printf "$(CYAN)>> frontend lint$(NC)\n"
	@$(COMPOSE) exec -T frontend pnpm lint
	@printf "$(CYAN)>> frontend typecheck$(NC)\n"
	@$(COMPOSE) exec -T frontend pnpm typecheck || $(COMPOSE) exec -T frontend pnpm tsc --noEmit

.PHONY: format
format: ## Auto-format code
	@$(COMPOSE) exec -T backend ruff format app
	@$(COMPOSE) exec -T frontend pnpm format || true

.PHONY: smoke
smoke: ## Run smoke tests against running stack
	@./scripts/smoke.sh

.PHONY: clean
clean: ## Stop containers and remove volumes (DATA LOSS!)
	@printf "$(RED)>> WARNING: this removes all volumes (postgres, redis, grafana)$(NC)\n"
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	@$(COMPOSE) down -v --remove-orphans
	@printf "$(GREEN)>> clean done$(NC)\n"

.PHONY: clean-images
clean-images: ## Remove built project images
	@docker image ls --filter "reference=forex-bot/*" -q | xargs -r docker rmi -f

.PHONY: pull
pull: ## Pull latest base images
	@$(COMPOSE) pull

.PHONY: env
env: ## Create .env from .env.example if missing
	@if [ ! -f .env ]; then \
		printf "$(CYAN)>> copying .env.example → .env$(NC)\n"; \
		cp .env.example .env; \
	else \
		printf "$(YELLOW)>> .env already exists — skipping$(NC)\n"; \
	fi

.PHONY: dev
dev: ## One-shot dev start (calls scripts/dev.sh)
	@./scripts/dev.sh

# ============================================================================
# Production deploy targets (Phase 2)
# ============================================================================

COMPOSE_PROD_FILE := infra/docker-compose.prod.yml
COMPOSE_PROD_STACK := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROD_FILE) --project-directory .

PROD_HOST ?= ops@vps.forexbot.example.com
STG_HOST ?= ops@staging.forexbot.example.com

.PHONY: deploy-prod
deploy-prod: ## Deploy current main to production (interactive, with smoke + rollback)
	@printf "$(CYAN)>> deploying to production ($(PROD_HOST))$(NC)\n"
	@./scripts/deploy.sh --env=production --host=$(PROD_HOST)

.PHONY: deploy-staging
deploy-staging: ## Deploy current branch to staging
	@printf "$(CYAN)>> deploying to staging ($(STG_HOST))$(NC)\n"
	@./scripts/deploy.sh --env=staging --host=$(STG_HOST)

.PHONY: rollback-prod
rollback-prod: ## Rollback production to last known good
	@printf "$(RED)>> rolling back production$(NC)\n"
	@./scripts/rollback.sh --env=production --host=$(PROD_HOST)

.PHONY: rollback-staging
rollback-staging: ## Rollback staging to last known good
	@./scripts/rollback.sh --env=staging --host=$(STG_HOST)

.PHONY: backup-now
backup-now: ## Trigger an immediate ad-hoc backup on production
	@ssh $(PROD_HOST) "/srv/forex-bot/infra/backup/backup.sh"

.PHONY: backup-verify
backup-verify: ## Trigger backup verification drill on production
	@ssh $(PROD_HOST) "/srv/forex-bot/infra/backup/verify.sh"

.PHONY: rotate-jwt
rotate-jwt: ## Rotate JWT signing key on production
	@./infra/scripts/rotate-secrets.sh --secret=JWT_SECRET_KEY --host=$(PROD_HOST)

.PHONY: rotate-kek
rotate-kek: ## Rotate encryption KEK (requires rewrap)
	@./infra/scripts/rotate-secrets.sh --secret=ENCRYPTION_KEK_BASE64 --host=$(PROD_HOST) --rewrap

.PHONY: prod-logs
prod-logs: ## Tail production backend logs
	@ssh $(PROD_HOST) "cd /srv/forex-bot && $(COMPOSE_PROD_STACK) --env-file .env.production logs --tail 200 -f backend"

.PHONY: prod-ps
prod-ps: ## Show production service status
	@ssh $(PROD_HOST) "cd /srv/forex-bot && $(COMPOSE_PROD_STACK) --env-file .env.production ps"

.PHONY: prod-kill-switch
prod-kill-switch: ## EMERGENCY: trigger global kill switch on production
	@printf "$(RED)>> EMERGENCY: triggering global kill switch$(NC)\n"
	@read -p "Type 'KILL ALL' to confirm: " confirm && [ "$$confirm" = "KILL ALL" ]
	@ssh $(PROD_HOST) "cd /srv/forex-bot && $(COMPOSE_PROD_STACK) --env-file .env.production exec backend python -m app.scripts.kill_all --confirm"
