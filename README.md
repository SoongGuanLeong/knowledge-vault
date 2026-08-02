# template

A general-purpose Python project starter. Not a Copier template, not a generator — just a folder you copy and start from.

---

## What's here

- **`AGENTS.md`** — behavior policy for AI coding agents
- **`docs/standards/`** — technical rules (Python, testing, infrastructure)
- **`docs/agents/`** — domain and issue-tracker conventions
- **`Makefile`** — `make help`, `make lint`, `make format`, `make clean`
- **`pyproject.toml`** — uv + ruff + pyright + pytest
- **`opencode.jsonc`** — AI agent config (MCPs, skills, instructions)
- **`.opencode/plugins/`** — AI agent plugins (e.g. `block-dangerous-git.ts` blocks `git push`, `git reset --hard`, etc.)
- **`.opencode/skills/`** — AI agent skills
- **`.env.example`** — environment variable template
- **`src/`** — Python source (empty starter layout)

---

## Getting started

```bash
# 1. Copy this folder to a new location
cp -r ~/projects/template ~/projects/<new-project>

# 2. Set up environment variables
cd ~/projects/<new-project>
cp .env.example .env
# edit .env with your values

# 3. Install Python dependencies
uv sync

# 4. Verify the scaffold
make help
make lint

# 5. Add your code under src/<package>/ and tests under tests/.
#    When you add tests, add a `test` target to the Makefile that runs pytest.
#    Update pyproject.toml's [project] name and authors.
```

---

## Conventions

- **No `CONTEXT.md` / `PROJECT.md` / `DECISIONS.md` stubs.** These are lazy-created when they have content. `CONTEXT.md` is the domain glossary; `docs/adr/NNNN-title.md` holds individual architectural decisions.
- **No empty placeholders.** If a file isn't relevant to your project, delete it. Don't leave empty stubs.
- **Standards currency.** Files in `docs/standards/` were last verified against upstream docs in June 2026. Before relying on a rule in a long-lived project, re-verify against current docs if more than 6 months have passed.

---

## License

MIT. See [LICENSE](LICENSE).
