# ADR-0001: Medallion store and generic repository acquisition

- **Status:** accepted
- **Date:** 2026-08-02
- **Related:** GitHub issue #1 (Project 0.1)

## Context

Project 0.1 builds a reproducible ingestion foundation for a future LLM-usable PKM. The first concrete goal is acquiring and organizing Apache Spark's official documentation. Two tensions needed resolving:

1. **Store layout.** The store must support many future source types (docs, APIs, source code, later PDFs/blogs/videos) without growing new top-level directories each time.
2. **Acquisition coupling.** The tool must not be a "Spark downloader"; acquisition should be generic, with downstream pipelines deciding what to extract.

## Decision

- Organize the knowledge store by **data maturity** using a medallion layout: `bronze/`, `silver/`, `gold/`, `cache/`. Every future source type flows through the same bronze → silver → gold lifecycle.
  - `bronze/<name>/<version>/repo/` + `manifest.json` — exact repository snapshot.
  - `silver/<name>/<version>/docs/` + `manifest.json` + `lineage.json` — byte-identical docs copy.
  - `gold/` — future indexes (FTS, vector, symbols, metadata). Not implemented.
- **Acquisition produces generic repository snapshots.** It knows nothing about documentation. A separate **docs pipeline** consumes the snapshot's configured `docs_path` and produces silver.
- **Version pinning.** Config declares `desired.tag`; acquisition resolves tag → commit → checkout. Manifests record `actual` (tag + commit + timestamp). No automatic latest resolution.
- **Partial clone** (`--filter=blob:none`) keeps snapshots cheap while retaining the full working tree.
- **Silver is byte-identical** in Project 0.1 — no normalization. Normalization is deliberately deferred to Project 0.2 (HTML/API docs pipeline).
- **Manifests are JSON.** Storage format is separate from future LLM context formatting (which may use token-optimized formats later).

## Consequences

- Adding a new project = adding a config file, no code changes.
- Adding a new source type (e.g. PDFs) = new pipeline feeding bronze→silver, no new top-level store dirs.
- Reproducibility: same config → same snapshot with complete provenance.
- Trade-off: byte-identical silver is less useful for retrieval until Project 0.2 adds normalization. Accepted to keep milestones single-challenge.
