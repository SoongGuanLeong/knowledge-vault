.PHONY: help lint format typecheck test check clean

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

lint: ## Run ruff linter.
	uv run --extra dev ruff check .

format: ## Auto-format with ruff.
	uv run --extra dev ruff format .

typecheck: ## Run basedpyright.
	uv run --extra dev basedpyright

test: ## Run the test suite.
	uv run --extra dev pytest

check: ## Run all quality checks (format check, lint, typecheck, test).
	uv run --extra dev ruff format --check .
	uv run --extra dev ruff check .
	uv run --extra dev basedpyright
	uv run --extra dev pytest

clean: ## Remove caches and build artifacts.
	rm -rf .pytest_cache .ruff_cache .pyright_cache .mypy_cache .coverage htmlcov
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
