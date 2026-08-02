# Domain Glossary

Single-context vocabulary for this repo. Terms are the shared language used across code, docs, and issues.

## Store layers

- **knowledge-store** — the generated machine data produced by ingestion; lives outside the code repo.
- **bronze** — first store layer: exact repository snapshots acquired at a pinned commit. Append-only raw material.
- **silver** — second store layer: selected artifacts extracted from bronze (e.g. documentation copies). Adds provenance.
- **gold** — third store layer: derived indexes over silver (FTS, vector, symbols, metadata). Not yet implemented.
- **cache** — transient store area.

## Acquisition

- **source** — a configured project to acquire knowledge from (e.g. Apache Spark). Declared in a per-source YAML file.
- **repository snapshot** — a full generic checkout of a source repo at an exact commit. Acquisition knows nothing about docs vs. code.
- **partial clone** — `git clone --filter=blob:none`; full working tree with lazy blob fetching, so snapshots are cheap.
- **desired** — the intent declared in config (e.g. `desired.tag: v4.1.3`).
- **actual** — what was really acquired, recorded in the manifest (resolved tag + commit SHA + timestamp).
- **manifest** — an immutable JSON record of exactly what was acquired/extracted and when.
- **lineage** — provenance record linking a silver artifact to the bronze snapshot that produced it.
- **ingest** — the pipeline that runs acquisition (→ bronze) and the docs pipeline (→ silver).
- **version pinning** — tags pinned in config; acquisition is deterministic; updates are deliberate config edits.

## Pipelines

- **docs pipeline** — the step that selects a snapshot's `docs_path` and copies it byte-identically into silver. No transformation.
- **knowledge-vault** — this code repo (the Python application).
- **engineering-vault** — future Obsidian vault; the human-curated knowledge layer.
