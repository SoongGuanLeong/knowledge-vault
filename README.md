# knowledge-vault

A reproducible knowledge ingestion foundation for LLM-powered personal knowledge management.

`kv` is a CLI tool that acquires repository snapshots, extracts documentation into a byte-identical silver layer, and records complete provenance at every step — so the same configuration always reproduces the same knowledge snapshot.

---

## What it does

- **`kv discover <name>`** — list available versions (tags) of a configured source
- **`kv ingest <name>`** — acquire a pinned repository snapshot into bronze, extract docs into silver, write manifests
- **`kv list`** — show what's been ingested

## How it works

The store uses a medallion layout:

- **bronze** — full repository snapshot at a pinned commit, with a manifest recording provenance
- **silver** — byte-identical copy of the configured `docs_path` from bronze, with a manifest and lineage record
- **gold** — derived indexes (not yet implemented)

Each source is configured via a YAML file in `sources/`:

```yaml
name: spark
repo: https://github.com/apache/spark.git
docs_path: docs
desired:
  tag: v4.1.3
```

## Getting started

```bash
# Install
uv sync --extra dev

# Check quality
make check

# Discover available versions
kv discover spark

# Ingest a pinned snapshot
kv ingest spark

# List what's been ingested
kv list
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
  cli.py                 # argparse CLI (discover, ingest, list)
  config.py              # Source config loading from YAML
  git.py                 # Git wrappers (tag discovery, clone, checkout)
  ingest.py              # Orchestration (bronze + silver pipeline)
  store.py               # Store layout helpers
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
