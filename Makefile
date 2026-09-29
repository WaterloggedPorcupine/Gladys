.PHONY: check test test-integration fmt migrate eval eval-live

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run lint-imports
	uv run pytest -m "not integration" --cov-fail-under=85

test:
	uv run pytest -m "not integration"

test-integration:
	GLADYS_REQUIRE_INTEGRATION=1 uv run pytest -m integration --no-cov

fmt:
	uv run ruff check --fix .
	uv run ruff format .

migrate:
	uv run alembic upgrade head

eval:
	@echo "Offline evals begin in Phase 1"

eval-live:
	@echo "Live evals begin in Phase 1"
