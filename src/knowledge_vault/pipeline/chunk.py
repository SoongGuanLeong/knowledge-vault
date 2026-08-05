"""Chunking helpers: recursive splitting, overlap, char-offset line index, chunk metadata."""

from __future__ import annotations

import bisect
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from knowledge_vault.pipeline._io import write_json
from knowledge_vault.pipeline.context import PipelineContext

DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", " ", ""]
DEFAULT_CHUNK_SIZE: int = 1000
DEFAULT_CHUNK_OVERLAP: int = 150

CHUNK_NAMESPACE: uuid.UUID = uuid.uuid5(uuid.NAMESPACE_DNS, "knowledge-vault.chunk-id")

DOC_EXTENSIONS: list[str] = [".md", ".mdx", ".rst", ".txt", ".adoc", ".html"]


class ChunkRecord(TypedDict):
    """A chunk record emitted to ``chunks.jsonl``."""

    chunk_id: str
    source: str
    version: str
    path: str
    text: str
    start_line: int
    end_line: int
    sha256: str
    parent_document: str


def _split_with_separator(text: str, separator: str) -> list[str]:
    """Split *text* on *separator*, keeping the separator attached to each preceding piece."""
    if separator == "":
        return list(text) if text else [""]
    parts = text.split(separator)
    pieces: list[str] = []
    for i, part in enumerate(parts):
        if i < len(parts) - 1:
            pieces.append(part + separator)
        else:
            pieces.append(part)
    return pieces


def _greedy_merge(pieces: list[str], chunk_size: int) -> list[str]:
    """Concatenate adjacent *pieces* greedily, never exceeding *chunk_size*."""
    if not pieces:
        return []
    chunks: list[str] = []
    current = pieces[0]
    for piece in pieces[1:]:
        if len(current) + len(piece) <= chunk_size:
            current += piece
        else:
            chunks.append(current)
            current = piece
    chunks.append(current)
    return chunks


def recursive_split(text: str, separators: list[str], chunk_size: int) -> list[str]:
    """Split *text* recursively by *separators* (largest first), capping chunks at *chunk_size*.

    Returns deterministic, separator-attached pieces greedily merged toward *chunk_size*.
    """
    if len(text) <= chunk_size:
        return [text] if text else []
    if not separators:
        return [text]

    sep = separators[0]
    sub = _split_with_separator(text, sep)

    if len(sub) <= 1:
        return recursive_split(text, separators[1:], chunk_size)

    pieces: list[str] = []
    for piece in sub:
        if len(piece) <= chunk_size:
            pieces.append(piece)
        else:
            pieces.extend(recursive_split(piece, separators[1:], chunk_size))

    pieces = [p for p in pieces if p]
    return _greedy_merge(pieces, chunk_size)


def apply_overlap(chunks: list[str], chunk_overlap: int) -> list[str]:
    """Prepend the last *chunk_overlap* chars of each preceding chunk to the next.

    First chunk is unchanged; overlap stays within document boundaries.
    """
    if chunk_overlap <= 0 or len(chunks) <= 1:
        return list(chunks)

    result: list[str] = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        overlap = prev[-chunk_overlap:] if len(prev) >= chunk_overlap else prev
        result.append(overlap + chunks[i])
    return result


def line_start_index(text: str) -> list[int]:
    """Return 1-indexed line start character offsets for *text* (offset 0 == line 1)."""
    starts: list[int] = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _offset_to_line(starts: list[int], offset: int) -> int:
    """Map a character *offset* to a 1-indexed line number via *starts*."""
    return bisect.bisect_right(starts, offset)


def _build_chunk_record(
    chunk_text: str,
    doc_path: str,
    ctx: PipelineContext,
) -> ChunkRecord:
    """Enrich *chunk_text* with the 9 schema fields (chunk_id, source, version, path,
    text, start_line, end_line, sha256, parent_document).

    Reads the parent document from ``ctx.silver_path / "docs" / doc_path`` to compute
    1-indexed line numbers via :func:`line_start_index`.
    """
    document_text = (ctx.silver_path / "docs" / doc_path).read_text(encoding="utf-8")
    starts = line_start_index(document_text)

    start_char = document_text.find(chunk_text)
    if start_char == -1:
        raise ValueError(f"chunk text not found in document {doc_path!r} (silver_path={ctx.silver_path})")
    end_char = start_char + len(chunk_text) - 1

    chunk_id = str(uuid.uuid5(CHUNK_NAMESPACE, chunk_text))
    sha = hashlib.sha256(chunk_text.encode()).hexdigest()

    return {
        "chunk_id": chunk_id,
        "source": ctx.config.name,
        "version": ctx.version,
        "path": doc_path,
        "text": chunk_text,
        "start_line": _offset_to_line(starts, start_char),
        "end_line": _offset_to_line(starts, end_char),
        "sha256": sha,
        "parent_document": doc_path,
    }


