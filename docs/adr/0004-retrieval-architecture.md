# ADR-0004: Retrieval architecture — gold serving artifact, chunks.jsonl canonical, SearchBackend abstraction

- **Status:** accepted
- **Date:** 2026-08-07
- **Related:** Project 0.5; GitHub issues #23 (research), #24 (schema), #25 (SearchBackend contracts), #26 (IndexStage rebuild), #28 (schema module), #30 (SQLiteFTSBackend), #31 (surface contract tests), #41/#42 (IndexStage implementation)

## Context

Project 0.5 ships keyword retrieval over the knowledge store. The architecture had to resolve three tensions:

1. **What is the deterministic artifact?** Gold must be reproducible and rebuildable. If gold is byte-deterministic, every index detail (SQLite segment layout, FTS merge history) becomes part of the contract and engine swaps become impossible.
2. **Where does the retrieval surface live?** A SQLite-specific schema, or an engine-agnostic API that leaves room for other backends (Tantivy, FAISS)?
3. **What is the unit of identity and replacement?** Documents and chunks are indexed per source+version; a store can hold several versions of the same source.

## Decision

- **Gold owns serving artifacts; Silver owns the deterministic dataset.** Gold's artifact is the store-level `gold/knowledge.db` — a SQLite retrieval database derived from silver, not a hand-authored dataset. It is fully reproducible (bronze → silver → chunks → db); delete-and-rebuild is the repair story.
- **`chunks.jsonl` is the canonical deterministic dataset.** Produced by the ChunkStage, stored at `silver/<src>/<ver>/chunks/chunks.jsonl`. It is never duplicated and survives backend swaps: the same chunks feed any retrieval engine. `knowledge.db` is a projection of it, not a second source of truth.
- **Store-level `knowledge.db` with `source`+`version` columns.** One database per store, not per source+version. Rows in `documents` and `chunks` carry source/version (via join), and `indexed_sources` records provenance per (source, version). Unit of replacement = one source+version slice. This keeps cross-version search possible and leaves room for later dedup / prefer-latest policies.
- **`SearchBackend` abstraction; backend swap = IndexStage rewrite only.** The retrieval surface is a `typing.Protocol` with a single sync `search(query, *, k, filters) -> list[SearchResult]`. The API never reveals storage — no connection/cursor escape, SQL owned by the backend. Swapping engines means rewriting the IndexStage that populates the new artifact; `chunks.jsonl` and the retrieval surface stay unchanged.
- **SQLite/FTS5 lexical choice for 0.5; vectors deferred to 0.6.** Keyword search uses SQLite FTS5 with the `unicode61` tokenizer and BM25 ranking. Embeddings (vector index) are deferred to Project 0.6; the schema keeps room (e.g. embedding metadata columns on `indexed_sources`) but does not build them.

## Consequences

- Determinism is scoped: same `chunks.jsonl` + same SQLite version → same relational contents + same search results. `knowledge.db` is **not** byte-identical across SQLite versions or segment-merge history — accepted, because `chunks.jsonl` is the deterministic artifact.
- Rebuild-not-migrate: schema bumps are handled by delete-and-rebuild of `gold/knowledge.db`, never by in-place migration. A future `kv index --prune` can reconcile stale slices at the orchestration layer.
- The 0.4 JSON gold index (`index/metadata.json`) is superseded and retired (ADR-0003), not migrated.
- Adding a non-SQLite backend later is additive: new IndexStage + new backend implementation behind the same `SearchBackend` protocol; no upstream change.
- Search-all-by-default with first-class filters: unknown filter values return empty results, and the CLI validates against `indexed_sources`.
