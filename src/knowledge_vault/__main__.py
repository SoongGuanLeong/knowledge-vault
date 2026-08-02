"""Allow running the CLI via `python -m knowledge_vault`."""

from __future__ import annotations

from knowledge_vault.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
