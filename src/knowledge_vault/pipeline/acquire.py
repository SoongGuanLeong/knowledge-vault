"""Acquire stage: git partial clone into bronze."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowledge_vault.git import acquire
from knowledge_vault.pipeline.context import PipelineContext


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AcquireStage:
    """Acquire a repository snapshot into the bronze layer.

    Checks for an existing manifest with matching commit (idempotent skip),
    performs a partial clone if needed, and writes ``manifest.json``.
    """

    def execute(self, ctx: PipelineContext) -> bool:
        """Run acquisition for *ctx*'s repository.

        Parameters
        ----------
        ctx : PipelineContext
            Immutable pipeline context carrying store, config, tag, version, commit.

        Returns
        -------
        bool
            True if newly acquired, False if skipped (already present with matching commit).
        """
        manifest_path = ctx.bronze_path / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("commit") == ctx.commit:
                print(f"{ctx.config.name} already present at {ctx.tag} ({ctx.commit})")
                return False

        repo_dir = ctx.bronze_path / "repo"
        ctx.bronze_path.mkdir(parents=True, exist_ok=True)
        acquire(ctx.config.repo, ctx.tag, ctx.commit, repo_dir)

        _write_json(
            manifest_path,
            {
                "name": ctx.config.name,
                "repo": ctx.config.repo,
                "requested_tag": ctx.tag,
                "resolved_tag": ctx.tag,
                "commit": ctx.commit,
                "retrieved_at": _now_iso(),
                "docs_path": ctx.config.docs_path,
            },
        )
        print(f"{ctx.config.name} acquired {ctx.tag} ({ctx.commit})")
        return True
