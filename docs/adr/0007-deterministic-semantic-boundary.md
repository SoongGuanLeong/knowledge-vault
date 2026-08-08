# ADR-0007: The deterministic/semantic boundary

- **Status:** accepted
- **Date:** 2026-08-08
- **Related:** GitHub issue #58 (Bound deterministic vs semantic responsibility), part of wayfinder map #55

## Context

ADR-0006 fixed the fact as the unit of state and sketched a deterministic/semantic split, but the boundary itself was not sharp: which operations the engine may perform on its own, and which require an explicit semantic decision supplied by the LLM/user. The plain-DB attack (#59) and Experiment 0 (#61) must test this boundary, so it has to be stated precisely enough to implement and falsify.

## Decision

**The engine may enforce semantics that have already been made explicit; it may not infer semantics.**

The line is the *derivable-from-store* test: the engine may compute anything recomputable from the facts and stored policies alone, with no knowledge of the world outside the store. Anything requiring world knowledge — meaning, contradiction, supersession intent, concept identity, preference — is semantic, supplied by the LLM/user as an explicit recorded decision that the engine then enforces deterministically.

Concretely, per signal:

| Signal | Side | Rationale |
|---|---|---|
| Fact identity / dedup (canonical `(s,p,o)`) | Deterministic | Exact stored identity; no fuzzy matching |
| Concept identity (e.g. "Apache Spark" == "Spark") | Semantic | Caller resolves before write; engine never fuzzy-matches |
| Evidence / provenance merge | Deterministic | Merge refs on dedup |
| Supersession target | Semantic (explicit input) | Caller's `update()` asserts a successor; engine records it, defaulting to current head |
| Supersession-chain integrity (acyclicity, single-parent, existence checks) | Deterministic | Engine enforces the consequence of the caller's decision |
| Timestamps / temporal ordering | Deterministic | Engine-assigned monotonic sequence; ordering never judged |
| Current-version (head-of-chain) selection | Deterministic | Recomputed from stored supersedes links |
| Conflict detection | Deterministic | Structural: two heads in the same slot, neither superseding |
| Contradiction classification | Semantic | Whether two facts are contradictory is meaning, not structure |
| Conflict surfacing | Deterministic | Persistent conflict record; `current()` never returns an ambiguous answer |
| Retention / indexing / filtering / access control | Policy definition semantic; enforcement deterministic | Policies are stored config decided by the operator/LLM; engine enforces them |
| Change detection | Deterministic | Hash compare |
| Ranking | Deterministic only | Engine never scores; ordering by chain position / sequence only |
| Source trust / quarantine | Deferred to #63 | Policy, not engine inference |

### The enforcement loop

When a semantic decision arrives (e.g. "fact B supersedes fact A"), the engine validates it deterministically — does B exist, does A exist, same slot, would this create a cycle — then commits. The engine enforces the consequence of the semantic decision; it never makes the decision.

### Layering

- **Source layer** (Q9/#63): provenance, integrity, trust policy, quarantine — decides *what KV will admit*.
- **Knowledge layer** (#56): facts, supersession, conflicts, `current()` — decides *what KV believes/stores*.
- **Semantic coprocessor** (LLM/user) sits above both: decides what a document means, extracts facts, resolves concepts, proposes supersession, resolves conflicts. The deterministic KV engine sits below it.

## Consequences

- `current()` is always deterministic: a conflict is a persistent record, never an ambiguous read.
- Dedup is exact-identity only; concept resolution happens before write.
- `update()`/`retract()` take a caller-supplied semantic decision and enforce its structural consequences.
- Experiment 0 (#61) and the plain-DB attack (#59) test this boundary: anything KV's engine does must be recomputable from stored facts and policies.
