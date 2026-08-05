"""Unit tests for the IndexStage gold-path plumbing (ticket #19).

Covers the ``gold_dir`` store helper and the ``gold_path`` / ``chunks_path``
fields added to :class:`PipelineContext`.
"""

from __future__ import annotations

from pathlib import Path

from knowledge_vault.config import SourceConfig
from knowledge_vault.ingest import _build_context
from knowledge_vault.store import gold_dir, silver_dir


def test_gold_dir_resolves_to_store_gold_name_version(tmp_path: Path) -> None:
    store = tmp_path / "store"
    assert gold_dir(store, "spark", "0.1.0") == store / "gold" / "spark" / "0.1.0"


def test_gold_dir_lives_under_gold_layer(tmp_path: Path) -> None:
    store = tmp_path / "store"
    name, version = "docs", "2.3.0"
    assert gold_dir(store, name, version).parents[1] == store / "gold"
    assert gold_dir(store, name, version).parent == store / "gold" / name


def test_build_context_populates_gold_path(tmp_path: Path, repo_url: str) -> None:
    config = SourceConfig(name="spark", repo=repo_url, docs_path="docs", desired_tags=["v0.1.0"])
    store = tmp_path / "store"

    ctx = _build_context(config, "v0.1.0", store)

    assert ctx.gold_path == gold_dir(store, "spark", "0.1.0")
    assert ctx.gold_path == store / "gold" / "spark" / "0.1.0"


def test_build_context_chunks_path_matches_chunk_stage_output(tmp_path: Path, repo_url: str) -> None:
    config = SourceConfig(name="spark", repo=repo_url, docs_path="docs", desired_tags=["v0.1.0"])
    store = tmp_path / "store"

    ctx = _build_context(config, "v0.1.0", store)

    assert ctx.chunks_path == ctx.silver_path / "chunks" / "chunks.jsonl"
    assert ctx.chunks_path == silver_dir(store, "spark", "0.1.0") / "chunks" / "chunks.jsonl"
