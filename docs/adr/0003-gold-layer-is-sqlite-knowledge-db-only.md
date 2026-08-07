# ADR-0003: Gold layer is SQLite knowledge.db only (JSON gold index retired)

- **Status:** accepted
- **Date:** 2026-08-07
- **Related:** GitHub issue #29 (Implement SQLite IndexStage), #36, #37, #38, #39

## Context

Project 0.5 introduced a SQLite `gold/knowledge.db` (FTS5) as the gold retrieval surface, with a frozen schema (`docs/standards/` + `retrieval/schema.py`) and a store-level `indexed_sources` registry carrying provenance.

The original JSON gold-index stage — a per-source+version `index/metadata.json` writer in `pipeline/index.py` — predates the SQLite path and was superseded by it: the ticket wording ("replacing the current JSON-index output path") made SQLite the only gold writer. Keeping both writers means two competing gold contracts, duplicated skip/determinism logic, and a second provenance store.

## Decision

- The gold layer has exactly one writer: the SQLite `IndexStage` in `retrieval/indexing.py`, writing store-level `gold/knowledge.db`.
- Delete the JSON gold-index stage module (`pipeline/index.py`), its package export, and its tests.
- Delete the per-source+version gold-path plumbing that existed only for the JSON writer: `gold_dir` (store helper) and `gold_path` (`PipelineContext` field). Gold is store-level, not per-source+version.

## Consequences

- Single gold contract; no competing `index/metadata.json` format to maintain.
- `gold/` remains a store-level directory (via `MEDALLION_DIRS`) housing `knowledge.db`.
- Removing `gold_path`/`gold_dir` is a public API surface change on `PipelineContext`; downstream consumers must use `knowledge_db_path(ctx.store)` instead.
