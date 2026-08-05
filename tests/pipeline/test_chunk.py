"""Unit tests for pipeline/chunk.py: recursive splitting, overlap, line index."""

from __future__ import annotations

import hashlib
import string
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from knowledge_vault.config import SourceConfig
from knowledge_vault.pipeline import chunk
from knowledge_vault.pipeline.context import PipelineContext


def _make_doc(paragraphs: int, para_chars: int) -> str:
    """Build a deterministic doc of *paragraphs* paragraphs, each *para_chars* chars."""
    words = string.ascii_lowercase
    body = "".join(words[i % len(words)] for i in range(para_chars))
    return "\n\n".join(body for _ in range(paragraphs))


def test_recursive_split_caps_chunks_at_chunk_size() -> None:
    text = _make_doc(paragraphs=5, para_chars=600)
    chunks = chunk.recursive_split(text, chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE)
    assert chunks, "expected non-empty chunk list"
    assert max(len(c) for c in chunks) <= chunk.DEFAULT_CHUNK_SIZE


def test_recursive_split_preserves_content_on_join() -> None:
    text = _make_doc(paragraphs=5, para_chars=600)
    chunks = chunk.recursive_split(text, chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE)
    assert "".join(chunks) == text


def test_recursive_split_short_text_is_single_chunk() -> None:
    assert chunk.recursive_split("short text", chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE) == ["short text"]


def test_recursive_split_empty_text_returns_empty() -> None:
    assert chunk.recursive_split("", chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE) == []


def test_recursive_split_uses_paragraph_breaks() -> None:
    text = "p1\n\np2\n\np3"
    # chunk_size smaller than text to force splitting on "\n\n"
    chunks = chunk.recursive_split(text, ["\n\n", "\n", " ", ""], 5)
    assert "".join(chunks) == text
    assert len(chunks) > 1
    # every chunk except the last ends on a paragraph break (separator retained)
    for c in chunks[:-1]:
        assert c.endswith("\n\n")


def test_recursive_split_is_deterministic() -> None:
    text = _make_doc(paragraphs=7, para_chars=700)
    args = (chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE)
    assert chunk.recursive_split(text, *args) == chunk.recursive_split(text, *args)


def test_apply_overlap_prepends_suffix_of_previous_chunk() -> None:
    chunks = ["AAAA1234", "BBBB5678", "CCCC9012"]
    overlapped = chunk.apply_overlap(chunks, 4)
    assert overlapped[0] == "AAAA1234"
    assert overlapped[1] == "1234BBBB5678"
    assert overlapped[2] == "5678CCCC9012"


def test_apply_overlap_zero_or_single_chunk() -> None:
    assert chunk.apply_overlap(["only"], 150) == ["only"]
    assert chunk.apply_overlap(["a", "b"], 0) == ["a", "b"]
    assert chunk.apply_overlap([], 150) == []


def test_apply_overlap_stays_within_boundaries() -> None:
    short_prev = "ab"
    chunks = [short_prev, "CCCCCCCCCCCC"]
    overlapped = chunk.apply_overlap(chunks, 150)
    assert overlapped[1] == short_prev + "CCCCCCCCCCCC"


def test_apply_overlap_only_between_adjacent_chunks_in_same_document() -> None:
    doc_a = ["AAAA1111", "BBBB2222"]
    doc_b = ["CCCC3333", "DDDD4444"]
    over_a = chunk.apply_overlap(doc_a, 4)
    over_b = chunk.apply_overlap(doc_b, 4)
    assert over_a[0] == "AAAA1111"
    assert over_a[1] == "1111BBBB2222"
    assert over_b[0] == "CCCC3333"
    assert over_b[1] == "3333DDDD4444"
    # No bleed: doc_b first chunk never receives doc_a suffix.
    assert not over_b[0].startswith("1111")


