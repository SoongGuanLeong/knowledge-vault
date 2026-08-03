.PHONY: help lint format typecheck test audit gitleaks check clean

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

lint: ## Run ruff linter.
	uv run ruff check .

format: ## Auto-format with ruff.
	uv run ruff format .

typecheck: ## Run basedpyright.
	uv run basedpyright

test: ## Run the test suite.
	uv run pytest

audit: ## Run pip-audit for dependency vulnerabilities.
	uv run pip-audit

gitleaks: ## Run gitleaks to detect secrets.
	gitleaks detect --source . -v

check: ## Run all quality checks (gitleaks, format check, lint, typecheck, test, audit).
	gitleaks detect --source . -v
	uv run ruff format --check .
	uv run ruff check .
	uv run basedpyright
	uv run pytest
	uv run pip-audit

clean: ## Remove caches and build artifacts.
	rm -rf .pytest_cache .ruff_cache .pyright_cache .mypy_cache .coverage htmlcov
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
