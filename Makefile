.PHONY: help lint format typecheck test audit gitleaks semgrep check clean

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

# Ignored pip-audit advisories:
# PYSEC-2026-3481/3482/3483 in mcp==1.23.3 — pinned exactly by semgrep (its optional MCP-server feature);
# the mcp package is not exercised by the CLI scan path, so the advisories are not reachable.
PIP_AUDIT_IGNORES := --ignore-vuln PYSEC-2026-3481 --ignore-vuln PYSEC-2026-3482 --ignore-vuln PYSEC-2026-3483

audit: ## Run pip-audit for dependency vulnerabilities.
	uv run pip-audit $(PIP_AUDIT_IGNORES)

gitleaks: ## Run gitleaks to detect secrets.
	gitleaks detect --source . -v

semgrep: ## Run semgrep SAST scan.
	uv run semgrep scan --config auto --error

check: ## Run all quality checks (gitleaks, format check, lint, typecheck, test, bandit, semgrep, audit).
	gitleaks detect --source . -v
	uv run ruff format --check .
	uv run ruff check .
	uv run basedpyright
	uv run pytest
	uv run bandit -r src/ -c pyproject.toml
	uv run semgrep scan --config auto --error
	uv run pip-audit $(PIP_AUDIT_IGNORES)

clean: ## Remove caches and build artifacts.
	rm -rf .pytest_cache .ruff_cache .pyright_cache .mypy_cache .coverage htmlcov
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
