"""Pure parser turning chunks.jsonl content into ordered retrieval row models (ticket #40).

The SQLite IndexStage (ticket #41) consumes these rows and assigns
``document_id`` / ``chunk_id`` while inserting; this module performs no
database or filesystem work.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

CHUNK_SEPARATOR = "\0"


@dataclass(frozen=True)
class ChunkRow:
    """A chunk in retrieval row form; ``chunk_uuid`` is verbatim from chunks.jsonl."""

    chunk_uuid: str
    text: str
    start_line: int
    end_line: int
    sha256: str


@dataclass(frozen=True)
class DocumentRow:
    """An ordered document with its chunks in file order."""

    path: str
    sha256: str
    chunks: tuple[ChunkRow, ...]


def parse_chunks(content: str) -> list[DocumentRow]:
    """Parse *content* (raw ``chunks.jsonl`` text) into ordered ``DocumentRow`` values.

    Documents appear in first-appearance order; each document's chunks keep
    chunks.jsonl order. ``DocumentRow.sha256`` is the sha256 of the document's
    ordered chunk texts joined with an explicit ``\\0`` separator.
    ``chunk_uuid`` is taken verbatim from the ``chunk_id`` field — never
    rewritten.

    Parameters
    ----------
    content : str
        Raw ``chunks.jsonl`` text.

    Returns
    -------
    list[DocumentRow]
        Documents in first-appearance order.

    Raises
    ------
    json.JSONDecodeError
        If any line is not valid JSON.
    """
    chunks_by_path: dict[str, list[ChunkRow]] = {}
    for line in content.splitlines():
        record = json.loads(line)
        chunks_by_path.setdefault(record["path"], []).append(
            ChunkRow(
                chunk_uuid=record["chunk_id"],
                text=record["text"],
                start_line=record["start_line"],
                end_line=record["end_line"],
                sha256=record["sha256"],
            )
        )

    return [
        DocumentRow(
            path=path,
            sha256=hashlib.sha256(CHUNK_SEPARATOR.join(c.text for c in chunks).encode()).hexdigest(),
            chunks=tuple(chunks),
        )
        for path, chunks in chunks_by_path.items()
    ]
