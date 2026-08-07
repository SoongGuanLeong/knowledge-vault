# Contributing

## Workflow

1. Branch.
2. Make your change.
3. Run `make check`.
4. Open a PR with a clear description of what changed and why.

## Style

- Keep edits minimal and traceable (per `AGENTS.md` Change Safety Rules).
- Don't refactor unrelated parts of the starter in the same PR.

## Quality checks

`make check` runs the full suite in this order:

| Order | Tool | Purpose |
| ----: | ---- | ------- |
| 1 | gitleaks | Prevent committing secrets |
| 2 | ruff format `--check` | Verify formatting |
| 3 | ruff check | Linting and code quality |
| 4 | basedpyright | Static type checking |
| 5 | pytest | Functional correctness |
| 6 | bandit | Security scan |
| 7 | semgrep | Deterministic SAST scan |
| 8 | pip-audit | Dependency vulnerability scan |

Pre-commit hooks cover gitleaks, ruff format, and ruff check for fast local feedback.
