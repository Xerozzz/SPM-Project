# Convenience wrapper around the docker compose commands in AGENTS.md §8.
# Every recipe runs inside a container, so Docker is the only tool you need installed.
# The exception is Playwright, which drives a real browser on your machine — see the README.
# Windows without make: run the docker compose command from the recipe directly, or use WSL.
#
# --no-deps on the web recipes: eslint, tsc and vitest never touch the API or the
# database, so there is no reason to spin the rest of the stack up to run them.

.PHONY: up down test lint fmt migrate revision seed

up:  ## Build and start web + api + db
	docker compose up --build

down:  ## Stop the stack (add ARGS=-v to also wipe the database volume)
	docker compose down $(ARGS)

test:  ## Backend tests with the coverage gate from AGENTS.md §4, then frontend tests
	docker compose run --rm api pytest --cov=. --cov-report=term-missing --cov-fail-under=90
	docker compose run --rm --no-deps web sh -c "npm run test -- --run"

lint:  ## ruff + mypy on the backend, eslint + tsc on the frontend
	docker compose run --rm api sh -c "ruff check . && ruff format --check . && mypy ."
	docker compose run --rm --no-deps web sh -c "npm run lint && npm run typecheck"

fmt:  ## Autoformat both sides
	docker compose run --rm api sh -c "ruff format . && ruff check --fix ."
	docker compose run --rm --no-deps web npm run fmt

migrate:  ## Apply all migrations to the running database
	docker compose run --rm api alembic upgrade head

revision:  ## Create a migration: make revision m="add users table"
	docker compose run --rm api alembic revision --autogenerate -m "$(m)"

seed:  ## Seed one user per role for local development
	@echo "scripts/seed.py lands with the auth story (US-1). Nothing to seed yet."
