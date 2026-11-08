# Project commands: `make help` lists them all. Works with GNU Make 3.81 (the version macOS ships).
UV      ?= uv
COMPOSE ?= docker compose
IMAGE   ?= agent-wf
API_URL ?= http://localhost:8000
ARGS    ?=
CONFIRM ?=

# Looked up only by the targets that use them, so `make help` needs neither uv nor git.
VERSION = $(shell $(UV) version --short)
GIT_SHA = $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)

.DEFAULT_GOAL := help
.NOTPARALLEL:
.PHONY: help install lock env keygen version dev health test lint fix eval eval-list smoke spec-check
.PHONY: build compose-check up down logs ps reset check clean

help: ## Show this list
	@awk 'BEGIN { FS = ":.*## " } \
		/^##@/ { printf "\n%s\n", substr($$0, 5) } \
		/^[a-zA-Z_-]+:.*## / { printf "  %-14s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@printf '\nOptions: ARGS="..." adds options to test, fix, eval and logs; UV, COMPOSE, IMAGE can be overridden; CONFIRM=yes confirms reset.\n'

##@ Setup
install: ## Install locked dependencies (same as CI)
	$(UV) sync --locked

lock: ## Re-resolve dependencies and update uv.lock
	$(UV) lock

env: ## Create .env from .env.example (never overwrites an existing .env)
	@if [ -f .env ]; then echo ".env already exists, left unchanged"; \
	else cp .env.example .env && echo "created .env from .env.example: set OPENROUTER_API_KEY and API_KEYS (make keygen)"; fi

keygen: ## Print a new random key for API_KEYS
	@openssl rand -hex 32

version: ## Print the project version
	@$(UV) version --short

##@ Run
dev: ## Run the API locally with auto-reload (needs .env)
	$(UV) run fastapi dev main.py

health: ## Probe the running API (GET /)
	@curl -fsS $(API_URL)/ && echo

##@ Quality
test: ## Run the unit tests, offline (ARGS passes options)
	$(UV) run pytest -q $(ARGS)

lint: ## Check style and errors with ruff
	$(UV) run ruff check

fix: ## Auto-fix lint problems (ARGS passes options)
	$(UV) run ruff check --fix $(ARGS)

eval: ## Run the real-model evals (needs OPENROUTER_API_KEY, costs a few cents; ARGS passes options)
	$(UV) run pytest -m eval $(ARGS)

eval-list: ## List the eval cases without running them
	$(UV) run pytest -m eval --collect-only -q

smoke: ## Live-check the Wikipedia tool against the real API
	@$(UV) run python -c "from agent_wf.tools.wikipedia import search_wikipedia as t; print(t.invoke({'query': 'Eiffel Tower'}))"

spec-check: ## Validate all OpenSpec changes and specs (needs the openspec CLI)
	@command -v openspec >/dev/null || { echo "openspec CLI not found"; exit 1; }
	openspec validate --all --strict

##@ Docker
build: ## Build the image, tagged with the project version and git commit
	docker build --build-arg GIT_SHA=$(GIT_SHA) -t $(IMAGE):$(VERSION) .

compose-check: ## Validate docker-compose.yml (works without a .env)
	@created=; [ -f .env ] || { touch .env; created=1; }; \
	$(COMPOSE) config -q; rc=$$?; \
	[ -z "$$created" ] || rm -f .env; \
	exit $$rc

up: ## Start the API and the Langfuse stack in the background (needs .env with keys)
	GIT_SHA=$(GIT_SHA) $(COMPOSE) up -d --build

down: ## Stop the stack (keeps all data)
	$(COMPOSE) down

logs: ## Follow the stack's logs (ARGS=api for one service)
	$(COMPOSE) logs -f --tail=100 $(ARGS)

ps: ## Show the stack's containers and their health
	$(COMPOSE) ps

reset: ## DELETE the stack's data, incl. Langfuse traces, users and projects (needs CONFIRM=yes)
	@[ "$(CONFIRM)" = yes ] || { echo "refusing: this deletes the Langfuse data volumes (traces, users, projects). To confirm: make reset CONFIRM=yes"; exit 1; }
	$(COMPOSE) down -v

##@ Verify
check: install test lint build compose-check ## Run everything CI runs, in order (needs Docker running; no key or .env)

##@ Cleanup
clean: ## Remove caches and eval reports (nothing else)
	rm -rf .pytest_cache .ruff_cache tests/evals/results
	find . -path ./.venv -prune -o -type d -name __pycache__ -prune -exec rm -rf {} +
