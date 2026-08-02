# AGENTS.md

## Environment

### Recommended: WSL2 on Windows
- Windows users: use WSL2 (Ubuntu) for development. Native Windows is unsupported.
- macOS / Linux: use directly.

### Project location
- Keep all projects under `~/projects`.
- Use Linux paths; never use `/mnt/*` for project files.

---

## Engineering Principles

### Think Before Coding
- State assumptions explicitly.
- Surface ambiguity; do not guess.
- If unclear, ask or present options.
- Prefer simpler alternatives when valid.

### Simplicity First
- Implement only what is requested.
- No speculative features or abstractions.
- Avoid over-engineering.

### Goal-Driven Execution
For non-trivial tasks:
1. Define success criteria.
2. Outline a short plan.
3. Execute step-by-step with verification.

---

## Communication Style

### Be extremely concise. sacrifice grammar for the sake of concision.

When the user asks a question, answer in as few words as possible. Drop filler, articles, and pleasantries unless they add meaning. Do not summarize unless asked. Do not explain unless asked.

---

## Change Safety Rules

- Do not refactor unrelated code.
- Do not "improve" code outside the scope of the task.
- Every change must directly map to a stated requirement.
- Keep edits minimal and traceable.

---

## Tooling

- Use Makefile targets for operations (see `Makefile`).
- Technical rules (language, testing, infrastructure) live in `docs/standards/`. Read the relevant standards before implementing.

---

## Completion Criteria

Before marking work complete:
- Run `make lint`.
- If a `test` target exists, run `make test`.
- Confirm success criteria are satisfied.
- Do not assume success without verification.

---

## Session Rules

### Session start
1. Read `AGENTS.md` (this file).
2. Read relevant files in `docs/standards/` for the current task.
3. If `CONTEXT.md` exists, read it for domain vocabulary.
4. If `docs/adr/` exists, skim for in-force architectural decisions.

### During the session
- When new domain terms emerge, add them to `CONTEXT.md` (create lazily if absent).
- When a durable architectural decision is made, write `docs/adr/NNNN-title.md` (create dir lazily if absent).
- When a feature needs a PRD, run the `to-prd` skill.

### Session end
- Run the `handoff` skill to capture session state for the next agent.

---

## Documentation Boundaries

- `AGENTS.md` defines behavior rules only.
- Technical standards live in `docs/standards/`.
- Do not assume implementation details not defined in this file or standards docs.

---

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical role names (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
