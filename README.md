# knowledge-vault

A reproducible knowledge ingestion foundation for LLM-powered personal knowledge management.

`kv` is a CLI tool that acquires repository snapshots, extracts documentation into a byte-identical silver layer, and records complete provenance at every step — so the same configuration always reproduces the same knowledge snapshot.

---

## What it does

- **`kv init`** — create a new knowledge store
- **`kv discover <name>`** — list available versions (tags) of a configured source
- **`kv ingest <name>`** — acquire a pinned repository snapshot into bronze, extract docs into silver, build a gold index, write manifests
- **`kv list`** — show what's been ingested
- **`kv status [--deep]`** — check store for drift against declared source configs
- **`kv doctor`** — pre-flight environment and source config checks

## Source configuration

Each source is configured via a YAML file (`*`.yaml or `*.yml) in `sources/`:

```yaml
name: spark
repo: https://github.com/apache/spark.git
docs_path: docs
desired:
  tags:
    - v0.1.0
    - v0.2.0
```

## How it works

The store uses a medallion layout:

- **bronze** — full repository snapshot at a pinned commit, with a manifest recording provenance
- **silver** — byte-identical copy of the configured `docs_path` from bronze, with a manifest and lineage record
- **gold** — the store-level `knowledge.db` (SQLite/FTS5) built from the silver chunks artifact; deterministic contents for identical input

## Getting started

```bash
# Install
uv sync --extra dev

# Check quality
make check

# Initialize a store
kv init --store /path/to/store

# Discover available versions
kv discover spark --sources ./sources --store /path/to/store

# Ingest a pinned snapshot
kv ingest spark --sources ./sources --store /path/to/store

# List what's been ingested
kv list --store /path/to/store

# Check for drift
kv status --sources ./sources --store /path/to/store

# Pre-flight checks
kv doctor --sources ./sources --store /path/to/store
```

## Configuration precedence

CLI flag > environment variable > default:

| Setting | Flag | Env var | Default |
|---|---|---|---|
| Store location | `--store` | `KV_STORE` | `<project-root>/../knowledge-store` |
| Sources directory | `--sources` | `KV_SOURCES` | `<project-root>/sources` |

## Project structure

```
src/knowledge_vault/     # Python package
  cli.py                 # argparse CLI (init, discover, ingest, list, status, doctor)
  config.py              # Source config loading from YAML
  git.py                 # Git wrappers (tag discovery, clone, checkout)
  ingest.py              # Orchestration (bronze + silver + gold pipeline)
  store.py               # Store layout helpers (init, metadata, medallion dirs)
  pipeline/              # Stage-based pipeline (acquire, chunk, silver)
tests/                   # CLI-seam tests (fully offline, fixture git repos)
sources/                 # Per-source YAML config files
```

## Standards

- Python 3.11+, uv-only dependency management
- `src/` layout, ruff formatting/linting, basedpyright strict
- Tests run fully offline against local fixture git repos
- See `docs/standards/` for detailed rules

## License

MIT. See [LICENSE](LICENSE).
