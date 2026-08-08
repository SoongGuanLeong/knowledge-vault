# ADR-0006: Unit of state and fact lifecycle

- **Status:** accepted
- **Date:** 2026-08-08
- **Related:** GitHub issue #56 (Decide the unit of state), part of wayfinder map #55

## Context

KV is hypothesized as a knowledge-state layer between agents and underlying data stores. The state unit determines the shape of `current()`, `history()`, `update()`, `remember()`, and `context()` — and therefore the data model Experiment 0 must test. The DB-capabilities research (#57) showed every knowledge-state guarantee except valid-window integrity is application code in PG and SQLite, so the unit must be chosen where claims, retraction, and contradiction are first-class.

## Decision

The **fact** is the semantic unit of KV: an immutable assertion `(subject, predicate, object)` with optional evidence and provenance. Documents and chunks are the ingestion and evidence layer, never the state unit. Fact changes are recorded as immutable history via supersession; agents read a materialized current-state projection.

```
WORLD → docs/sources → chunks/evidence → FACTS (semantic unit) → fact history (supersession) → current projection (read surface)
```

### Fact identity

Deterministic assertion dedup on canonical `(subject, predicate, object)` identity; provenance/evidence is *merged* into the fact, not part of its identity. Source is evidence, not identity. This is a dedup rule, not a physical `UNIQUE(subject, predicate, object)` schema constraint — identical-looking assertions may still carry distinct provenance context.

### Evidence / provenance

Optional `EvidenceRef[]` on each fact. Refs merge on dedup (a fact's evidence grows as more sources assert the same triple).

### Supersession

`update(slot, new_object)` asserts a successor fact carrying a `supersedes` link to the slot's current fact. `retract(slot)` retires the current fact with no successor. The `⊥` sentinel is an internal mechanism only, not part of the public contract — it avoids conflating unknown / null / missing / deleted / retracted.

### Conflict behavior

`current()` returns the head of a slot's supersession chain. When two facts claim the same slot and neither supersedes the other, the conflict is **surfaced**, never silently arbitrated. The engine never picks a winner at read time.

### Deterministic/semantic boundary

Engine-enforced (deterministic): dedup by canonical `(s,p,o)`, evidence merge, slot grouping, head-of-chain resolution, hashing, atomicity. LLM/user-decided (semantic): fact extraction, slot choice, supersession, contradiction. The engine never scores and never picks winners.

### Why event sourcing is deferred

The write model is immutable facts + a supersession table. Full replayable event sourcing is deferred until Experiment 0 demonstrates that event sourcing's benefits justify its machinery.

## Consequences

- `context()` consumes the current/provenance-aware layer, not raw chunks; its contract is defined in #60.
- `remember()` extracts facts from chunks with evidence refs (Phase 5, deferred).
- Source trust / ingestion verification (what may create facts) is a separate concern, ticketed as #63.
- The deterministic/semantic boundary here is what the plain-DB attack (#59) and Experiment 0 (#61) must test.
