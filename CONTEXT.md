# Domain Glossary

Single-context vocabulary for this repo. Terms are the shared language used across code, docs, and issues.

## Store layers

- **knowledge-store** — the generated machine data produced by ingestion; lives outside the code repo.
- **bronze** — first store layer: exact repository snapshots acquired at a pinned commit. Append-only raw material.
- **silver** — second store layer: documentation files extracted from bronze via selective extraction (only `.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, `.html` files). Includes `manifest.json` with extraction inventory and `lineage.json` with provenance.
- **gold** — third store layer: derived indexes over silver (FTS, vector, symbols, metadata). Not yet implemented.
- **cache** — transient store area.

## Acquisition

- **source** — a configured project to acquire knowledge from (e.g. Apache Spark). Declared in a per-source YAML file.
- **repository snapshot** — a full generic checkout of a source repo at an exact commit. Acquisition knows nothing about docs vs. code.
- **partial clone** — `git clone --filter=blob:none`; full working tree with lazy blob fetching, so snapshots are cheap.
- **desired** — the intent declared in config (e.g. `desired.tags: [v4.1.3, v3.5]`). Plural form supports multi-version ingestion.
- **actual** — what was really acquired, recorded in the manifest (resolved tag + commit SHA + timestamp).
- **requested_tag** — the specific tag being ingested in a single-ingest context (via `--tag` override).
- **manifest** — an immutable JSON record of exactly what was acquired/extracted and when.
- **lineage** — provenance record linking a silver artifact to the bronze snapshot that produced it.
- **ingest** — the pipeline that runs acquisition (→ bronze) and the docs pipeline (→ silver).
- **version pinning** — tags pinned in config; acquisition is deterministic; updates are deliberate config edits.
- **store initialization** — running `kv init` creates the medallion directory structure (`bronze/`, `silver/`, `gold/`, `cache/`) and `metadata.json` at the store root.
- **store schema version** — integer in `metadata.json` recording the store format version; current = 1.

## Pipelines

- **docs pipeline** — the step that selects a snapshot's `docs_path` and copies it byte-identically into silver. No transformation.
- **pipeline** — the orchestrated sequence of stages (Acquire → Bronze → Silver → Chunk → Index → Gold). Introduced in Project 0.15 as a minimal skeleton.
- **stage** — one processing unit in the pipeline (e.g. `AcquireStage`, `SilverStage`). Each has an `execute(ctx)` method.
- **PipelineContext** — immutable dataclass carrying store path, source config, tag, version, commit, and all precomputed sub-paths. Passed between stages.
- **selective extraction** — Silver copies only documentation files (`.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, `.html`) from bronze, excluding binary assets. Bronze remains the source of truth.
- **extraction inventory** — manifest sub-structure listing `included` files (with checksum, source, destination) and `skipped` files (with reason), along with `total_files_discovered`.
- **extraction_patterns** — the list of doc extensions used for selective extraction in the Silver stage.
- **knowledge-vault** — this code repo (the Python application).
- **engineering-vault** — future Obsidian vault; the human-curated knowledge layer.

## Retrieval

- **retrieval** — the search API layer (`src/knowledge_vault/retrieval/`): engine-agnostic surface over the gold `knowledge.db`.
- **SearchBackend** — `typing.Protocol` with a single sync method `search(query, *, k=10, filters=None) -> list[SearchResult]`. Never exposes connection/cursor; SQL owned by the backend.
- **SearchResult** — frozen dataclass: `chunk_uuid, text, source, version, path, start_line, end_line, score`. `score` higher = more relevant (backend normalizes raw bm25). No rank/snippet/document_id.
- **SearchFilters** — frozen dataclass `source: str | None, version: str | None`. None = all; unknown filter value = empty result (CLI validates typos).
- **slice** — the `(source, version)` unit of identity and replacement in the gold index. A slice is the set of documents and chunks indexed for one source at one version; it is the thing that is up-to-date checked (via `chunks_sha256`), atomically replaced in place when its chunks change, and isolated from other slices during replacement (delete cascades only that slice's chunks, FTS is rebuilt, the `indexed_sources` row is updated — all within one transaction). Stale-by-default: only the changed slice is rewritten, leaving other slices untouched. See also **indexed-slices**.
- **indexed-slices** — the registry lookup for what `(source, version)` slices have been indexed into `knowledge.db`. Backed by the `indexed_sources` table (rows: `chunks_sha256`, document/chunk counts); surfaced as the typed `IndexedSlices` answer (distinct sources + versions derivable without re-query). Each entry is the registry record for one **slice**.
- **indexed_sources** — build registry inside `knowledge.db`: `(source, version)` PK, `chunks_sha256`, document/chunk counts. Provenance lives in the DB, no gold-side manifest. Each row is the registry record for one **slice**.
- **chunk_uuid** — deterministic UUID5 identity for a chunk; the external id returned by SearchResult (not the SQLite rowid alias).

## Knowledge state

- **fact** — the semantic unit of knowledge-state (per ADR-0006): an immutable assertion `(subject, predicate, object)` with optional evidence and provenance. KV stores and resolves facts, not documents or chunks.
- **slot** — the read/grouping concept a supersession chain hangs off: one `(subject, predicate)` grouping. Not the fact identity; facts of a slot are linked by `supersedes`.
- **supersession** — the relation linking a successor fact to the fact it replaces within a slot. `update()` asserts a successor; `retract()` retires the current fact with no successor.
- **current projection** — the materialized read surface of the heads of all slots' supersession chains; what `current()` and `context()` read. Deterministic, not scored.
- **evidence** — optional references from a fact to the chunks/sources that support it, with provenance (source, document, chunk, content hash, trust class). Merged on dedup; source is evidence, not identity.
- **conflict record** — the persistent record written when two facts claim the same slot and neither supersedes the other. Structural detection is deterministic; contradiction classification is semantic. `current()` never returns an ambiguous read.
- **semantic coprocessor** — the LLM/user layer above the deterministic KV engine: decides what a document means, extracts facts, resolves concepts, proposes supersession, resolves conflicts. The engine enforces these explicit decisions; it never infers semantics.

## CLI operations

- **kv init** — creates the medallion store structure and ``metadata.json``.
- **kv ingest** — acquires source snapshots into bronze and copies docs into silver. Additive-only, idempotent. Supports ``--tag`` for single-version override.
- **kv status** — offline audit comparing source configs against store manifests. Reports missing, stale, and drift. Exit 0 (healthy) / 1 (drift). ``--deep`` verifies remote commits.
- **kv doctor** — pre-flight checks (git, partial-clone support, YAML validity, remote reachability, store writability, schema compat). Reports PASS/WARN/FAIL. Exit 0 (all pass) / 1 (any fail).
- **kv discover** — lists available tags for a source on the remote.
- **kv list** — lists all ingested source versions in the store.
- **kv search** — full-text search over the gold index. ``kv search [--store] [--source] [--version] [--limit] query`` (positional FTS5 query). Default: all sources+versions; ``--version`` independent of ``--source``; ``--limit`` = k, default 10. Exit 0 found / 1 none / 2 error (bad args, unknown source/version, missing/incompatible db). Output: ranked blocks (rank=position, source@version, path:start-end, snippet), no score. Snippet from ``snippet.py``: whitespace-tokenize query, strip FTS5 syntax + stopwords, fixed ``SNIPPET_WINDOW_CHARS`` window at first term match, ANSI highlight only on TTY.
