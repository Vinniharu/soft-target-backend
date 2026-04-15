.PHONY: dev test lint fmt migrate migration create-admin typecheck check

dev:
	uv run uvicorn app.main:app --reload --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run mypy app

fmt:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy app

migrate:
	uv run alembic upgrade head

migration:
	@if [ -z "$(name)" ]; then echo "usage: make migration name=\"describe change\""; exit 1; fi
	uv run alembic revision --autogenerate -m "$(name)"

create-admin:
	uv run softtarget create-admin

check: fmt lint test
