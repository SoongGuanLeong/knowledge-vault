"""Unit tests for retrieval/rows.py: pure chunks.jsonl -> DocumentRow parser (ticket #40)."""

from __future__ import annotations

import hashlib
import json

import pytest

from knowledge_vault.retrieval.rows import parse_chunks


def _chunk(
    chunk_id: str,
    path: str,
    text: str,
    start_line: int = 1,
    end_line: int = 1,
) -> dict[str, object]:
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


def _jsonl(records: list[dict[str, object]]) -> str:
    if not records:
        return ""
    return "\n".join(json.dumps(r) for r in records) + "\n"


def test_parse_chunks_empty_content_returns_empty_list() -> None:
    assert parse_chunks("") == []


def test_parse_chunks_single_chunk_passes_fields_through_verbatim() -> None:
    record = _chunk(chunk_id="verbatim-!$", path="intro.md", text="hello world", start_line=3, end_line=5)
    docs = parse_chunks(_jsonl([record]))

    assert len(docs) == 1
    doc = docs[0]
    assert doc.path == "intro.md"
    assert len(doc.chunks) == 1
    chunk = doc.chunks[0]
    assert chunk.chunk_uuid == "verbatim-!$"
    assert chunk.text == "hello world"
    assert chunk.start_line == 3
    assert chunk.end_line == 5
    assert chunk.sha256 == hashlib.sha256(b"hello world").hexdigest()
    assert doc.sha256 == hashlib.sha256(b"hello world").hexdigest()


def test_parse_chunks_document_sha256_joins_ordered_texts_with_null_separator() -> None:
    records = [
        _chunk(chunk_id="c1", path="a.md", text="alpha", start_line=1, end_line=2),
        _chunk(chunk_id="c2", path="a.md", text="beta", start_line=3, end_line=4),
    ]
    docs = parse_chunks(_jsonl(records))

    assert len(docs) == 1
    doc = docs[0]
    assert [c.chunk_uuid for c in doc.chunks] == ["c1", "c2"]
    assert [c.text for c in doc.chunks] == ["alpha", "beta"]
    assert doc.sha256 == hashlib.sha256(b"alpha\0beta").hexdigest()


def test_parse_chunks_sha256_independent_per_document() -> None:
    records = [
        _chunk(chunk_id="c1", path="a.md", text="alpha"),
        _chunk(chunk_id="c2", path="b.md", text="beta"),
    ]
    docs = parse_chunks(_jsonl(records))

    expected = {
        "a.md": hashlib.sha256(b"alpha").hexdigest(),
        "b.md": hashlib.sha256(b"beta").hexdigest(),
    }
    assert {d.path: d.sha256 for d in docs} == expected


def test_parse_chunks_documents_ordered_by_first_appearance_chunks_in_file_order() -> None:
    records = [
        _chunk(chunk_id="c1", path="b.md", text="one"),
        _chunk(chunk_id="c2", path="a.md", text="two"),
        _chunk(chunk_id="c3", path="b.md", text="three"),
    ]
    docs = parse_chunks(_jsonl(records))

    assert [d.path for d in docs] == ["b.md", "a.md"]
    assert [c.chunk_uuid for c in docs[0].chunks] == ["c1", "c3"]
    assert [c.chunk_uuid for c in docs[1].chunks] == ["c2"]


def test_parse_chunks_deterministic_across_parses() -> None:
    records = [
        _chunk(chunk_id="c1", path="a.md", text="alpha"),
        _chunk(chunk_id="c2", path="b.md", text="beta"),
    ]
    content = _jsonl(records)

    assert parse_chunks(content) == parse_chunks(content)


def test_parse_chunks_malformed_line_raises_json_decode_error() -> None:
    records = [_chunk(chunk_id="c1", path="a.md", text="one")]
    content = _jsonl(records).rstrip("\n") + "\nthis is not json\n"

    with pytest.raises(json.JSONDecodeError):
        parse_chunks(content)


def test_parse_chunks_empty_text_chunk_included() -> None:
    """Chunk with empty text is still a chunk; doc sha256 hashes the empty string."""
    records = [
        _chunk(chunk_id="c1", path="a.md", text="alpha"),
        _chunk(chunk_id="c2", path="empty.md", text=""),
    ]
    docs = parse_chunks(_jsonl(records))

    assert len(docs) == 2
    empty_doc = next(d for d in docs if d.path == "empty.md")
    assert empty_doc.sha256 == hashlib.sha256(b"").hexdigest()
    assert len(empty_doc.chunks) == 1
    assert empty_doc.chunks[0].text == ""
    assert empty_doc.chunks[0].chunk_uuid == "c2"
