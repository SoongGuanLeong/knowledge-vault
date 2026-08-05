"""Chunking helpers: recursive splitting, overlap, and char-offset line index."""

from __future__ import annotations

DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", " ", ""]
DEFAULT_CHUNK_SIZE: int = 1000
DEFAULT_CHUNK_OVERLAP: int = 150


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
