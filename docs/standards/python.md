# Python Standards

These standards were written on June 2, 2026 using Context7. Verify currency before project start if found older than 6 months.

## Project Structure
- Use `src/` layout.
- Each module must be independently installable via `uv pip install -e`.

## Dependencies
- Use `uv` only.
- No `pip`, no `setup.py`.

## Imports
- Absolute imports preferred.
- Avoid circular dependencies.
- Add `from __future__ import annotations` to all modules.

## Type Hints
- Use built-in generics: `list[str]`, `dict[str, Any]`
- Use `X | None` instead of `Optional[X]`
- Import from `typing` as needed; `from __future__ import annotations` handles runtime.

## Type Checking (required, not optional)
- Run `pyright --strict` before commit.
- `mypy --strict` is allowed as an opt-in alternative.
- No `# type: ignore` without a justification comment.

## Code Rules
- No dynamic schema dicts crossing function boundaries.
- Use explicit models for structured data (see data_contracts.md).

## Formatting
- Line length: 120 characters.
- Use `ruff format`.

## Docstrings
- NumPy style for all public functions.

## Comments
- Only when logic is non-obvious.
- Must be full sentences.

## Naming
- `snake_case` for functions and variables.
- `PascalCase` for classes.

## Anti-patterns
- No overly generic abstractions for single-use code.
- No premature optimization.

## Execution
- Python 3.11+
- Ruff + type checker must pass before commit.
