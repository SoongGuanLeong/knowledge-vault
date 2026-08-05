"""Unit tests for pipeline/index.py: IndexStage deterministic gold index (ticket #20)."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from knowledge_vault.config import SourceConfig
from knowledge_vault.pipeline import IndexStage
from knowledge_vault.pipeline.context import PipelineContext


def _chunk_record(chunk_id: str, path: str, start_line: int, end_line: int, text: str) -> dict[str, str | int]:
    return {
        "chunk_id": chunk_id,
        "source": "test-source",
        "version": "1.0.0",
        "path": path,
        "text": text,
        "start_line": start_line,
        "end_line": end_line,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "parent_document": path,
    }


def _write_chunks(ctx: PipelineContext, records: list[dict[str, str | int]]) -> None:
    ctx.chunks_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records]
    content = "\n".join(lines) + "\n" if lines else ""
    ctx.chunks_path.write_text(content, encoding="utf-8")


@pytest.fixture
def make_ctx(tmp_path: Path):
    """Factory producing an isolated PipelineContext under pytest's tmp_path."""
    counter = 0

    def _make() -> PipelineContext:
        nonlocal counter
        counter += 1
        base = tmp_path / f"ctx-{counter}"
        config = SourceConfig(
            name="test-source",
            repo="file:///fake/repo",
            docs_path="docs",
            desired_tags=["v1.0.0"],
        )
        store = base / "store"
        silver = base / "silver" / "test-source" / "1.0.0"
        bronze = base / "bronze" / "test-source" / "1.0.0"
        gold = base / "gold" / "test-source" / "1.0.0"
        return PipelineContext(
            store=store,
            config=config,
            tag="v1.0.0",
            version="1.0.0",
            commit="abc1234",
            bronze_path=bronze,
            silver_path=silver,
            gold_path=gold,
            chunks_path=silver / "chunks" / "chunks.jsonl",
            repo_dir=bronze / "repo",
            manifest_path=bronze / "manifest.json",
        )

    return _make


def test_index_stage_missing_chunks_raises_naming_artifact(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()

    with pytest.raises(FileNotFoundError) as excinfo:
        IndexStage().execute(ctx)

    message = str(excinfo.value)
    assert "chunks.jsonl" in message
    assert "Run ChunkStage before IndexStage." in message


def test_index_stage_empty_chunks_produces_valid_empty_index(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [])

    stage = IndexStage()
    result = stage.execute(ctx)
    assert result is ctx

    metadata_json = ctx.gold_path / "index" / "metadata.json"
    assert metadata_json.is_file()

    index = json.loads(metadata_json.read_text(encoding="utf-8"))
    empty_sha = hashlib.sha256(b"").hexdigest()
    assert index["schema_version"] == 1
    assert index["chunks_sha256"] == empty_sha
    assert index["chunk_count"] == 0
    assert index["chunks"] == {}


def test_index_stage_non_empty_input_yields_envelope(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    record = _chunk_record("chunk-1", "a.md", 1, 5, "alpha\nbeta")
    _write_chunks(ctx, [record])

    IndexStage().execute(ctx)

    metadata_json = ctx.gold_path / "index" / "metadata.json"
    index = json.loads(metadata_json.read_text(encoding="utf-8"))
    assert index["schema_version"] == 1
    assert index["chunk_count"] == 1
    assert index["chunks_sha256"] == hashlib.sha256(ctx.chunks_path.read_bytes()).hexdigest()
    assert index["chunks"] == {
        "chunk-1": {
            "path": "a.md",
            "start_line": 1,
            "end_line": 5,
            "parent_document": "a.md",
            "sha256": record["sha256"],
        },
    }


def test_index_stage_chunks_key_always_present(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [])

    IndexStage().execute(ctx)

    index = json.loads((ctx.gold_path / "index" / "metadata.json").read_text(encoding="utf-8"))
    assert "chunks" in index


def test_index_stage_no_timestamp_byte_identical_for_identical_input(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    records = [
        _chunk_record("chunk-1", "a.md", 1, 3, "content one"),
        _chunk_record("chunk-2", "b.md", 1, 2, "content two"),
    ]

    ctx1 = make_ctx()
    _write_chunks(ctx1, records)
    IndexStage().execute(ctx1)
    content1 = (ctx1.gold_path / "index" / "metadata.json").read_bytes()

    ctx2 = make_ctx()
    _write_chunks(ctx2, records)
    IndexStage().execute(ctx2)
    content2 = (ctx2.gold_path / "index" / "metadata.json").read_bytes()

    assert content1 == content2
    assert b"generated_at" not in content1
    assert b"timestamp" not in content1


def test_index_stage_skips_when_chunks_sha_matches(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [_chunk_record("chunk-1", "a.md", 1, 2, "stable")])

    stage = IndexStage()
    stage.execute(ctx)

    metadata_json = ctx.gold_path / "index" / "metadata.json"
    os.utime(metadata_json, (1000, 1000))

    stage.execute(ctx)

    assert os.path.getmtime(metadata_json) == 1000


def test_index_stage_rebuilds_when_chunks_change(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [_chunk_record("chunk-1", "a.md", 1, 2, "old text")])

    stage = IndexStage()
    stage.execute(ctx)

    metadata_json = ctx.gold_path / "index" / "metadata.json"
    original = metadata_json.read_bytes()

    _write_chunks(ctx, [_chunk_record("chunk-1", "a.md", 1, 2, "new text")])
    stage.execute(ctx)

    assert metadata_json.read_bytes() != original
    index = json.loads(metadata_json.read_text(encoding="utf-8"))
    assert index["chunks"]["chunk-1"]["sha256"] == hashlib.sha256(b"new text").hexdigest()


def test_index_stage_skip_does_not_rewrite_existing_index(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [_chunk_record("chunk-1", "a.md", 1, 2, "stable")])

    stage = IndexStage()
    stage.execute(ctx)

    metadata_json = ctx.gold_path / "index" / "metadata.json"
    corrupted = json.loads(metadata_json.read_text(encoding="utf-8"))
    corrupted["chunks"]["chunk-1"]["path"] = "tampered.md"
    corrupted_json = json.dumps(corrupted, indent=2) + "\n"
    metadata_json.write_text(corrupted_json, encoding="utf-8")

    stage.execute(ctx)

    assert metadata_json.read_text(encoding="utf-8") == corrupted_json


def test_index_stage_rebuilds_when_existing_index_unparseable(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [_chunk_record("chunk-1", "a.md", 1, 2, "stable")])

    stage = IndexStage()
    stage.execute(ctx)

    metadata_json = ctx.gold_path / "index" / "metadata.json"
    metadata_json.write_text("{ truncated json", encoding="utf-8")

    stage.execute(ctx)

    index = json.loads(metadata_json.read_text(encoding="utf-8"))
    assert index["chunks"]["chunk-1"]["path"] == "a.md"