def _silver_fingerprint(ctx: PipelineContext) -> str:
    """Deterministic sha256 over the silver docs ChunkStage consumes.

    Hashes each doc-extension file's relative path and bytes so any out-of-band
    change to ``silver/docs`` (not just a re-extraction) invalidates the fingerprint.
    """
    h = hashlib.sha256()
    docs_dir = ctx.silver_path / "docs"
    if docs_dir.is_dir():
        for f in sorted(docs_dir.rglob("*")):
            if f.is_file() and f.suffix.lower() in DOC_EXTENSIONS:
                h.update(str(f.relative_to(docs_dir)).encode())
                h.update(b"\0")
                h.update(f.read_bytes())
                h.update(b"\0")
    return h.hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ChunkStage:
    """Chunk silver-layer documents into JSONL + manifest.

    Idempotent: skips when ``chunks/chunks.jsonl`` and ``chunks/manifest.json``
    exist, ``manifest["chunks_sha256"]`` matches the SHA-256 of the file contents,
    and ``manifest["silver_fingerprint"]`` matches the current Silver docs state.
    """

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Run chunking for *ctx*'s silver docs.

        Parameters
        ----------
        ctx : PipelineContext
            Immutable pipeline context carrying silver_path, config, version.

        Returns
        -------
        PipelineContext
            The same context (chunking does not modify context).
        """
        chunks_dir = ctx.silver_path / "chunks"
        chunks_jsonl = chunks_dir / "chunks.jsonl"
        manifest_json = chunks_dir / "manifest.json"

        if chunks_jsonl.is_file() and manifest_json.is_file():
            manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
            stored_sha = manifest.get("chunks_sha256", "")
            actual_sha = hashlib.sha256(chunks_jsonl.read_bytes()).hexdigest()
            stored_fp = manifest.get("silver_fingerprint", "")
            if stored_sha == actual_sha and stored_fp == _silver_fingerprint(ctx):
                print(f"{ctx.config.name} chunks already up-to-date at v{ctx.version}")
                return ctx

        docs_dir = ctx.silver_path / "docs"
        documents: list[tuple[str, Path]] = []
        if docs_dir.is_dir():
            for f in sorted(docs_dir.rglob("*")):
                if f.is_file() and f.suffix.lower() in DOC_EXTENSIONS:
                    rel = str(f.relative_to(docs_dir))
                    documents.append((rel, f))
            documents.sort(key=lambda item: item[0])

        all_records: list[ChunkRecord] = []
        documents_chunked: list[dict[str, str]] = []

        for rel_path, doc_file in documents:
            text = doc_file.read_text(encoding="utf-8")
            chunks = recursive_split(text, DEFAULT_SEPARATORS, DEFAULT_CHUNK_SIZE)
            chunks = apply_overlap(chunks, DEFAULT_CHUNK_OVERLAP)
            for chunk_text in chunks:
                record = _build_chunk_record(chunk_text, rel_path, ctx)
                all_records.append(record)
            documents_chunked.append({"path": rel_path})

        all_records.sort(key=lambda r: (r["path"], r["start_line"]))

        chunks_dir.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        for record in all_records:
            lines.append(json.dumps(record))
        chunks_content = "\n".join(lines) + "\n" if lines else ""
        chunks_jsonl.write_text(chunks_content, encoding="utf-8")

        chunks_sha256 = hashlib.sha256(chunks_jsonl.read_bytes()).hexdigest()

        write_json(
            manifest_json,
            {
                "name": ctx.config.name,
                "version": ctx.version,
                "bronze": {"name": ctx.config.name, "version": ctx.version, "commit": ctx.commit},
                "total_chunks": len(all_records),
                "documents_chunked": documents_chunked,
                "file_chunks": len(documents_chunked),
                "chunk_size": DEFAULT_CHUNK_SIZE,
                "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
                "separators": DEFAULT_SEPARATORS,
                "silver_fingerprint": _silver_fingerprint(ctx),
                "chunks_sha256": chunks_sha256,
                "generated_at": _now_iso(),
            },
        )

        print(
            f"{ctx.config.name} chunked v{ctx.version}: "
            f"{len(all_records)} chunks from {len(documents_chunked)} documents"
        )
        return ctx
