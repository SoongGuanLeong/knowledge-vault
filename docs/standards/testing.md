# Testing Standards (pytest)

These standards were written on June 2, 2026 using Context7. Verify currency before project start if found older than 6 months.

## Coverage
- Every non-trivial function must have tests.
- Must include failure paths.
- Minimum 80% line coverage for new code (enforce via `pytest-cov`).

## Test Types
- **Unit**: isolated with mocked dependencies (`pytest-mock`).
- **Integration**: real services via `pytest.fixture` with scoped setup/teardown.
- Keep unit tests fast (<100ms each).

## Fixtures
- Use `conftest.py` for shared fixtures.
- Prefer `pytest.fixture` scope (`function`, `module`, `session`) over manual setup.
- Use `pytest-asyncio` for async code.

## Rules
- No silent test failures.
- Setup errors must raise immediately.

- Use `pytest.raises` for expected exceptions, not `try/except`.

## Execution
- Use pytest only.
- Tests live under `tests/` per module.