def test_apply_overlap_is_deterministic() -> None:
    chunks = [f"chunk{i}" * 200 for i in range(4)]
    assert chunk.apply_overlap(chunks, 150) == chunk.apply_overlap(chunks, 150)


def test_apply_overlap_default_with_real_split() -> None:
    text = _make_doc(paragraphs=6, para_chars=400)
    chunks = chunk.recursive_split(text, chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE)
    overlapped = chunk.apply_overlap(chunks, chunk.DEFAULT_CHUNK_OVERLAP)
    assert len(overlapped) == len(chunks)
    assert overlapped[0] == chunks[0]
    for i in range(1, len(chunks)):
        expected_prefix = chunks[i - 1][-chunk.DEFAULT_CHUNK_OVERLAP :]
        assert overlapped[i].startswith(expected_prefix)


def test_recursive_split_forces_character_level_with_small_chunk_size() -> None:
    text = "abcdefgh"
    chunks = chunk.recursive_split(text, chunk.DEFAULT_SEPARATORS, 3)
    assert chunks == ["abc", "def", "gh"]
    assert "".join(chunks) == text
    assert max(len(c) for c in chunks) <= 3


def test_recursive_split_separator_not_found_falls_through() -> None:
    text = "a b c d e f g h"  # spaces only; no newlines
    chunks = chunk.recursive_split(text, chunk.DEFAULT_SEPARATORS, 4)
    assert "".join(chunks) == text
    assert max(len(c) for c in chunks) <= 4


def test_line_start_index_offsets() -> None:
    text = "ab\ncd\nef"
    assert chunk.line_start_index(text) == [0, 3, 6]


def test_line_start_index_single_line() -> None:
    assert chunk.line_start_index("no newlines") == [0]


def test_line_start_index_empty() -> None:
    assert chunk.line_start_index("") == [0]


def test_line_start_index_trailing_newline() -> None:
    assert chunk.line_start_index("a\n") == [0, 2]


def test_line_start_index_is_one_indexed() -> None:
    text = "l1\nl2\nl3"
    starts = chunk.line_start_index(text)
    assert starts[0] == 0  # line 1
    assert text[starts[0] :] == "l1\nl2\nl3"
    assert text[starts[1] :] == "l2\nl3"
    assert text[starts[2] :] == "l3"


# --- Chunk metadata tests (ticket #13 re-verification) ---


def test_offset_to_line_maps_to_correct_line() -> None:
    text = "line1\nline2\nline3"
    starts = chunk.line_start_index(text)
    assert chunk._offset_to_line(starts, 0) == 1
    assert chunk._offset_to_line(starts, 5) == 1  # within line 1 (before \n at index 5)
    assert chunk._offset_to_line(starts, 6) == 2  # line 2 starts at index 6
    assert chunk._offset_to_line(starts, 11) == 2  # within line 2
    assert chunk._offset_to_line(starts, 12) == 3  # line 3 starts at index 12


def test_offset_to_line_handles_end_of_text() -> None:
    text = "abc\ndef"
    starts = chunk.line_start_index(text)
    assert chunk._offset_to_line(starts, 6) == 2  # last char of text


def test_offset_to_line_empty_text() -> None:
    starts = chunk.line_start_index("")
    assert chunk._offset_to_line(starts, 0) == 1


def test_build_chunk_record_populates_all_fields(make_build_ctx: Callable[[], tuple[PipelineContext, str]]) -> None:
    ctx, chunk_text = make_build_ctx()
    record = chunk._build_chunk_record(chunk_text, "doc.md", ctx)

    assert list(record.keys()) == list(chunk.ChunkRecord.__annotations__.keys())
    assert len(record) == 9
    assert record["text"] == chunk_text
    assert record["path"] == "doc.md"
    assert record["parent_document"] == "doc.md"
    assert record["source"] == ctx.config.name
    assert record["version"] == ctx.version


