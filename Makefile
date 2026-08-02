.PHONY: help lint format clean

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

lint: ## Run ruff and pyright.
	uv run --extra dev ruff check .
	uv run --extra dev pyright

format: ## Auto-format with ruff.
	uv run --extra dev ruff format .
	uv run --extra dev ruff check --fix .

# `test` target is not defined: a starter with no tests would always fail.
# When you add tests under tests/, add:
#   test:
#       uv run --extra dev pytest

clean: ## Remove caches and build artifacts.
	rm -rf .pytest_cache .ruff_cache .pyright_cache .mypy_cache .coverage htmlcov
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
