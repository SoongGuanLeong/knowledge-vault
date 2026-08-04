# ADR-0002: Minimal pipeline skeleton with stage boundaries

- **Status:** accepted
- **Date:** 2026-08-03
- **Related:** Project 0.1 (complete), Project 0.2 (Silver extraction pipeline)

## Context

Project 0.1 is complete. The handoff recommends turning the knowledge vault into an actual knowledge platform, with a roadmap through 9 more projects (Silver extraction, parsing, chunking, search, embeddings, hybrid search, LLM integration, more sources, gold layer).

Before implementing Project 0.2, introduce a pipeline abstraction boundary. The codebase is small (~150 lines in `ingest.py`), so refactoring now is cheap. Delaying would force painful migration after adding extraction, chunking, embeddings, and indexing stages.

We want stable stage boundaries so future work naturally flows:

```
Acquire → Bronze → Extract → Silver → Chunk → Index → Gold
```

## Decision

- Introduce a `pipeline/` module (a subpackage under `src/knowledge_vault/`) containing:
  - `context.py` — `PipelineContext` dataclass carrying store path, source config, and resolved version/commit. Immutable; passed between stages.
  - `acquire.py` — `AcquireStage` class extracting the current acquisition logic from `ingest.py` into a class with an `execute(ctx) -> bool` contract (returns True if newly acquired, False if skipped).
  - `silver.py` — `SilverStage` class performing selective extraction of documentation files (`.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, `.html`) from bronze into silver, excluding binary assets. Generates `manifest.json` with extraction inventory (included files with checksums + skipped files with reasons) and `lineage.json` with provenance.
  - `__init__.py` — re-exports for convenience.
- Refactor `ingest.py` to use the new pipeline modules. The public `ingest()` API stays the same; CLI behavior is unchanged.
- Do **not** introduce plugin systems, abstract base classes, configurable DAGs, or any other machinery beyond what's needed for the immediate next two projects. Stages are plain classes with an `execute` method.
- No new dependencies.

## Consequences

- Future milestones (Extract/Silver, Chunk, Index, Gold) can add new stage classes alongside `AcquireStage` and wire them sequentially in `ingest.py` without touching acquisition code.
- The pipeline is concrete and simple — no abstraction tax. When/if the pipeline grows complex enough to warrant a framework, the transition is localized.
- All 29 existing tests continue to pass (updated 2 tests to reflect selective extraction behavior replacing byte-identical copy).