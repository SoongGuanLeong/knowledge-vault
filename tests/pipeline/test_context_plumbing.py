"""Unit tests for the PipelineContext chunks-path plumbing (ticket #19).

Covers the ``chunks_path`` field added to :class:`PipelineContext`.
"""

from __future__ import annotations

from pathlib import Path

from knowledge_vault.config import SourceConfig
from knowledge_vault.ingest import _build_context
from knowledge_vault.store import silver_dir


def test_build_context_chunks_path_matches_chunk_stage_output(tmp_path: Path, repo_url: str) -> None:
    config = SourceConfig(name="spark", repo=repo_url, docs_path="docs", desired_tags=["v0.1.0"])
    store = tmp_path / "store"

    ctx = _build_context(config, "v0.1.0", store)

    assert ctx.chunks_path == ctx.silver_path / "chunks" / "chunks.jsonl"
    assert ctx.chunks_path == silver_dir(store, "spark", "0.1.0") / "chunks" / "chunks.jsonl"