def test_build_chunk_record_chunk_id_is_deterministic_uuidv5(
    make_build_ctx: Callable[[], tuple[PipelineContext, str]],
) -> None:
    ctx, chunk_text = make_build_ctx()
    record = chunk._build_chunk_record(chunk_text, "doc.md", ctx)

    assert record["chunk_id"] == str(uuid.uuid5(chunk.CHUNK_NAMESPACE, chunk_text))
    again = chunk._build_chunk_record(chunk_text, "doc.md", ctx)
    assert record["chunk_id"] == again["chunk_id"]


def test_build_chunk_record_chunk_id_varies_with_text(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _make_silver_docs(ctx, {"doc.md": "hello\n\nhello!"})

    id1 = chunk._build_chunk_record("hello", "doc.md", ctx)["chunk_id"]
    id2 = chunk._build_chunk_record("hello", "doc.md", ctx)["chunk_id"]
    id3 = chunk._build_chunk_record("hello!", "doc.md", ctx)["chunk_id"]

    assert id1 == id2  # same text → same ID
    assert id3 != id1  # different text → different ID


def test_build_chunk_record_sha256_matches_hashlib(
    make_build_ctx: Callable[[], tuple[PipelineContext, str]],
) -> None:
    ctx, chunk_text = make_build_ctx()
    record = chunk._build_chunk_record(chunk_text, "doc.md", ctx)

    assert record["sha256"] == hashlib.sha256(chunk_text.encode()).hexdigest()


def test_build_chunk_record_line_numbers_are_one_indexed(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _make_silver_docs(ctx, {"doc.md": "line1\nline2\nline3"})
    record = chunk._build_chunk_record("line2\nline3", "doc.md", ctx)

    assert record["start_line"] == 2
    assert record["end_line"] == 3


# --- ChunkStage tests (ticket #14) ---


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
        return PipelineContext(
            store=store,
            config=config,
            tag="v1.0.0",
            version="1.0.0",
            commit="abc1234",
            bronze_path=bronze,
            silver_path=silver,
            repo_dir=bronze / "repo",
            manifest_path=bronze / "manifest.json",
        )

    return _make


@pytest.fixture
def make_build_ctx(make_ctx):
    """Factory producing a (ctx, chunk_text) pair with a doc on disk for line lookup."""

    def _make() -> tuple[PipelineContext, str]:
        ctx = make_ctx()
        _make_silver_docs(ctx, {"doc.md": "para1\n\npara2\n\npara3\n\npara4"})
        return ctx, "para2\n\npara3"

    return _make


def _make_silver_docs(ctx: PipelineContext, docs: dict[str, str]) -> None:
    docs_dir = ctx.silver_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in docs.items():
        p = docs_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_chunk_stage_creates_output_files(make_ctx: Callable[[], PipelineContext]) -> None:
    import json

    ctx = make_ctx()
    _make_silver_docs(ctx, {"a.md": "hello world\n", "b.md": "second doc\n"})

    stage = chunk.ChunkStage()
    result = stage.execute(ctx)
    assert result is ctx

    chunks_jsonl = ctx.silver_path / "chunks" / "chunks.jsonl"
    manifest_json = ctx.silver_path / "chunks" / "manifest.json"
    assert chunks_jsonl.is_file()
    assert manifest_json.is_file()

    manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
    assert manifest["name"] == "test-source"
    assert manifest["version"] == "1.0.0"
    assert manifest["total_chunks"] >= 2
    assert manifest["file_chunks"] == 2
    assert manifest["chunk_size"] == chunk.DEFAULT_CHUNK_SIZE
    assert manifest["chunk_overlap"] == chunk.DEFAULT_CHUNK_OVERLAP
    assert manifest["separators"] == chunk.DEFAULT_SEPARATORS
    assert "chunks_sha256" in manifest
    assert "generated_at" in manifest
    assert manifest["bronze"]["commit"] == "abc1234"

    # chunks_sha256 matches actual file content
    actual_sha = hashlib.sha256(chunks_jsonl.read_bytes()).hexdigest()
    assert manifest["chunks_sha256"] == actual_sha


def test_chunk_stage_chunks_jsonl_has_9_fields_in_stable_order(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    import json

    ctx = make_ctx()
    _make_silver_docs(ctx, {"doc.md": "line1\nline2\nline3\n"})

    stage = chunk.ChunkStage()
    stage.execute(ctx)

    chunks_jsonl = ctx.silver_path / "chunks" / "chunks.jsonl"
    expected_fields = list(chunk.ChunkRecord.__annotations__.keys())
    for line in chunks_jsonl.read_text(encoding="utf-8").strip().split("\n"):
        record = json.loads(line)
        assert list(record.keys()) == expected_fields


def test_chunk_stage_sorts_records_by_path_then_start_line(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    import json

    ctx = make_ctx()
    _make_silver_docs(ctx, {"b.md": "b content\n", "a.md": "a content\n"})

    stage = chunk.ChunkStage()
    stage.execute(ctx)

    chunks_jsonl = ctx.silver_path / "chunks" / "chunks.jsonl"
    records = [json.loads(line) for line in chunks_jsonl.read_text(encoding="utf-8").strip().split("\n")]
    # Records sorted by path, then ascending start_line within each path
    keys = [(r["path"], r["start_line"]) for r in records]
    assert keys == sorted(keys)


def test_chunk_stage_idempotent_skip_when_input_unchanged(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _make_silver_docs(ctx, {"doc.md": "some content here\n"})

    stage = chunk.ChunkStage()
    result1 = stage.execute(ctx)
    assert result1 is ctx

    chunks_jsonl = ctx.silver_path / "chunks" / "chunks.jsonl"
    original_content = chunks_jsonl.read_bytes()

    # Re-run with unchanged inputs: should skip, returning ctx unchanged
    result2 = stage.execute(ctx)
    assert result2 is ctx

    assert chunks_jsonl.read_bytes() == original_content


def test_chunk_stage_reprocesses_when_silver_docs_change(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _make_silver_docs(ctx, {"doc.md": "some content here\n"})

    stage = chunk.ChunkStage()
    stage.execute(ctx)

    chunks_jsonl = ctx.silver_path / "chunks" / "chunks.jsonl"
    original_content = chunks_jsonl.read_bytes()

    # Modify the source docs; output must be rebuilt, not silently skipped
    (ctx.silver_path / "docs" / "doc.md").write_text("completely different\ncontent\n", encoding="utf-8")
    result = stage.execute(ctx)
    assert result is ctx
    assert chunks_jsonl.read_bytes() != original_content


def test_chunk_stage_reprocesses_when_manifest_corrupted(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _make_silver_docs(ctx, {"doc.md": "content\n"})

    stage = chunk.ChunkStage()
    stage.execute(ctx)

    chunks_jsonl = ctx.silver_path / "chunks" / "chunks.jsonl"
    original_content = chunks_jsonl.read_bytes()

    # Corrupt the manifest sha
    manifest_json = ctx.silver_path / "chunks" / "manifest.json"
    import json

    manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
    manifest["chunks_sha256"] = "deadbeef" * 8
    manifest_json.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # Re-run: should reprocess
    result = stage.execute(ctx)
    assert result is ctx
    assert chunks_jsonl.read_bytes() == original_content  # content should be same

    # Manifest rewritten with a valid chunks_sha256 for the current chunks
    new_manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
    assert new_manifest["chunks_sha256"] == hashlib.sha256(chunks_jsonl.read_bytes()).hexdigest()


def test_chunk_stage_empty_docs_dir_produces_empty_chunks(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    import json

    ctx = make_ctx()
    # Create empty docs dir
    docs_dir = ctx.silver_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    stage = chunk.ChunkStage()
    result = stage.execute(ctx)
    assert result is ctx

    chunks_jsonl = ctx.silver_path / "chunks" / "chunks.jsonl"
    assert chunks_jsonl.is_file()
    # Should be empty (no chunks)
    content = chunks_jsonl.read_text(encoding="utf-8")
    assert content == ""

    manifest = json.loads((ctx.silver_path / "chunks" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["total_chunks"] == 0
    assert manifest["file_chunks"] == 0


def test_chunk_stage_no_docs_dir_proceeds_gracefully(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    import json

    ctx = make_ctx()
    # Don't create docs dir at all

    stage = chunk.ChunkStage()
    result = stage.execute(ctx)
    assert result is ctx

    chunks_jsonl = ctx.silver_path / "chunks" / "chunks.jsonl"
    assert chunks_jsonl.is_file()

    manifest = json.loads((ctx.silver_path / "chunks" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["total_chunks"] == 0


def test_chunk_stage_filters_non_doc_extensions(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    import json

    ctx = make_ctx()
    _make_silver_docs(
        ctx,
        {
            "real.md": "content\n",
            "also.txt": "notes\n",
            "nested/deep.md": "nested content\n",
        },
    )
    # A genuinely binary file (null bytes), not just a misleading extension label
    (ctx.silver_path / "docs" / "ignored.png").parent.mkdir(parents=True, exist_ok=True)
    (ctx.silver_path / "docs" / "ignored.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00binary")

    stage = chunk.ChunkStage()
    stage.execute(ctx)

    manifest = json.loads((ctx.silver_path / "chunks" / "manifest.json").read_text(encoding="utf-8"))
    doc_paths = [entry["path"] for entry in manifest["documents_chunked"]]
    assert "real.md" in doc_paths
    assert "also.txt" in doc_paths
    assert "nested/deep.md" in doc_paths
    assert "ignored.png" not in doc_paths
    assert manifest["file_chunks"] == 3


def test_chunk_stage_single_chunk_when_text_matches_chunk_size(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    import json

    ctx = make_ctx()
    doc_text = "x" * chunk.DEFAULT_CHUNK_SIZE  # exactly one chunk-sized doc
    _make_silver_docs(ctx, {"doc.md": doc_text})

    stage = chunk.ChunkStage()
    stage.execute(ctx)

    chunks_jsonl = ctx.silver_path / "chunks" / "chunks.jsonl"
    records = [json.loads(line) for line in chunks_jsonl.read_text(encoding="utf-8").strip().split("\n")]
    assert len(records) == 1
    assert records[0]["text"] == doc_text


def test_chunk_stage_chunk_size_one_splits_into_characters(
    monkeypatch: pytest.MonkeyPatch,
    make_ctx: Callable[[], PipelineContext],
) -> None:
    import json

    monkeypatch.setattr(chunk, "DEFAULT_CHUNK_SIZE", 1)
    monkeypatch.setattr(chunk, "DEFAULT_CHUNK_OVERLAP", 0)

    ctx = make_ctx()
    _make_silver_docs(ctx, {"doc.md": "abc"})

    stage = chunk.ChunkStage()
    stage.execute(ctx)

    chunks_jsonl = ctx.silver_path / "chunks" / "chunks.jsonl"
    texts = [json.loads(line)["text"] for line in chunks_jsonl.read_text(encoding="utf-8").strip().split("\n")]
    assert texts == ["a", "b", "c"]


def test_chunk_stage_deterministic_output(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx1 = make_ctx()
    _make_silver_docs(ctx1, {"doc.md": "deterministic\ncontent\n" * 50})
    stage = chunk.ChunkStage()
    stage.execute(ctx1)

    content1 = (ctx1.silver_path / "chunks" / "chunks.jsonl").read_bytes()

    ctx2 = make_ctx()
    _make_silver_docs(ctx2, {"doc.md": "deterministic\ncontent\n" * 50})
    stage2 = chunk.ChunkStage()
    stage2.execute(ctx2)

    content2 = (ctx2.silver_path / "chunks" / "chunks.jsonl").read_bytes()
    assert content1 == content2
