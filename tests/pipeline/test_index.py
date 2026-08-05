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


def _chunk_record(
    *,
    chunk_id: str,
    path: str,
    start_line: int,
    end_line: int,
    text: str,
) -> dict[str, str | int]:
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


def test_index_stage_indexes_chunk_metadata(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    record = _chunk_record(chunk_id="chunk-1", path="a.md", start_line=1, end_line=5, text="alpha\nbeta")
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


def test_index_stage_multiple_chunks_all_present(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    records = [
        _chunk_record(chunk_id="chunk-1", path="a.md", start_line=1, end_line=2, text="first"),
        _chunk_record(chunk_id="chunk-2", path="a.md", start_line=3, end_line=4, text="second"),
        _chunk_record(chunk_id="chunk-3", path="b.md", start_line=1, end_line=2, text="third"),
    ]
    _write_chunks(ctx, records)

    IndexStage().execute(ctx)

    index = json.loads((ctx.gold_path / "index" / "metadata.json").read_text(encoding="utf-8"))
    assert index["chunk_count"] == 3
    assert set(index["chunks"]) == {"chunk-1", "chunk-2", "chunk-3"}
    for record in records:
        assert index["chunks"][record["chunk_id"]]["path"] == record["path"]


def test_index_stage_malformed_chunks_line_fails_immediately(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [])
    ctx.chunks_path.write_text(
        '{"chunk_id":"1"}\nthis is not json\n{"chunk_id":"2"}\n',
        encoding="utf-8",
    )

    with pytest.raises(json.JSONDecodeError):
        IndexStage().execute(ctx)

    assert not (ctx.gold_path / "index" / "metadata.json").exists()


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
        _chunk_record(chunk_id="chunk-1", path="a.md", start_line=1, end_line=3, text="content one"),
        _chunk_record(chunk_id="chunk-2", path="b.md", start_line=1, end_line=2, text="content two"),
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
    _write_chunks(ctx, [_chunk_record(chunk_id="chunk-1", path="a.md", start_line=1, end_line=2, text="stable")])

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
    _write_chunks(ctx, [_chunk_record(chunk_id="chunk-1", path="a.md", start_line=1, end_line=2, text="old text")])

    stage = IndexStage()
    stage.execute(ctx)

    metadata_json = ctx.gold_path / "index" / "metadata.json"
    original = metadata_json.read_bytes()

    _write_chunks(ctx, [_chunk_record(chunk_id="chunk-1", path="a.md", start_line=1, end_line=2, text="new text")])
    stage.execute(ctx)

    assert metadata_json.read_bytes() != original
    index = json.loads(metadata_json.read_text(encoding="utf-8"))
    assert index["chunks"]["chunk-1"]["sha256"] == hashlib.sha256(b"new text").hexdigest()


def test_index_stage_rebuilds_when_existing_index_unparseable(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [_chunk_record(chunk_id="chunk-1", path="a.md", start_line=1, end_line=2, text="stable")])

    stage = IndexStage()
    stage.execute(ctx)

    metadata_json = ctx.gold_path / "index" / "metadata.json"
    metadata_json.write_text("{ truncated json", encoding="utf-8")

    stage.execute(ctx)

    index = json.loads(metadata_json.read_text(encoding="utf-8"))
    assert index["chunks"]["chunk-1"]["path"] == "a.md"
