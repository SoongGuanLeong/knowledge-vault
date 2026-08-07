# ADR-0005: Subprocess-aware test coverage with fast local tests and a CI coverage gate

- **Status:** accepted
- **Date:** 2026-08-07
- **Related:** Wayfinder map "Wayfinder: Honest CLI test coverage" (GitHub issue #49)

## Context

Every CLI test runs the kv tool as a subprocess (the `run_cli` fixture), but coverage was collected only in the pytest process. Subprocess executions were invisible to coverage, so the CLI seam reported 0% coverage (cli.py) and every CLI-reachable module was under-stated; the repo-wide `--cov-fail-under=56` gate was fake both locally and in CI. The honest numbers, once the subprocess is measured, are cli.py ~90% and repo total ~95%.

## Decision

- **Measure subprocesses via stock coverage.py** — set `COVERAGE_PROCESS_START` in the `run_cli` fixture env and ship a sitecustomize that calls `coverage.process_startup()`; configure `[tool.coverage.run] parallel = true` so pytest-cov auto-combines subprocess data files into the report. No pytest-cov extension needed.
- **Enforce gates outside pytest** — a per-module gate (`coverage report --include='*/cli.py' --fail-under=80`) plus a repo-wide gate (`--fail-under=85`), run from the Makefile and CI. The `--cov*` addopts are removed from pytest so plain `pytest` stays fast.
- **Workflow split** — `make test` runs fast pytest with no coverage; `make coverage` runs the full subprocess-aware measurement and both gates; CI runs `make coverage`. Coverage is a quality gate, not part of every edit.
- **Test only deterministic, user-triggerable failure branches.** Environment/infrastructure failure branches (git missing, partial-clone unsupported, remote unreachable, store unwritable) are documented, not mocked-and-tested, unless a future regression shows they need tests.

## Consequences

- Local iteration (`make test`) avoids the ~2x runtime cost of subprocess tracing; honest coverage is opt-in locally and always enforced in CI.
- The 56% gate was a false signal; it becomes a real 85% repo floor with cli.py >= 80% individually.
- Moving `--cov*` out of pytest addopts means plain `uv run pytest` no longer measures coverage — the explicit `make coverage` is the measurement path.
