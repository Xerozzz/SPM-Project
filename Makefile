# Convenience wrapper around the docker compose commands in AGENTS.md §8.
# Everything runs inside the containers, so you need no local Python or Node toolchain.
# Windows without make: run the docker compose command from the recipe directly, or use WSL.

.PHONY: up down test lint fmt migrate revision seed

up:  ## Build and start web + api + db
	docker compose up --build

down:  ## Stop the stack (add ARGS=-v to wipe the database volume)
	docker compose down $(ARGS)

test:  ## Backend tests with the coverage gate from AGENTS.md §4
	docker compose run --rm api pytest --cov=. --cov-report=term-missing --cov-fail-under=90
	npm --prefix web run test -- --run

lint:  ## ruff + mypy on the backend, eslint + tsc on the frontend
	docker compose run --rm api sh -c "ruff check . && ruff format --check . && mypy ."
	npm --prefix web run lint
	npm --prefix web run typecheck

fmt:  ## Autoformat both sides
	docker compose run --rm api sh -c "ruff format . && ruff check --fix ."
	npm --prefix web run fmt

migrate:  ## Apply all migrations to the running database
	docker compose run --rm api alembic upgrade head

revision:  ## Create a migration: make revision m="add users table"
	docker compose run --rm api alembic revision --autogenerate -m "$(m)"

seed:  ## Seed one user per role for local development
	@echo "scripts/seed.py lands with the auth story (US-1). Nothing to seed yet."
